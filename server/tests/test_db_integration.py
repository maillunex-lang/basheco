"""PostgreSQL integration tests. Run only with BASHECO_TEST_DATABASE_URL.

The supplied database MUST be a disposable test database, never production.
"""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi import HTTPException
from basheco.db import connect
from basheco.api import TransferRequest, transfer
from basheco.migrate import main as migrate

@unittest.skipUnless(os.environ.get("BASHECO_TEST_DATABASE_URL"), "No disposable integration database")
class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get("BASHECO_TEST_DATABASE_URL"):
            return
        url = os.environ["BASHECO_TEST_DATABASE_URL"]
        if not url.rstrip("/").endswith("/basheco_integration_test"):
            raise RuntimeError("Integration database name must be basheco_integration_test")
        os.environ["DATABASE_URL"] = url
        migrate()

    def setUp(self):
        with connect() as conn:
            self.a = conn.execute(
                "INSERT INTO accounts(email,display_name,password_hash) VALUES(%s,'Test User','test-only') RETURNING id",
                (f"test-{uuid4()}@example.invalid",),
            ).fetchone()["id"]
            self.b = conn.execute(
                "INSERT INTO accounts(email,display_name,password_hash) VALUES(%s,'Test User','test-only') RETURNING id",
                (f"test-{uuid4()}@example.invalid",),
            ).fetchone()["id"]
            self.wa = conn.execute(
                "INSERT INTO wallets(account_id,balance_kopecks) VALUES(%s,1000) RETURNING id", (self.a,),
            ).fetchone()["id"]
            self.wb = conn.execute(
                "INSERT INTO wallets(account_id,balance_kopecks) VALUES(%s,0) RETURNING id", (self.b,),
            ).fetchone()["id"]

    def tearDown(self):
        with connect() as conn:
            conn.execute("DELETE FROM security_audit WHERE actor_account_id=ANY(%s::uuid[])", ([self.a,self.b],))
            conn.execute("DELETE FROM ledger_postings WHERE wallet_id=ANY(%s::uuid[])", ([self.wa,self.wb],))
            conn.execute("DELETE FROM ledger_transfers WHERE initiated_by=ANY(%s::uuid[])", ([self.a,self.b],))
            conn.execute("DELETE FROM wallets WHERE id=ANY(%s::uuid[])", ([self.wa,self.wb],))
            conn.execute("DELETE FROM accounts WHERE id=ANY(%s::uuid[])", ([self.a,self.b],))

    def request(self, amount=100, key=None):
        return TransferRequest(
            debit_wallet=self.wa, credit_wallet=self.wb,
            amount_kopecks=amount, idempotency_key=key or str(uuid4()),
        )

    def balances(self):
        with connect() as conn:
            return [conn.execute("SELECT balance_kopecks AS n FROM wallets WHERE id=%s", (i,)).fetchone()["n"] for i in (self.wa,self.wb)]

    def test_success_and_replay(self):
        request = self.request(125)
        first = transfer(request, str(self.a))
        replay = transfer(request, str(self.a))
        self.assertFalse(first["replayed"])
        self.assertTrue(replay["replayed"])
        self.assertEqual(first["transfer_id"], replay["transfer_id"])
        self.assertEqual(self.balances(), [875,125])
        with connect() as conn:
            postings = conn.execute("SELECT delta_kopecks FROM ledger_postings WHERE transfer_id=%s", (first["transfer_id"],)).fetchall()
        self.assertEqual(sorted(x["delta_kopecks"] for x in postings), [-125,125])
        with connect() as conn:
            audit = conn.execute("SELECT count(*) AS n FROM security_audit WHERE event_type=%s AND subject_id=%s", ("wallet.transfer",first["transfer_id"])).fetchone()["n"]
        self.assertEqual(audit,1)
        with self.assertRaises(HTTPException) as ctx:
            transfer(self.request(126,request.idempotency_key),str(self.a))
        self.assertEqual(ctx.exception.status_code,409)

    def test_concurrent_duplicate_key(self):
        request=self.request(250)
        with ThreadPoolExecutor(max_workers=2) as workers:
            responses=list(workers.map(lambda _: transfer(request,str(self.a)),range(2)))
        self.assertEqual(sorted(x["replayed"] for x in responses),[False,True])
        self.assertEqual(self.balances(),[750,250])

    def test_concurrent_double_spend_prevented(self):
        requests=[self.request(800),self.request(800)]
        def run(request):
            try:
                return transfer(request,str(self.a))
            except HTTPException as exc:
                return exc.status_code
        with ThreadPoolExecutor(max_workers=2) as workers:
            results=list(workers.map(run,requests))
        self.assertEqual(sum(isinstance(r,dict) for r in results),1)
        self.assertIn(409,results)
        self.assertEqual(self.balances(),[200,800])

    def test_foreign_wallet_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            transfer(self.request(100),str(self.b))
        self.assertEqual(ctx.exception.status_code,403)
        self.assertEqual(self.balances(),[1000,0])
