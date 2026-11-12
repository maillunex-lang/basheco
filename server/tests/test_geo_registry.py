"""Administrative geography registry (stage 1.2): committed data must be consistent
and exactly what the committed source snapshots produce."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from basheco.geo_registry import (
    DATASET_VERSION, SIMPLIFY_METRES, assemble_rings, build, point_in_rings, polygon_area,
    ring_points, settlement_type, shoelace, simplify,
)
from basheco.world_projection import lonlat_to_metres

ADMIN = Path(__file__).resolve().parents[1] / "geodata" / "admin"


class PureGeometryTests(unittest.TestCase):
    def test_rings_are_joined_in_any_way_direction(self):
        ways = {"1": [[0, 0], [1, 0]], "2": [[1, 1], [1, 0]], "3": [[1, 1], [0, 1], [0, 0]],
                "9": [[5, 5], [6, 5], [6, 6], [5, 5]]}
        rings = assemble_rings([["1", "outer"], ["3", "outer"], ["2", "outer"], ["9", "inner"]], ways)
        self.assertEqual([r["role"] for r in rings], ["outer", "inner"])
        self.assertEqual(ring_points(rings[0], ways), [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]])
        self.assertEqual(shoelace(ring_points(rings[0], ways)[:-1]), 1.0)

    def test_open_boundary_is_rejected(self):
        with self.assertRaises(ValueError):
            assemble_rings([["1", "outer"]], {"1": [[0, 0], [1, 0]]})

    def test_point_in_polygon_with_hole(self):
        outer = [[0, 0], [10, 0], [10, 10], [0, 10]]
        hole = [[4, 4], [6, 4], [6, 6], [4, 6]]
        self.assertTrue(point_in_rings((1, 1), [outer, hole]))
        self.assertFalse(point_in_rings((5, 5), [outer, hole]))
        self.assertFalse(point_in_rings((11, 5), [outer, hole]))

    def test_simplification_keeps_end_points_and_tolerance(self):
        line = [[0, 0], [10, 1], [20, 0], [30, 50], [40, 0]]
        self.assertEqual(simplify(line, 5), [[0, 0], [20, 0], [30, 50], [40, 0]])
        self.assertEqual(simplify(line, 0), line)
        self.assertEqual(simplify(line, 1000), [[0, 0], [40, 0]])

    def test_settlement_types(self):
        self.assertEqual(settlement_type(["деревня", "административно-территориальная единица России"]), "деревня")
        self.assertEqual(settlement_type(["город России", "посёлок городского типа"]), "город")
        self.assertEqual(settlement_type(["посёлок городского типа"]), "рабочий посёлок")
        self.assertEqual(settlement_type(["посёлок станции"]), "посёлок")
        self.assertIsNone(settlement_type(["кордон"]))


@unittest.skipUnless(ADMIN.is_dir(), "Repository geodata not available in this image")
class CommittedRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        load = lambda name: json.loads((ADMIN / name).read_text(encoding="utf-8"))
        cls.version = load("dataset_version.json")
        cls.region = load("region.json")
        cls.municipalities = load("municipalities.json")["municipalities"]
        cls.registry = load("id_registry.json")["ids"]
        cls.issues = load("issues.json")
        cls.sources = load("sources.json")["sources"]
        cls.legacy = load("legacy_ids.json")["ids"]
        cls.ways = {lod: load(f"boundaries/ways_{lod}.json") for lod in SIMPLIFY_METRES}
        cls.source_ways = load("sources/osm_admin.json")["ways"]
        cls.settlements = []
        for item in cls.municipalities:
            data = load(f"settlements/{item['id']}.json")
            assert data["municipality_id"] == item["id"]
            cls.settlements.extend(data["settlements"])

    def test_63_municipalities_54_districts_9_urban_okrugs(self):
        types = [m["type"] for m in self.municipalities]
        self.assertEqual(len(types), 63)
        self.assertEqual(types.count("муниципальный район"), 54)
        self.assertEqual(types.count("городской округ"), 9)
        self.assertEqual(self.version["counts"]["municipalities_by_type"],
                         {"городской округ": 9, "муниципальный район": 54})
        for item in self.municipalities:
            self.assertRegex(item["oktmo"], r"^80[67]\d{2}000$")
            self.assertTrue(item["name"] and item["admin_centre"] and item["osm_relation"])
            self.assertEqual(item["oktmo"][2] == "7", item["type"] == "городской округ")

    def test_identifiers_are_unique_and_registered(self):
        ids = [m["id"] for m in self.municipalities] + [s["id"] for s in self.settlements] + [self.region["id"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), set(self.registry))
        codes = [s["oktmo"] for s in self.settlements]
        self.assertEqual(len(codes), len(set(codes)))
        for entry in self.settlements:
            self.assertEqual(entry["id"], "S" + self.registry[entry["id"]]["oktmo_at_issue"])
            self.assertRegex(entry["oktmo"], r"^80\d{9}$")

    def test_every_settlement_belongs_to_one_existing_municipality(self):
        by_id = {m["id"]: m for m in self.municipalities}
        counted = {}
        for entry in self.settlements:
            owner = by_id[entry["municipality_id"]]
            self.assertEqual(entry["oktmo"][:5], owner["oktmo"][:5])
            self.assertTrue(entry["name"])
            self.assertNotRegex(entry["name"], r"^Q\d+$|\(|поселение")
            self.assertIn(entry["type"], {"город", "рабочий посёлок", "село", "деревня", "посёлок", "хутор",
                                          "населённый пункт"})
            counted[owner["id"]] = counted.get(owner["id"], 0) + 1
        for item in self.municipalities:
            self.assertEqual(counted.get(item["id"], 0), item["settlement_count"])
            self.assertGreaterEqual(item["settlement_count"], 1)
        self.assertEqual(len(self.settlements), self.version["counts"]["settlements"])
        self.assertEqual(sum(s["type"] == "город" for s in self.settlements), 21)

    def test_coordinates_agree_with_boundaries_and_world_grid(self):
        rings_by_id = {}
        for item in self.municipalities:
            rings_by_id[item["id"]] = [ring_points(r, self.source_ways) for r in item["rings"]]
        inside = outside = 0
        for entry in self.settlements:
            if entry["lon"] is None:
                self.assertEqual(entry["coordinate_status"], "missing")
                self.assertIsNone(entry["coordinate_source"])
                self.assertIsNone(entry["world_cell"])
                continue
            self.assertTrue(52.5 < entry["lon"] < 60.5 and 51.0 < entry["lat"] < 56.8)
            east, north = lonlat_to_metres(entry["lon"], entry["lat"])
            self.assertAlmostEqual(east, entry["easting"], delta=0.06)
            self.assertAlmostEqual(north, entry["northing"], delta=0.06)
            self.assertEqual(entry["world_cell"], [int(east // 6), int(-north // 6)])
            self.assertEqual(entry["coordinate_source"], "wikidata:P625")
            really_inside = point_in_rings((entry["lon"], entry["lat"]), rings_by_id[entry["municipality_id"]])
            self.assertEqual(entry["coordinate_status"],
                             "inside_municipality" if really_inside else "outside_municipality")
            inside += really_inside
            outside += not really_inside
        self.assertEqual(inside, self.version["counts"]["coordinates_confirmed"])
        self.assertEqual(outside, self.issues["counts"].get("outside_boundary", 0))
        missing = sum(s["lon"] is None for s in self.settlements)
        self.assertEqual(missing, self.issues["counts"].get("coordinates_rejected", 0)
                         + self.issues["counts"].get("no_coordinates", 0))
        self.assertGreater(inside / len(self.settlements), 0.99)

    def test_boundaries_have_no_gaps_or_overlaps_at_every_level(self):
        for lod, data in self.ways.items():
            ways = data["ways"]
            self.assertEqual((data["crs"], data["dataset_version"]), ("EPSG:32640", DATASET_VERSION))
            region_area = polygon_area(self.region["rings"], ways)
            municipal_area = sum(polygon_area(m["rings"], ways) for m in self.municipalities)
            # Neighbours share the very same simplified ways, so the areas add up exactly.
            self.assertAlmostEqual(municipal_area / region_area, 1.0, places=9, msg=lod)
            self.assertTrue(142000 < region_area / 1e6 < 143500, region_area)
            for item in self.municipalities:
                for ring in item["rings"]:
                    points = ring_points(ring, ways)
                    self.assertEqual(points[0], points[-1])
                    self.assertGreaterEqual(len(points), 5)
                self.assertGreater(polygon_area(item["rings"], ways), 1e6)

    def test_simplified_levels_are_small_enough_for_a_phone(self):
        levels = self.version["boundaries"]["levels"]
        self.assertLess(levels["overview"]["points"], levels["detail"]["points"])
        self.assertLess(levels["detail"]["points"], levels["source"]["points"])
        self.assertLess(levels["overview"]["points"], 15000)
        self.assertLess((ADMIN / "boundaries" / "ways_overview.json").stat().st_size, 300_000)

    def test_every_population_figure_has_year_and_reference(self):
        with_population = [s for s in self.settlements if s["population"]]
        self.assertEqual(len(with_population), self.version["counts"]["with_population"])
        for entry in with_population:
            population = entry["population"]
            self.assertIsInstance(population["value"], int)
            self.assertTrue(1900 < population["year"] <= 2026)
            self.assertTrue(population["source"] or population["source_url"])

    def test_sources_and_honest_verification_flags(self):
        by_id = {s["id"]: s for s in self.sources}
        self.assertEqual(by_id["osm-admin-boundaries"]["license"], "ODbL 1.0")
        self.assertEqual(by_id["wikidata-units"]["license"], "CC0 1.0")
        self.assertIsNone(by_id["oktmo-rosstat"]["retrieved_utc"])
        self.assertFalse(self.version["verification"]["official_oktmo_file_compared"])
        self.assertEqual(self.version["target_reference_date"], "2026-01-01")

    def test_legacy_text_ids_are_mapped(self):
        by_id = {s["id"]: s for s in self.settlements}
        self.assertEqual(by_id[self.legacy["ufa"]]["name"], "Уфа")
        self.assertEqual(by_id[self.legacy["mikhailovka"]]["name"], "Михайловка")
        self.assertEqual(by_id[self.legacy["mikhailovka"]]["municipality_id"], "M80652000")

    def test_rebuild_reproduces_files_and_keeps_issued_identifiers(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            shutil.copytree(ADMIN / "sources", work / "sources")
            for name in ("id_registry.json", "sources.json"):
                shutil.copy(ADMIN / name, work / name)
            build(work)
            committed = sorted(p.relative_to(ADMIN).as_posix() for p in ADMIN.rglob("*.json"))
            fresh = sorted(p.relative_to(work).as_posix() for p in work.rglob("*.json"))
            self.assertEqual(fresh, committed)
            for name in fresh:
                self.assertEqual((work / name).read_bytes(), (ADMIN / name).read_bytes(), name)
        with tempfile.TemporaryDirectory() as temp:
            # An identifier issued earlier survives even if today's rule would name it differently.
            work = Path(temp)
            shutil.copytree(ADMIN / "sources", work / "sources")
            registry = {"schema": "basheco.geo_id_registry/1", "ids": {
                "S-OLD-UFA": {"oktmo_at_issue": "80701000001", "issued_in": "earlier"}}}
            (work / "id_registry.json").write_text(json.dumps(registry), encoding="utf-8")
            build(work)
            ufa = json.loads((work / "settlements" / "M80701000.json").read_text(encoding="utf-8"))["settlements"]
            self.assertEqual(next(s for s in ufa if s["oktmo"] == "80701000001")["id"], "S-OLD-UFA")
            self.assertEqual(json.loads((work / "legacy_ids.json").read_text(encoding="utf-8"))["ids"]["ufa"],
                             "S-OLD-UFA")


if __name__ == "__main__":
    unittest.main()
