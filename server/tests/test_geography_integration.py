"""Geography provenance and NPC simulation must remain separate."""
import os
import unittest
from basheco.db import connect
from basheco.migrate import main as migrate

@unittest.skipUnless(os.environ.get('BASHECO_TEST_DATABASE_URL'), 'Disposable test database required')
class GeographyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.environ['BASHECO_TEST_DATABASE_URL']
        if not url.rstrip('/').endswith('/basheco_integration_test'):
            raise RuntimeError('Refusing non-test database')
        os.environ['DATABASE_URL'] = url
        migrate()

    def test_prototype_location_has_no_fabricated_statistics(self):
        with connect() as conn:
            row = conn.execute("SELECT id,playable FROM geo_locations WHERE id='ufa'").fetchone()
            self.assertEqual(row['id'], 'ufa')
            self.assertTrue(row['playable'])
            count = conn.execute("SELECT count(*) AS n FROM geo_statistics WHERE location_id='ufa'").fetchone()['n']
            self.assertEqual(count, 0)

    def test_statistics_require_provenance_and_npc_is_distinct(self):
        with connect() as conn:
            official_columns = {r['column_name'] for r in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='geo_statistics'")}
            npc_columns = {r['column_name'] for r in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='npc_economy_parameters'")}
            self.assertTrue({'reference_year','source_name','source_url','retrieved_on','geography_scope'} <= official_columns)
            self.assertTrue({'simulation_population','simulation_monthly_income_kopecks','simulation_consumption_fraction'} <= npc_columns)
            self.assertNotIn('source_url', npc_columns)
