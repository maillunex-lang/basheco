import json
import tempfile
import unittest
from pathlib import Path
from basheco.prepare_geodata import prepare

class PrepareGeodataTests(unittest.TestCase):
    def test_source_provenance_and_no_invented_objects(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source'
            source.mkdir()
            (source / 'chunk_0_0.json').write_text(json.dumps({'features': [
                {'osm_id': 'r1', 'kind': 'road', 'coordinates': [[55.969, 54.738], [55.973, 54.738]]},
                {'osm_id': 'b1', 'kind': 'building', 'coordinates': [[55.971, 54.738], [55.9711, 54.738],
                                                                      [55.9711, 54.7381], [55.971, 54.7381]]},
                {'osm_id': 'b2', 'kind': 'building', 'coordinates': [[55.971, 54.738], [55.99, 54.738],
                                                                      [55.99, 54.74], [55.971, 54.738]]}
            ]}), encoding='utf-8')
            (source / 'manifest.json').write_text(json.dumps({
                'bbox': [55.970, 54.737, 55.974, 54.740],
                'source_url': 'https://example.invalid/test-fixture',
                'license': 'ODbL 1.0', 'attribution': '© OpenStreetMap contributors',
                'downloaded_utc': '2026-01-01T00:00:00Z',
                'chunks': [{'path': 'res://data/ufa_chunks/chunk_0_0.json'}]
            }), encoding='utf-8')
            result = prepare(source / 'manifest.json', root / 'output')
            self.assertEqual(result['feature_counts']['building'], 1)
            self.assertGreater(result['feature_counts']['road'], 0)
            self.assertEqual(result['license'], 'ODbL 1.0')
            self.assertEqual(result['status'], 'pilot_snapshot_not_full_city')
            self.assertEqual(json.loads((root / 'output' / 'manifest.json').read_text())['source_url'],
                             'https://example.invalid/test-fixture')

    def test_rejects_untrusted_source_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'manifest.json').write_text(json.dumps({
                'bbox': [55, 54, 56, 55],
                'chunks': [{'path': 'res://data/ufa_chunks/../../private.json'}]
            }))
            with self.assertRaises(ValueError):
                prepare(root / 'manifest.json', root / 'output')
