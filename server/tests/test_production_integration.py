"""Disposable DB integration tests for production, replay and concurrency."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from fastapi import HTTPException
from basheco.db import connect
from basheco.migrate import main as migrate
from basheco.production import ProduceRequest,produce,inventory,catalog
from basheco.world import ConstructRequest,construct

@unittest.skipUnless(os.environ.get("BASHECO_TEST_DATABASE_URL"),"Disposable test DB required")
class ProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get("BASHECO_TEST_DATABASE_URL"):
            return
        url=os.environ["BASHECO_TEST_DATABASE_URL"]
        if not url.rstrip("/").endswith("/basheco_integration_test"):
            raise RuntimeError("Refusing non-test database")
        os.environ["DATABASE_URL"]=url
        migrate()

    def setUp(self):
        with connect() as conn:
            self.account=conn.execute(
                "INSERT INTO accounts(email,display_name,password_hash) "
                "VALUES(%s,'Producer','test') RETURNING id",
                (f"prod-{uuid4()}@example.invalid",),
            ).fetchone()["id"]
            self.company=conn.execute(
                "INSERT INTO companies(owner_account_id,name) VALUES(%s,'Producer Co') RETURNING id",
                (self.account,),
            ).fetchone()["id"]
            self.plot=conn.execute(
                "INSERT INTO world_plots(sector_id,tile_x,tile_y,width_tiles,height_tiles,zone) "
                "VALUES('ufa',80,80,5,5,'agricultural') RETURNING id"
            ).fetchone()["id"]
        self.building=construct(ConstructRequest(
            company_id=self.company,plot_id=self.plot,building_type="greenhouse"
        ),str(self.account))["building_id"]

    def tearDown(self):
        with connect() as conn:
            conn.execute("DELETE FROM production_runs WHERE company_id=%s",(self.company,))
            conn.execute("DELETE FROM company_inventory WHERE company_id=%s",(self.company,))
            conn.execute("DELETE FROM world_buildings WHERE plot_id=%s",(self.plot,))
            conn.execute("DELETE FROM world_plots WHERE id=%s",(self.plot,))
            conn.execute("DELETE FROM companies WHERE id=%s",(self.company,))
            conn.execute("DELETE FROM accounts WHERE id=%s",(self.account,))

    def request(self,key="production-test-123",recipe="grow_vegetables"):
        return ProduceRequest(building_id=self.building,recipe_code=recipe,idempotency_key=key)

    def test_catalog_and_inventory(self):
        self.assertEqual(len(catalog()["recipes"]),3)
        self.assertEqual(inventory(str(self.account))["inventory"],[])

    def test_produce_replay_and_cooldown(self):
        first=produce(self.request(),str(self.account))
        self.assertFalse(first["replayed"])
        self.assertTrue(produce(self.request(),str(self.account))["replayed"])
        with self.assertRaises(HTTPException) as ctx:
            produce(self.request("production-test-456"),str(self.account))
        self.assertEqual(ctx.exception.status_code,429)
        self.assertEqual(inventory(str(self.account))["inventory"][0]["quantity"],10)

    def test_wrong_recipe_and_wrong_owner(self):
        with self.assertRaises(HTTPException) as ctx:
            produce(self.request(recipe="pack_food"),str(self.account))
        self.assertEqual(ctx.exception.status_code,422)
        with self.assertRaises(HTTPException) as ctx:
            produce(self.request(),str(uuid4()))
        self.assertEqual(ctx.exception.status_code,403)

    def test_concurrent_same_key_single_output(self):
        def action(_):
            return produce(self.request(),str(self.account))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(action,range(2)))
        self.assertEqual(sorted(x["replayed"] for x in results),[False,True])
        self.assertEqual(inventory(str(self.account))["inventory"][0]["quantity"],10)

    def test_key_reuse_conflict(self):
        produce(self.request(),str(self.account))
        with self.assertRaises(HTTPException) as ctx:
            produce(self.request(recipe="make_parts"),str(self.account))
        self.assertEqual(ctx.exception.status_code,409)
