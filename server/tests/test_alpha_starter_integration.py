"""Alpha starter money must be granted once per player, not per company."""
import os
import unittest
from uuid import uuid4
from basheco.db import connect
from basheco.migrate import main as migrate
from basheco.api import _grant_starter, ALPHA_STARTER_KOPECKS

@unittest.skipUnless(os.environ.get('BASHECO_TEST_DATABASE_URL'), 'Disposable test database required')
class StarterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.environ['BASHECO_TEST_DATABASE_URL']
        if not url.rstrip('/').endswith('/basheco_integration_test'):
            raise RuntimeError('Refusing non-test database')
        os.environ['DATABASE_URL'] = url
        migrate()

    def test_one_grant_across_two_companies(self):
        with connect() as conn:
            account = conn.execute('INSERT INTO accounts(email,display_name,password_hash) VALUES(%s,%s,%s) RETURNING id', (f'alpha-{uuid4()}@example.invalid','Alpha Player','test-only')).fetchone()['id']
            companies = []
            for name in ('Alpha One', 'Alpha Two'):
                company = conn.execute('INSERT INTO companies(owner_account_id,name) VALUES(%s,%s) RETURNING id', (account,name)).fetchone()['id']
                wallet = conn.execute('INSERT INTO wallets(company_id) VALUES(%s) RETURNING id', (company,)).fetchone()['id']
                companies.append((company,wallet))
            self.assertEqual(_grant_starter(conn, account, companies[0][0]), ALPHA_STARTER_KOPECKS)
            self.assertEqual(_grant_starter(conn, account, companies[0][0]), 0)
            self.assertEqual(_grant_starter(conn, account, companies[1][0]), 0)
            amounts = [conn.execute('SELECT balance_kopecks FROM wallets WHERE id=%s', (wallet,)).fetchone()['balance_kopecks'] for _,wallet in companies]
            self.assertEqual(amounts, [ALPHA_STARTER_KOPECKS, 0])
            self.assertEqual(conn.execute('SELECT count(*) AS n FROM alpha_starter_grants WHERE account_id=%s', (account,)).fetchone()['n'],1)
            # Explicit rollback: the disposable test database remains clean.
            conn.rollback()
