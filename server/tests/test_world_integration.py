"""World integration tests run only on disposable basheco_integration_test DB."""
import os
import unittest
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from fastapi import HTTPException
from basheco.db import connect
from basheco.world import ConstructRequest, construct, sector_map
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
                "SELECT id FROM world_plots WHERE sector_id='ufa-prototype-01' AND zone='commercial' "
                "AND owner_company_id IS NULL ORDER BY tile_x LIMIT 1 FOR UPDATE"
            ).fetchone()["id"]

    def tearDown(self):
        with connect() as conn:
            conn.execute("DELETE FROM world_buildings WHERE plot_id=%s", (self.plot,))
            conn.execute("UPDATE world_plots SET owner_company_id=NULL WHERE id=%s", (self.plot,))
            conn.execute("DELETE FROM world_plots WHERE sector_id=%s AND generated_by_growth=true", ("ufa-prototype-01",))
            conn.execute("DELETE FROM companies WHERE id=ANY(%s::uuid[])", (self.companies,))
            conn.execute("DELETE FROM accounts WHERE id=ANY(%s::uuid[])", (self.accounts,))

    def req(self, idx=0, building="shop"):
        return ConstructRequest(company_id=self.companies[idx],plot_id=self.plot,building_type=building)

    def test_sector_is_prototype(self):
        world=sector_map("ufa-prototype-01")
        self.assertEqual(world["sector"]["geometry_source"],"prototype")
        self.assertEqual(len(world["plots"]),6)

    def test_building_and_double_claim(self):
        result=construct(self.req(),str(self.accounts[0]))
        self.assertEqual(result["building_type"],"shop")
        self.assertGreaterEqual(result["new_plots"], 0)
        expanded = sector_map("ufa-prototype-01")
        self.assertGreaterEqual(len(expanded["plots"]), 6)
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
