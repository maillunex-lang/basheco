import json
import tempfile
import unittest
from pathlib import Path
from basheco.import_osm_xml import convert


class OfflineOSMImportTests(unittest.TestCase):
    def test_way_classification_projection_and_chunk_deduplication(self):
        xml = """<osm version="0.6">
        <node id="1" lat="54.7300" lon="55.9500"/>
        <node id="2" lat="54.7300" lon="55.9550"/>
        <node id="3" lat="54.7301" lon="55.9550"/>
        <node id="4" lat="54.7301" lon="55.9500"/>
        <way id="11"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/></way>
        <way id="12"><nd ref="1"/><nd ref="3"/><nd ref="4"/><nd ref="1"/><tag k="building" v="yes"/></way>
        <way id="13"><nd ref="1"/><nd ref="2"/><tag k="name" v="No classification"/></way>
        </osm>"""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "map.osm").write_text(xml)
            manifest = convert(root / "map.osm", root / "out", "ufa", 55.95, 54.73,
                               "https://www.openstreetmap.org/", "2026-11-12T00:00:00Z")
            self.assertEqual(manifest["unique_feature_count"], 2)
            self.assertEqual(manifest["feature_counts"], {"road": 1, "building": 1})
            self.assertEqual(manifest["license"], "ODbL 1.0")
            self.assertGreater(len(manifest["spatial_chunks"]), 1)
            ids = set()
            for entry in manifest["spatial_chunks"]:
                chunk = json.loads((root / "out" / Path(entry["path"]).name).read_text())
                ids.update(f["id"] for f in chunk["features"])
            self.assertEqual(ids, {11, 12})
            self.assertTrue((root / "out" / "manifest.json").exists())

    def test_source_required(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "empty.osm").write_text('<osm version="0.6"/>')
            with self.assertRaises(ValueError):
                convert(root / "empty.osm", root / "out", "ufa", 55.95, 54.73, "", "2026-11-12")
