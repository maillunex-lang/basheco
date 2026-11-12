"""World integration tests run only on disposable basheco_integration_test DB."""
import os
import unittest
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from fastapi import HTTPException
from basheco.db import connect
from basheco.world import (ConstructRequest, construct, sector_map, sector_viewport, NewPlotRequest,
                           create_plot, world_viewport, world_grid_info)
from basheco.migrate import main as migrate

@unittest.skipUnless(os.environ.get("BASHECO_TEST_DATABASE_URL"), "Disposable test database required")
class WorldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get("BASHECO_TEST_DATABASE_URL"):
            return
        url = os.environ["BASHECO_TEST_DATABASE_URL"]
        if not url.rstrip("/").endswith("/basheco_integration_test"):
            raise RuntimeError("Refusing non-test database")
        os.environ["DATABASE_URL"] = url
        migrate()

    def setUp(self):
        with connect() as conn:
            self.accounts = []
            self.companies = []
            for _ in range(2):
                aid = conn.execute(
                    "INSERT INTO accounts(email,display_name,password_hash) VALUES(%s,'Builder','test-only') RETURNING id",
                    (f"world-{uuid4()}@example.invalid",)
                ).fetchone()["id"]
                cid = conn.execute(
                    "INSERT INTO companies(owner_account_id,name) VALUES(%s,'Builder Co') RETURNING id",
                    (aid,)
                ).fetchone()["id"]
                self.accounts.append(aid)
                self.companies.append(cid)
            self.plot = conn.execute(
                "INSERT INTO world_plots(sector_id,tile_x,tile_y,width_tiles,height_tiles,zone) "
                "VALUES('ufa',2,2,5,5,'commercial') RETURNING id"
            ).fetchone()["id"]

    def tearDown(self):
        with connect() as conn:
            conn.execute("DELETE FROM world_buildings WHERE plot_id=%s", (self.plot,))
            conn.execute("UPDATE world_plots SET owner_company_id=NULL WHERE id=%s", (self.plot,))
            conn.execute("DELETE FROM world_plots WHERE id=%s", (self.plot,))
            conn.execute("DELETE FROM companies WHERE id=ANY(%s::uuid[])", (self.companies,))
            conn.execute("DELETE FROM accounts WHERE id=ANY(%s::uuid[])", (self.accounts,))

    def req(self, idx=0, building="shop"):
        return ConstructRequest(company_id=self.companies[idx],plot_id=self.plot,building_type=building)

    def test_sector_is_prototype(self):
        world=sector_map("ufa")
        self.assertEqual(world["sector"]["geometry_source"],"osm-background")
        self.assertGreaterEqual(len(world["plots"]),1)

    def test_viewport_only_intersecting_parcels(self):
        visible = sector_viewport("ufa", 0, 0, 8, 8)
        self.assertEqual(visible["viewport"]["max_x"], 8)
        self.assertEqual(len(visible["plots"]), 1)
        self.assertEqual(visible["plots"][0]["tile_x"], 2)
        empty = sector_viewport("ufa", 300, 300, 310, 310)
        self.assertEqual(empty["plots"], [])
        with self.assertRaises(HTTPException) as ctx:
            sector_viewport("ufa", 0, 0, 1000, 1000)
        self.assertEqual(ctx.exception.status_code, 422)

    def test_new_parcel_overlap_and_quota(self):
        created = []
        try:
            for x in (200, 210, 220):
                row = create_plot(NewPlotRequest(sector_id="ufa", tile_x=x,
                                                  tile_y=200, zone="industrial"),
                                  str(self.accounts[0]))
                created.append(row["plot_id"])
            with self.assertRaises(HTTPException) as overlap:
                create_plot(NewPlotRequest(sector_id="ufa", tile_x=202,
                                           tile_y=200, zone="industrial"),
                            str(self.accounts[1]))
            self.assertEqual(overlap.exception.status_code, 409)
            with self.assertRaises(HTTPException) as quota:
                create_plot(NewPlotRequest(sector_id="ufa", tile_x=230,
                                           tile_y=200, zone="industrial"),
                            str(self.accounts[0]))
            self.assertEqual(quota.exception.status_code, 409)
        finally:
            with connect() as conn:
                conn.execute("DELETE FROM world_plots WHERE id=ANY(%s::uuid[])", (created,))

    def test_building_and_double_claim(self):
        result=construct(self.req(),str(self.accounts[0]))
        self.assertEqual(result["building_type"],"shop")
        self.assertGreaterEqual(result["new_plots"], 0)
        expanded = sector_map("ufa")
        self.assertGreaterEqual(len(expanded["plots"]), 1)
        with self.assertRaises(HTTPException) as ctx:
            construct(self.req(1),str(self.accounts[1]))
        self.assertEqual(ctx.exception.status_code,409)

    def test_zone_restriction(self):
        with self.assertRaises(HTTPException) as ctx:
            construct(self.req(building="workshop"),str(self.accounts[0]))
        self.assertEqual(ctx.exception.status_code,422)

    def test_foreign_company_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            construct(self.req(),str(self.accounts[1]))
        self.assertEqual(ctx.exception.status_code,403)

    def test_concurrent_claim_only_one_wins(self):
        def attempt(i):
            try:
                return construct(self.req(i),str(self.accounts[i]))
            except HTTPException as e:
                return e.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(attempt,range(2)))
        self.assertEqual(sum(isinstance(x,dict) for x in outcomes),1)
        self.assertIn(409,outcomes)

    # --- Stage 1: one world grid for every settlement ---
    def place_fixture(self):
        from basheco.world_compat import main as backfill
        backfill()
        with connect() as conn:
            return conn.execute("SELECT * FROM world_plots WHERE id=%s", (self.plot,)).fetchone()

    def test_legacy_sector_api_is_unchanged_and_gains_world_cells(self):
        row = self.place_fixture()
        for payload in (sector_map("ufa"), sector_viewport("ufa", 0, 0, 8, 8)):
            plot = next(p for p in payload["plots"] if p["id"] == self.plot)
            for key in ("id", "tile_x", "tile_y", "width_tiles", "height_tiles", "zone",
                        "owner_company_id", "building_id", "building_type"):
                self.assertIn(key, plot)
            self.assertEqual((plot["tile_x"], plot["tile_y"]), (2, 2))
            self.assertEqual((plot["world_cell_x"], plot["world_cell_y"]),
                             (row["world_cell_x"], row["world_cell_y"]))
            self.assertEqual(set(payload["sector"]), {"id", "name", "city", "width_tiles",
                                                      "height_tiles", "geometry_source"})

    def test_world_viewport_uses_global_cells_across_settlements(self):
        row = self.place_fixture()
        x, y = row["world_cell_x"], row["world_cell_y"]
        self.assertLess(y, 0)  # the world has negative cell coordinates near Ufa
        with connect() as conn:
            other = conn.execute(
                "INSERT INTO world_plots(sector_id,tile_x,tile_y,width_tiles,height_tiles,zone,"
                "world_cell_x,world_cell_y,world_cell_source) "
                "VALUES('mikhailovka',4000,4000,5,5,'industrial',%s,%s,'legacy_anchor_v1') RETURNING id",
                (x + 20, y)).fetchone()["id"]
        try:
            seen = world_viewport(x - 10, y - 10, x + 40, y + 10)
            self.assertEqual({p["id"] for p in seen["plots"]}, {self.plot, other})
            self.assertEqual({p["sector_id"] for p in seen["plots"]}, {"ufa", "mikhailovka"})
            self.assertEqual(seen["grid"]["crs"], "EPSG:32640")
            self.assertEqual([p["id"] for p in world_viewport(x + 4, y + 4, x + 5, y + 5)["plots"]], [self.plot])
            self.assertEqual(world_viewport(x + 5, y, x + 6, y + 5)["plots"], [])   # half-open edge
            self.assertEqual(world_viewport(x - 200, y - 200, x - 100, y - 100)["plots"], [])
        finally:
            with connect() as conn:
                conn.execute("DELETE FROM world_plots WHERE id=%s", (other,))
        for bad in ((0, 0, 0, 10), (0, 0, 513, 10), (10, 0, 0, 10), (0, 0, 2 ** 41, 1)):
            with self.assertRaises(HTTPException) as ctx:
                world_viewport(*bad)
            self.assertEqual(ctx.exception.status_code, 422)

    def test_unplaced_plots_are_counted_not_shown(self):
        with connect() as conn:
            conn.execute("UPDATE world_plots SET world_cell_x=NULL,world_cell_y=NULL,"
                         "world_cell_source=NULL,world_cell_offset_m=NULL WHERE id=%s", (self.plot,))
        seen = world_viewport(72000, -1011300, 72500, -1010800)
        self.assertNotIn(self.plot, {p["id"] for p in seen["plots"]})
        self.assertGreaterEqual(seen["unplaced_plot_count"], 1)

    def test_new_parcels_are_placed_and_cannot_overlap_another_settlement(self):
        from basheco.geodata import LocalProjection
        from basheco.world_compat import legacy_tile_to_lonlat, load_anchors
        created = []
        try:
            first = create_plot(NewPlotRequest(sector_id="ufa", tile_x=300, tile_y=300, zone="industrial"),
                                str(self.accounts[0]))
            created.append(first["plot_id"])
            self.assertGreater(first["world_cell_x"], 60000)
            self.assertLess(first["world_cell_y"], -900000)
            with connect() as conn:
                anchors = load_anchors(conn)
            lon, lat = legacy_tile_to_lonlat(anchors["ufa"], 302, 302)
            mikh = anchors["mikhailovka"]
            local = LocalProjection(mikh.origin_lon, mikh.origin_lat).project(lon, lat)
            tile_x = round(mikh.origin_tile_x + local[0] / 6)
            tile_y = round(mikh.origin_tile_y + local[1] / 6)
            with self.assertRaises(HTTPException) as ctx:  # same ground, other settlement's sector
                create_plot(NewPlotRequest(sector_id="mikhailovka", tile_x=tile_x, tile_y=tile_y,
                                           zone="industrial"), str(self.accounts[1]))
            self.assertEqual(ctx.exception.status_code, 409)
            seen = world_viewport(first["world_cell_x"], first["world_cell_y"],
                                  first["world_cell_x"] + 5, first["world_cell_y"] + 5)
            self.assertEqual([str(p["id"]) for p in seen["plots"]], [first["plot_id"]])
        finally:
            with connect() as conn:
                conn.execute("DELETE FROM world_plots WHERE id=ANY(%s::uuid[])", (created,))

    def test_grid_contract(self):
        info = world_grid_info()
        self.assertEqual(info["grid"]["grid_version"], "basheco-grid/1")
        self.assertEqual({a["sector_id"] for a in info["legacy_sector_anchors"]}, {"ufa", "mikhailovka"})
