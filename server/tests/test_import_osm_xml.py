import json
import tempfile
import unittest
from pathlib import Path
from basheco.import_osm_xml import convert
from basheco.osm_source import classify, normalise

XML = """<osm version="0.6">
<bounds minlat="54.7290" minlon="55.9490" maxlat="54.7310" maxlon="55.9560"/>
<node id="1" lat="54.7300" lon="55.9500" user="someone" uid="7"/>
<node id="2" lat="54.7300" lon="55.9550"/>
<node id="3" lat="54.7301" lon="55.9550"/>
<node id="4" lat="54.7301" lon="55.9500"/>
<node id="5" lat="54.7305" lon="55.9500"/>
<way id="11"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/><tag k="name" v="Тестовая улица"/></way>
<way id="12"><nd ref="1"/><nd ref="3"/><nd ref="4"/><nd ref="1"/><tag k="building" v="yes"/></way>
<way id="13"><nd ref="1"/><nd ref="2"/><tag k="name" v="No classification"/></way>
<way id="14"><nd ref="1"/><nd ref="2"/><nd ref="3"/></way>
<way id="15"><nd ref="3"/><nd ref="4"/><nd ref="1"/></way>
<way id="16"><nd ref="1"/><nd ref="99"/><tag k="highway" v="service"/></way>
<way id="17"><nd ref="1"/><nd ref="5"/><tag k="natural" v="water"/></way>
<relation id="21"><member type="way" ref="14" role="outer"/><member type="way" ref="15" role="outer"/>
 <tag k="type" v="multipolygon"/><tag k="natural" v="water"/></relation>
</osm>"""


class OfflineOSMImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "map.osm").write_text(XML, encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def snapshot(self):
        return normalise(self.root / "map.osm", "test-osm", "ufa",
                         "https://www.openstreetmap.org/", "2026-11-12T00:00:00Z")

    def test_identifiers_types_and_untouched_wgs84_coordinates(self):
        snap = self.snapshot()
        self.assertEqual(snap["crs"], "EPSG:4326")
        self.assertEqual(snap["license"], "ODbL 1.0")
        by_id = {f["osm_id"]: f for f in snap["features"]}
        self.assertEqual(set(by_id), {"way/11", "way/12", "relation/21/outer/0"})
        self.assertEqual(by_id["way/11"]["coordinates"], [[55.95, 54.73], [55.955, 54.73]])
        self.assertEqual((by_id["way/11"]["kind"], by_id["way/11"]["subtype"]), ("road", "residential"))
        self.assertEqual(by_id["way/11"]["name"], "Тестовая улица")
        self.assertEqual(by_id["way/12"]["geometry"], "polygon")
        ring = by_id["relation/21/outer/0"]["coordinates"]
        self.assertEqual(ring[0], ring[-1])
        self.assertEqual(len(ring), 5)

    def test_incomplete_objects_are_skipped_not_invented(self):
        snap = self.snapshot()
        self.assertEqual(snap["skipped"]["incomplete_geometry"], 1)  # way 16: node outside extract
        self.assertEqual(snap["skipped"]["open_area"], 1)            # way 17: unclosed water area
        self.assertEqual(snap["feature_counts"], {"road": 1, "building": 1, "water": 1})

    def test_no_contributor_metadata_is_stored(self):
        self.assertNotIn("someone", json.dumps(self.snapshot(), ensure_ascii=False))

    def test_convert_writes_source_snapshot(self):
        convert(self.root / "map.osm", self.root / "geodata", "test-osm", "ufa",
                "https://www.openstreetmap.org/", "2026-11-12T00:00:00Z")
        stored = json.loads((self.root / "geodata" / "sources" / "test-osm.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["source_id"], "test-osm")

    def test_source_and_bounds_required(self):
        with self.assertRaises(ValueError):
            normalise(self.root / "map.osm", "test-osm", "ufa", "", "2026-11-12")
        with self.assertRaises(ValueError):
            normalise(self.root / "map.osm", "Bad ID", "ufa", "https://www.openstreetmap.org/", "2026-11-12")
        (self.root / "empty.osm").write_text('<osm version="0.6"/>')
        with self.assertRaises(ValueError):
            normalise(self.root / "empty.osm", "test-osm", "ufa", "https://www.openstreetmap.org/", "2026-11-12")

    def test_classification(self):
        self.assertEqual(classify({"building": "no"}), None)
        self.assertEqual(classify({"highway": "primary"}), ("road", "primary"))
        self.assertEqual(classify({"waterway": "river"}), ("water", "river"))
        self.assertEqual(classify({"landuse": "meadow"}), ("farmland", "meadow"))


if __name__ == "__main__":
    unittest.main()
