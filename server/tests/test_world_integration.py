"""World integration tests run only on disposable basheco_integration_test DB."""
import os
import unittest
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from fastapi import HTTPException
from basheco.db import connect
from basheco.world import ConstructRequest, construct, sector_map, sector_viewport, NewPlotRequest, create_plot
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
