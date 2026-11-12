"""Publication and parcel occupancy integration tests on a disposable PostgreSQL 18."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier, Event
from uuid import uuid4

from fastapi import HTTPException
from basheco.db import connect
from basheco.generated_occupancy import generated_overlap, lock_occupancy
from basheco.generated_storage import import_unpublished, prepare, publish_location
from basheco.location_generator import PILOT, build
from basheco.migrate import main as migrate
from basheco.world import NewPlotRequest, create_plot
from basheco.world_compat import LegacyAnchor, backfill_plots, legacy_tile_to_world_cell


def pilot_bundle():
    bundle = build()
    idx = next(i for i, loc in enumerate(bundle["locations"]) if loc["settlement_id"] == PILOT)
    bundle["selection"] = [bundle["selection"][idx]]
    bundle["locations"] = [bundle["locations"][idx]]
    return bundle


@unittest.skipUnless(os.environ.get("BASHECO_TEST_DATABASE_URL"), "Disposable test DB required")
class PublicationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.environ["BASHECO_TEST_DATABASE_URL"]
        if not url.rstrip("/").endswith("/basheco_integration_test"):
            raise RuntimeError("Refusing non-test database")
        os.environ["DATABASE_URL"] = url
        migrate()
        cls.bundle = pilot_bundle()
        cls.locations = cls.bundle["locations"]
        cls.objects = cls.locations[0]["objects"]
        cls.cell = tuple(cls.objects[0]["cell"])

    def setUp(self):
        with connect() as conn:
            conn.execute("DELETE FROM generated_location_chunks")
            conn.execute("DELETE FROM generated_locations")
            self.account = conn.execute(
                "INSERT INTO accounts(email,display_name,password_hash) VALUES(%s,'Pilot Tester','test-only') RETURNING id",
                (f"pilot-{uuid4()}@example.invalid",)).fetchone()["id"]
        self.plot_ids = []

    def tearDown(self):
        with connect() as conn:
            conn.execute("DELETE FROM generated_location_chunks")
            conn.execute("DELETE FROM generated_locations")
            if self.plot_ids:
                conn.execute("DELETE FROM world_plots WHERE id=ANY(%s::uuid[])", (self.plot_ids,))
            conn.execute("DELETE FROM accounts WHERE id=%s", (self.account,))

    def plot_at(self, x, y, placed=True):
        with connect() as conn:
            row = conn.execute(
                "INSERT INTO world_plots(sector_id,tile_x,tile_y,width_tiles,height_tiles,zone,"
                "world_cell_x,world_cell_y,world_cell_source) "
                "VALUES('mikhailovka',%s,%s,1,1,'commercial',%s,%s,%s) RETURNING id",
                (3200 + len(self.plot_ids), 3200, x if placed else None,
                 y if placed else None, 'legacy_anchor_v1' if placed else None)).fetchone()
            self.plot_ids.append(row["id"])
        return row["id"]

    def test_import_idempotency_and_hash_conflict(self):
        self.assertEqual(import_unpublished(self.bundle, dry_run=False)["inserted"], 1)
        self.assertEqual(import_unpublished(self.bundle, dry_run=False)["unchanged"], 1)
        altered = deepcopy(self.bundle)
        altered["locations"][0]["seed"] += 1
        with self.assertRaisesRegex(ValueError, "Immutable snapshot conflict"):
            import_unpublished(altered, dry_run=False)
        self.assertEqual(import_unpublished(self.bundle, dry_run=False)["unchanged"], 1)

    def test_import_rollback_on_collision(self):
        import_unpublished(self.bundle, dry_run=False)
        original = self.bundle
        altered = deepcopy(original)
        altered["locations"][0]["seed"] += 2
        with self.assertRaises(ValueError):
            import_unpublished(altered, dry_run=False)
        with connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) AS n FROM generated_locations").fetchone()["n"], 1)

    def test_publication_is_explicit_and_idempotent(self):
        import_unpublished(self.bundle, dry_run=False)
        with connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) AS n FROM generated_locations WHERE published").fetchone()["n"], 0)
        self.assertFalse(publish_location(PILOT)["unchanged"])
        self.assertTrue(publish_location(PILOT)["unchanged"])

    def test_existing_world_plot_blocks_publication(self):
        import_unpublished(self.bundle, dry_run=False)
        self.plot_at(*self.cell)
        with self.assertRaisesRegex(ValueError, "overlaps a player plot"):
            publish_location(PILOT)
        with connect() as conn:
            self.assertFalse(conn.execute("SELECT published FROM generated_locations WHERE settlement_id=%s",
                                          (PILOT,)).fetchone()["published"])

    def pilot_request(self):
        x, y = self.cell
        with connect() as conn:
            anchor = LegacyAnchor.from_row(conn.execute(
                "SELECT * FROM world_legacy_sector_anchors WHERE sector_id='mikhailovka'").fetchone())
        from basheco.world_projection import metres_to_lonlat
        from basheco.world_grid import cell_to_metre_corner
        from basheco.geodata import LocalProjection
        lon, lat = metres_to_lonlat(*cell_to_metre_corner(x, y))
        e, n = LocalProjection(anchor.origin_lon, anchor.origin_lat).project(lon, lat)
        tx = round(anchor.origin_tile_x + e / anchor.metres_per_tile)
        ty = round(anchor.origin_tile_y + n / anchor.metres_per_tile)
        mapped = legacy_tile_to_world_cell(anchor, tx, ty)
        self.assertEqual(mapped[:2], (x, y))
        return NewPlotRequest(sector_id="mikhailovka", tile_x=tx,
                              tile_y=ty, zone="commercial")

    def test_real_create_plot_rejects_published_road(self):
        request = self.pilot_request()
        import_unpublished(self.bundle, dry_run=False)
        publish_location(PILOT)
        with self.assertRaises(HTTPException) as error:
            create_plot(request, str(self.account))
        self.assertEqual(error.exception.status_code, 409)
        with connect() as conn:
            self.assertEqual(conn.execute(
                "SELECT count(*) AS n FROM world_plots WHERE created_by_account_id=%s",
                (self.account,)).fetchone()["n"], 0)

    def test_concurrent_real_plot_and_publication_never_both_succeed(self):
        request = self.pilot_request()
        import_unpublished(self.bundle, dry_run=False)
        together = Barrier(2)
        def place():
            together.wait(timeout=8)
            try:
                result = create_plot(request, str(self.account))
                self.plot_ids.append(result["plot_id"])
                return "created"
            except HTTPException as exc:
                self.assertEqual(exc.status_code, 409)
                return "blocked"
        def publish():
            together.wait(timeout=8)
            try:
                publish_location(PILOT)
                return "published"
            except ValueError as exc:
                self.assertIn("overlaps a player plot", str(exc))
                return "blocked"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda func: func(), (place, publish)))
        self.assertIn(results, (["created", "blocked"], ["blocked", "published"]))

    def test_published_cell_blocks_new_plot_check(self):
        import_unpublished(self.bundle, dry_run=False)
        publish_location(PILOT)
        x, y = self.cell
        with connect() as conn:
            lock_occupancy(conn)
            self.assertTrue(generated_overlap(conn, x, y, 1, 1))
            self.assertFalse(generated_overlap(conn, x + 1000, y + 1000, 1, 1))

    def test_published_cell_blocks_legacy_backfill(self):
        import_unpublished(self.bundle, dry_run=False)
        publish_location(PILOT)
        with connect() as conn:
            anchor = LegacyAnchor.from_row(conn.execute(
                "SELECT * FROM world_legacy_sector_anchors WHERE sector_id='mikhailovka'").fetchone())
        # Exercise the same mapping logic with the nearest legacy tile to one generated cell.
        x, y = self.cell
        from basheco.world_projection import metres_to_lonlat
        from basheco.world_grid import cell_to_metre_corner
        from basheco.geodata import LocalProjection
        lon, lat = metres_to_lonlat(*cell_to_metre_corner(x, y))
        e, n = LocalProjection(anchor.origin_lon, anchor.origin_lat).project(lon, lat)
        tx = round(anchor.origin_tile_x + e / anchor.metres_per_tile)
        ty = round(anchor.origin_tile_y + n / anchor.metres_per_tile)
        actual = legacy_tile_to_world_cell(anchor, tx, ty)
        self.assertLessEqual(abs(actual[0] - x), 1)
        self.assertLessEqual(abs(actual[1] - y), 1)
        parcel = self.plot_at(x, y, placed=False)
        with connect() as conn:
            conn.execute("UPDATE world_plots SET tile_x=%s,tile_y=%s WHERE id=%s", (tx, ty, parcel))
            report = backfill_plots(conn)
            self.assertIn(str(parcel), report["unmapped_conflict"])
            self.assertIsNone(conn.execute("SELECT world_cell_x FROM world_plots WHERE id=%s", (parcel,)).fetchone()["world_cell_x"])

    def test_publication_and_placement_share_one_lock(self):
        import_unpublished(self.bundle, dry_run=False)
        entered = Event()
        release = Event()
        def hold_lock():
            with connect() as conn:
                lock_occupancy(conn)
                entered.set()
                if not release.wait(10):
                    raise TimeoutError("Test hold lock exceeded 10 seconds")
        def try_publication():
            return publish_location(PILOT)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(hold_lock)
            self.assertTrue(entered.wait(5))
            second = pool.submit(try_publication)
            try:
                self.assertFalse(second.done())
            finally:
                release.set()
            first.result(timeout=10)
            self.assertFalse(second.result(timeout=10)["unchanged"])

    def test_restricted_settlement_rejected(self):
        with self.assertRaises(ValueError):
            publish_location("S80745000001")