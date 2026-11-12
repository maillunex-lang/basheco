"""Upgrade path 014 -> 015 with pre-existing plots, owners and buildings.

Runs in a throw-away schema of the disposable basheco_integration_test database.
"""
import os
import unittest
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from basheco.world_compat import backfill_plots, legacy_tile_to_lonlat, load_anchors
from basheco.world_grid import cell_to_metre_corner
from basheco.world_projection import metres_to_lonlat

SQL = Path(__file__).resolve().parents[1] / "sql"
SNAPSHOT = ("SELECT p.id,p.sector_id,p.tile_x,p.tile_y,p.width_tiles,p.height_tiles,p.zone,"
            "p.owner_company_id,p.created_by_account_id,p.generated_by_growth,"
            "b.id AS building_id,b.company_id,b.building_type,b.built_at "
            "FROM world_plots p LEFT JOIN world_buildings b ON b.plot_id=p.id ORDER BY p.id")


@unittest.skipUnless(os.environ.get("BASHECO_TEST_DATABASE_URL"), "Disposable test database required")
class UpgradePathTests(unittest.TestCase):
    def setUp(self):
        url = os.environ["BASHECO_TEST_DATABASE_URL"]
        if not url.rstrip("/").endswith("/basheco_integration_test"):
            raise RuntimeError("Refusing non-test database")
        self.schema = "stage1_upgrade_" + uuid4().hex[:12]
        self.conn = psycopg.connect(url, row_factory=dict_row, autocommit=True)
        self.conn.execute(f'CREATE SCHEMA "{self.schema}"')
        self.conn.execute(f'SET search_path TO "{self.schema}"')
        for path in sorted(SQL.glob("[0-9]*.sql")):
            if path.name < "015":
                self.conn.execute(path.read_text(encoding="utf-8"))
        # Data as it exists before stage 1: local sector coordinates only.
        account = self.conn.execute(
            "INSERT INTO accounts(email,display_name,password_hash) "
            "VALUES('legacy@example.invalid','Legacy','test-only') RETURNING id").fetchone()["id"]
        self.company = self.conn.execute(
            "INSERT INTO companies(owner_account_id,name) VALUES(%s,'Legacy Co') RETURNING id",
            (account,)).fetchone()["id"]
        self.plots = {}
        for name, sector, x, y, zone, owned in (
                ("ufa_built", "ufa", 30, 40, "commercial", True),
                ("ufa_free", "ufa", 36, 40, "industrial", False),
                ("ufa_far", "ufa", 4000, 3900, "agricultural", False),
                ("mikh_built", "mikhailovka", 150, 180, "industrial", True),
                ("mikh_free", "mikhailovka", 10, 10, "commercial", False)):
            plot = self.conn.execute(
                "INSERT INTO world_plots(sector_id,tile_x,tile_y,width_tiles,height_tiles,zone,"
                "generated_by_growth,created_by_account_id,owner_company_id) "
                "VALUES(%s,%s,%s,5,5,%s,true,%s,%s) RETURNING id",
                (sector, x, y, zone, account, self.company if owned else None)).fetchone()["id"]
            self.plots[name] = plot
            if owned:
                kind = {"commercial": "shop", "industrial": "workshop"}[zone]
                self.conn.execute(
                    "INSERT INTO world_buildings(plot_id,company_id,building_type) VALUES(%s,%s,%s)",
                    (plot, self.company, kind))
        self.before = self.conn.execute(SNAPSHOT).fetchall()

    def tearDown(self):
        self.conn.execute(f'DROP SCHEMA "{self.schema}" CASCADE')
        self.conn.close()

    def upgrade(self):
        self.conn.execute((SQL / "015_world_grid_link.sql").read_text(encoding="utf-8"))
        with self.conn.transaction():
            return backfill_plots(self.conn)

    def test_upgrade_preserves_every_existing_row(self):
        report = self.upgrade()
        self.assertEqual(self.conn.execute(SNAPSHOT).fetchall(), self.before)
        self.assertEqual((report["examined"], report["mapped"], report["still_unmapped"]), (5, 5, 0))
        self.assertEqual(report["unmapped_conflict"], [])
        self.assertLess(report["max_snap_offset_m"], 4.25)

    def test_mapped_plots_sit_where_the_old_client_drew_them(self):
        self.upgrade()
        anchors = load_anchors(self.conn)
        rows = self.conn.execute(
            "SELECT id,sector_id,tile_x,tile_y,world_cell_x,world_cell_y,world_cell_source,"
            "world_cell_offset_m FROM world_plots").fetchall()
        for row in rows:
            self.assertEqual(row["world_cell_source"], "legacy_anchor_v1")
            self.assertNotEqual((row["world_cell_x"], row["world_cell_y"]), (row["tile_x"], row["tile_y"]))
            east, north = cell_to_metre_corner(row["world_cell_x"], row["world_cell_y"])
            lon, lat = metres_to_lonlat(east, north)
            old_lon, old_lat = legacy_tile_to_lonlat(anchors[row["sector_id"]], row["tile_x"], row["tile_y"])
            self.assertAlmostEqual(lon, old_lon, delta=0.00007)   # < 4.3 m
            self.assertAlmostEqual(lat, old_lat, delta=0.00004)
            self.assertLess(row["world_cell_offset_m"], 4.25)
        by_id = {r["id"]: r for r in rows}
        built, free = by_id[self.plots["ufa_built"]], by_id[self.plots["ufa_free"]]
        self.assertEqual(free["world_cell_x"] - built["world_cell_x"], 6)
        # Mikhailovka really is about 9 km north-west of the Ufa extract.
        mikh = by_id[self.plots["mikh_built"]]
        self.assertLess(mikh["world_cell_x"], built["world_cell_x"] - 700)
        self.assertLess(mikh["world_cell_y"], built["world_cell_y"] - 1100)

    def test_backfill_is_idempotent(self):
        self.upgrade()
        placed = self.conn.execute("SELECT id,world_cell_x,world_cell_y FROM world_plots ORDER BY id").fetchall()
        with self.conn.transaction():
            again = backfill_plots(self.conn)
        self.assertEqual((again["examined"], again["mapped"]), (0, 0))
        self.assertEqual(self.conn.execute(
            "SELECT id,world_cell_x,world_cell_y FROM world_plots ORDER BY id").fetchall(), placed)

    def test_cross_settlement_conflict_stays_unmapped_and_owner_wins(self):
        # A vacant Mikhailovka-sector plot on the very ground of the built Ufa plot.
        from basheco.geodata import LocalProjection
        self.conn.execute((SQL / "015_world_grid_link.sql").read_text(encoding="utf-8"))
        anchors = load_anchors(self.conn)
        lon, lat = legacy_tile_to_lonlat(anchors["ufa"], 31, 41)
        mikh = anchors["mikhailovka"]
        local = LocalProjection(mikh.origin_lon, mikh.origin_lat).project(lon, lat)
        tile = (round(mikh.origin_tile_x + local[0] / 6), round(mikh.origin_tile_y + local[1] / 6))
        clash = self.conn.execute(
            "INSERT INTO world_plots(sector_id,tile_x,tile_y,width_tiles,height_tiles,zone) "
            "VALUES('mikhailovka',%s,%s,5,5,'commercial') RETURNING id", tile).fetchone()["id"]
        with self.conn.transaction():
            report = backfill_plots(self.conn)
        self.assertEqual(report["unmapped_conflict"], [str(clash)])
        self.assertEqual(report["still_unmapped"], 1)
        row = self.conn.execute("SELECT * FROM world_plots WHERE id=%s", (clash,)).fetchone()
        self.assertIsNone(row["world_cell_x"])                 # not guessed, not deleted
        self.assertEqual((row["tile_x"], row["tile_y"]), tile)
        owner = self.conn.execute("SELECT world_cell_x FROM world_plots WHERE id=%s",
                                  (self.plots["ufa_built"],)).fetchone()
        self.assertIsNotNone(owner["world_cell_x"])

    def test_sector_without_anchor_is_not_placed(self):
        self.conn.execute("INSERT INTO world_sectors(id,name,city,width_tiles,height_tiles) "
                          "VALUES('unknown-town','?','?',64,64)")
        orphan = self.conn.execute(
            "INSERT INTO world_plots(sector_id,tile_x,tile_y,width_tiles,height_tiles,zone) "
            "VALUES('unknown-town',1,1,5,5,'commercial') RETURNING id").fetchone()["id"]
        report = self.upgrade()
        self.assertEqual(report["unmapped_no_anchor"], [str(orphan)])
        self.assertEqual(report["mapped"], 5)

    def test_database_rejects_overlapping_world_cells(self):
        self.upgrade()
        row = self.conn.execute("SELECT world_cell_x,world_cell_y FROM world_plots WHERE id=%s",
                                (self.plots["ufa_built"],)).fetchone()
        with self.assertRaises(psycopg.errors.ExclusionViolation):
            self.conn.execute(
                "INSERT INTO world_plots(sector_id,tile_x,tile_y,width_tiles,height_tiles,zone,"
                "world_cell_x,world_cell_y,world_cell_source) "
                "VALUES('mikhailovka',3000,3000,5,5,'commercial',%s,%s,'legacy_anchor_v1')",
                (row["world_cell_x"] + 4, row["world_cell_y"] - 4))
        self.conn.execute(  # touching edge to edge is allowed
            "INSERT INTO world_plots(sector_id,tile_x,tile_y,width_tiles,height_tiles,zone,"
            "world_cell_x,world_cell_y,world_cell_source) "
            "VALUES('mikhailovka',3000,3000,5,5,'commercial',%s,%s,'legacy_anchor_v1')",
            (row["world_cell_x"] - 5, row["world_cell_y"]))


if __name__ == "__main__":
    unittest.main()
