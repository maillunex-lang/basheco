"""Marketplace tests on disposable basheco_integration_test only."""
import os
import unittest
from uuid import uuid4,UUID
from concurrent.futures import ThreadPoolExecutor
from fastapi import HTTPException
from basheco.db import connect
from basheco.migrate import main as migrate
from basheco.market import ListRequest,BuyRequest,create_listing,buy,cancel_listing

@unittest.skipUnless(os.environ.get("BASHECO_TEST_DATABASE_URL"),"Disposable test DB required")
class MarketTests(unittest.TestCase):
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
        self.accounts=[]
        self.companies=[]
        self.wallets=[]
        with connect() as conn:
            for i in range(2):
                aid=conn.execute(
                    "INSERT INTO accounts(email,display_name,password_hash) "
                    "VALUES(%s,'Trader','test') RETURNING id",
                    (f"trader-{uuid4()}@example.invalid",),
                ).fetchone()["id"]
                cid=conn.execute(
                    "INSERT INTO companies(owner_account_id,name) VALUES(%s,'Trader Co') RETURNING id",
                    (aid,),
                ).fetchone()["id"]
                wid=conn.execute(
                    "INSERT INTO wallets(company_id,balance_kopecks) VALUES(%s,%s) RETURNING id",
                    (cid,10000 if i==1 else 0),
                ).fetchone()["id"]
                self.accounts.append(aid);self.companies.append(cid);self.wallets.append(wid)
            conn.execute(
                "INSERT INTO company_inventory(company_id,resource_code,quantity) VALUES(%s,'vegetables',20)",
                (self.companies[0],),
            )

    def tearDown(self):
        with connect() as conn:
            ids=[str(x) for x in self.companies]
            conn.execute("DELETE FROM ledger_postings WHERE transfer_id IN "
                         "(SELECT id FROM ledger_transfers WHERE initiated_by=ANY(%s::uuid[]))",
                         ([str(x) for x in self.accounts],))
            conn.execute("DELETE FROM market_purchases WHERE buyer_account_id=ANY(%s::uuid[])",
                         ([str(x) for x in self.accounts],))
            conn.execute("DELETE FROM ledger_transfers WHERE initiated_by=ANY(%s::uuid[])",
                         ([str(x) for x in self.accounts],))
            conn.execute("DELETE FROM market_listings WHERE seller_company_id=ANY(%s::uuid[])",(ids,))
            conn.execute("DELETE FROM company_inventory WHERE company_id=ANY(%s::uuid[])",(ids,))
            conn.execute("DELETE FROM wallets WHERE company_id=ANY(%s::uuid[])",(ids,))
            conn.execute("DELETE FROM companies WHERE id=ANY(%s::uuid[])",(ids,))
            conn.execute("DELETE FROM accounts WHERE id=ANY(%s::uuid[])",
                         ([str(x) for x in self.accounts],))

    def listing(self,quantity=10,price=100):
        return UUID(create_listing(ListRequest(company_id=self.companies[0],resource_code="vegetables",
                                              quantity=quantity,unit_price_kopecks=price),
                                   str(self.accounts[0]))["listing_id"])

    def purchase(self,listing,key="buy-test-123",quantity=4):
        return buy(listing,BuyRequest(company_id=self.companies[1],quantity=quantity,
                                     idempotency_key=key),str(self.accounts[1]))

    def test_sale_ledger_and_replay(self):
        lid=self.listing()
        first=self.purchase(lid)
        self.assertEqual(first["total_kopecks"],400)
        self.assertFalse(first["replayed"])
        self.assertTrue(self.purchase(lid)["replayed"])
        with connect() as conn:
            balances=[conn.execute("SELECT balance_kopecks FROM wallets WHERE id=%s",(w,)).fetchone()["balance_kopecks"] for w in self.wallets]
            self.assertEqual(balances,[400,9600])
            qty=conn.execute("SELECT quantity FROM company_inventory WHERE company_id=%s AND resource_code='vegetables'",
                             (self.companies[1],)).fetchone()["quantity"]
            self.assertEqual(qty,4)
            postings=conn.execute("SELECT sum(delta_kopecks) AS total FROM ledger_postings "
                                  "WHERE transfer_id IN (SELECT transfer_id FROM market_purchases WHERE listing_id=%s)",(lid,)).fetchone()["total"]
            self.assertEqual(postings,0)

    def test_cancel_returns_unsold_escrow(self):
        lid=self.listing()
        self.purchase(lid)
        returned=cancel_listing(lid,str(self.accounts[0]))
        self.assertEqual(returned["returned_quantity"],6)
        with connect() as conn:
            qty=conn.execute("SELECT quantity FROM company_inventory WHERE company_id=%s AND resource_code='vegetables'",
                             (self.companies[0],)).fetchone()["quantity"]
            self.assertEqual(qty,16)
        with self.assertRaises(HTTPException) as ctx:
            self.purchase(lid,"buy-test-other")
        self.assertEqual(ctx.exception.status_code,409)

    def test_no_stock_no_funds_and_ownership(self):
        with self.assertRaises(HTTPException) as ctx:
            self.listing(quantity=21)
        self.assertEqual(ctx.exception.status_code,409)
        lid=self.listing()
        with self.assertRaises(HTTPException) as ctx:
            buy(lid,BuyRequest(company_id=self.companies[0],quantity=1,
                              idempotency_key="own-test-123"),str(self.accounts[0]))
        self.assertEqual(ctx.exception.status_code,422)
        with self.assertRaises(HTTPException) as ctx:
            buy(lid,BuyRequest(company_id=self.companies[1],quantity=1,
                              idempotency_key="foreign-test-123"),str(self.accounts[0]))
        self.assertEqual(ctx.exception.status_code,403)
        with self.assertRaises(HTTPException) as ctx:
            self.purchase(lid,"expensive-test",quantity=10)
        # 10 * 100 = 1000, so this succeeds; use insufficient funds separately.
        self.assertEqual(ctx.exception.status_code,409)

    def test_parallel_buy_single_inventory(self):
        lid=self.listing(quantity=5)
        def attempt(i):
            try:
                return self.purchase(lid,f"parallel-buy-{i}",quantity=4)
            except HTTPException as exc:
                return exc.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(attempt,range(2)))
        self.assertEqual(sum(isinstance(x,dict) for x in results),1)
        self.assertIn(409,results)
        with connect() as conn:
            q=conn.execute("SELECT quantity_remaining FROM market_listings WHERE id=%s",(lid,)).fetchone()["quantity_remaining"]
            self.assertEqual(q,1)
