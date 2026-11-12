"""The committed world atlas must be exactly what the sources produce."""
import json
import math
import tempfile
import unittest
from pathlib import Path

from basheco.world_atlas import build, split_line, polygon_home
from basheco.world_grid import CHUNK_METRES, chunk_bounds_metres, metres_to_chunk
from basheco.world_projection import lonlat_to_metres, metres_to_lonlat

ROOT = Path(__file__).resolve().parents[2]
GEODATA = ROOT / "server" / "geodata"
ATLAS = ROOT / "client" / "data" / "world"


class LineSplitTests(unittest.TestCase):
    def test_cut_points_are_shared_by_both_neighbours(self):
        pieces = split_line([(100.0, -100.0), (900.0, -500.0)])
        self.assertEqual([chunk for chunk, _ in pieces], [(0, 0), (1, 0), (1, 1), (2, 1)])
        for (_, left), (_, right) in zip(pieces, pieces[1:]):
            self.assertEqual(left[-1], right[0])
        self.assertEqual(pieces[0][1][0], (100.0, -100.0))
        self.assertEqual(pieces[-1][1][-1], (900.0, -500.0))
        self.assertEqual(pieces[0][1][-1][0], 384.0)

    def test_negative_coordinates_and_vertices_on_borders(self):
        pieces = split_line([(-10.0, 10.0), (0.0, 0.0), (10.0, -10.0)])
        self.assertEqual([chunk for chunk, _ in pieces], [(-1, -1), (0, 0)])
        self.assertEqual(pieces[0][1], [(-10.0, 10.0), (0.0, 0.0)])

    def test_line_inside_one_chunk_is_not_cut(self):
        points = [(1.0, -1.0), (50.0, -70.0), (300.0, -383.0)]
        self.assertEqual(split_line(points), [((0, 0), points)])

    def test_polygon_home_and_large_detection(self):
        small = [(10.0, -10.0), (30.0, -10.0), (30.0, -30.0), (10.0, -10.0)]
        self.assertEqual(polygon_home(small), ((0, 0), True))
        crossing = [(380.0, -10.0), (500.0, -10.0), (500.0, -30.0), (380.0, -10.0)]
        self.assertEqual(polygon_home(crossing), ((1, 0), True))
        huge = [(0.0, 0.0), (2000.0, 0.0), (2000.0, -2000.0), (0.0, 0.0)]
        self.assertFalse(polygon_home(huge)[1])


@unittest.skipUnless(GEODATA.is_dir() and ATLAS.is_dir(), "Repository geodata not available in this image")
class CommittedAtlasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ATLAS / "manifest.json").read_text(encoding="utf-8"))
        cls.chunks = {}
        for cx, cy, _ in cls.manifest["chunks"]:
            cls.chunks[cx, cy] = json.loads((ATLAS / "chunks" / f"chunk_{cx}_{cy}.json").read_text(encoding="utf-8"))
        cls.large = json.loads((ATLAS / "large.json").read_text(encoding="utf-8"))["features"]
        cls.sources = {p.stem: json.loads(p.read_text(encoding="utf-8"))
                       for p in (GEODATA / "sources").glob("*.json")}

    def all_features(self):
        for chunk in self.chunks.values():
            yield from chunk["features"]
        yield from self.large

    def test_rebuild_reproduces_committed_atlas(self):
        with tempfile.TemporaryDirectory() as temp:
            build(GEODATA, Path(temp))
            fresh = sorted(p.relative_to(temp).as_posix() for p in Path(temp).rglob("*.json"))
            committed = sorted(p.relative_to(ATLAS).as_posix() for p in ATLAS.rglob("*.json"))
            self.assertEqual(fresh, committed)
            for name in fresh:
                self.assertEqual((Path(temp) / name).read_bytes(), (ATLAS / name).read_bytes(), name)

    def test_one_crs_one_origin_and_version(self):
        m = self.manifest
        self.assertEqual((m["schema"], m["crs"], m["source_crs"]), ("basheco.world_atlas/2", "EPSG:32640", "EPSG:4326"))
        self.assertEqual((m["cell_metres"], m["chunk_cells"], m["origin_easting"], m["origin_northing"]), (6, 64, 0, 0))
        for chunk in self.chunks.values():
            self.assertEqual((chunk["schema"], chunk["crs"], chunk["grid_version"]),
                             ("basheco.world_chunk/2", "EPSG:32640", m["grid_version"]))
        text = json.dumps(m)
        for forbidden in ("origin_lon", "origin_lat", "local_equirectangular", "origin_tile"):
            self.assertNotIn(forbidden, text)

    def test_no_geographic_object_is_duplicated(self):
        uids = [f["uid"] for f in self.all_features()]
        self.assertEqual(len(uids), len(set(uids)))
        self.assertEqual(len(uids), self.manifest["exported_piece_count"])
        polygons = [f["uid"] for f in self.all_features() if f["geom"] == "polygon"]
        lines = {f["uid"].split("#")[0] for f in self.all_features() if f["geom"] == "line"}
        total = sum(len(s["features"]) for s in self.sources.values())
        self.assertEqual(len(polygons) + len(lines), total)
        self.assertEqual(total, self.manifest["source_object_count"])

    def test_chunk_contents_lie_inside_their_chunk(self):
        for (cx, cy), chunk in self.chunks.items():
            self.assertEqual(chunk["chunk"], [cx, cy])
            east_min, north_min, east_max, north_max = chunk_bounds_metres(cx, cy)
            self.assertEqual(chunk["bounds_m"], [east_min, north_min, east_max, north_max])
            for feature in chunk["features"]:
                xs = [p[0] for p in feature["points"]]
                ys = [p[1] for p in feature["points"]]
                if feature["geom"] == "line":
                    self.assertTrue(east_min <= min(xs) and max(xs) <= east_max, feature["uid"])
                    self.assertTrue(north_min <= min(ys) and max(ys) <= north_max, feature["uid"])
                else:
                    self.assertEqual(metres_to_chunk((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2), (cx, cy))
                    self.assertTrue(min(xs) >= east_min - CHUNK_METRES and max(xs) <= east_max + CHUNK_METRES)
                    self.assertTrue(min(ys) >= north_min - CHUNK_METRES and max(ys) <= north_max + CHUNK_METRES)

    def test_roads_keep_every_source_vertex_and_join_without_gaps(self):
        pieces = {}
        for feature in self.all_features():
            if feature["geom"] == "line":
                base, index = feature["uid"].split("#")
                pieces.setdefault(base, {})[int(index)] = feature["points"]
        checked = 0
        for source_id, source in self.sources.items():
            for item in source["features"]:
                if item["geometry"] != "line":
                    continue
                parts = pieces[f"{source_id}:{item['osm_id']}"]
                ordered = [parts[i] for i in range(len(parts))]
                for left, right in zip(ordered, ordered[1:]):
                    self.assertEqual(left[-1], right[0])  # identical cut point: seamless
                joined = [tuple(p) for part in ordered for p in part]
                expected = [tuple(round(v, 2) for v in lonlat_to_metres(lon, lat)) for lon, lat in item["coordinates"]]
                position = 0
                for vertex in expected:  # every real vertex survives, in order
                    position = joined.index(vertex, position)
                self.assertEqual(joined[0], expected[0])
                self.assertEqual(joined[-1], expected[-1])
                for vertex in joined:    # added points are only cuts on chunk borders
                    if vertex not in expected:
                        self.assertTrue(vertex[0] % CHUNK_METRES == 0 or vertex[1] % CHUNK_METRES == 0)
                checked += 1
        self.assertGreater(checked, 100)

    def test_buildings_and_areas_match_source_coordinates(self):
        exported = {f["uid"]: f for f in self.all_features() if f["geom"] == "polygon"}
        worst = 0.0
        for source_id, source in self.sources.items():
            for item in source["features"]:
                if item["geometry"] != "polygon":
                    continue
                feature = exported[f"{source_id}:{item['osm_id']}"]
                self.assertEqual((feature["kind"], feature["subtype"], feature["osm_id"]),
                                 (item["kind"], item["subtype"], item["osm_id"]))
                self.assertEqual(len(feature["points"]), len(item["coordinates"]))
                for (east, north), (lon, lat) in zip(feature["points"], item["coordinates"]):
                    back_lon, back_lat = metres_to_lonlat(east, north)
                    worst = max(worst, abs(back_lon - lon) * 111320 * math.cos(math.radians(lat)),
                                abs(back_lat - lat) * 110540)
        self.assertLess(worst, 0.011)  # only the 1 cm rounding of stored metres

    def test_settlements_share_the_grid_at_their_real_distance(self):
        by_id = {s["id"]: s for s in self.manifest["settlements"]}
        ufa, mikhailovka = by_id["ufa"], by_id["mikhailovka"]
        self.assertEqual(ufa["focus_cell"], [72302, -1011032])
        self.assertEqual(mikhailovka["focus_cell"], [71469, -1012286])
        self.assertEqual(ufa["focus_chunk"], [1129, -15798])
        self.assertEqual(mikhailovka["focus_chunk"], [1116, -15817])
        distance = math.dist(ufa["focus_m"], mikhailovka["focus_m"])
        self.assertAlmostEqual(distance, 9032.3, delta=0.5)
        for settlement in by_id.values():
            self.assertNotIn("origin", " ".join(settlement.keys()))

    def test_control_points_are_consistent(self):
        points = json.loads((ATLAS / "control_points.json").read_text(encoding="utf-8"))["points"]
        self.assertGreaterEqual(len(points), 9)
        for point in points:
            east, north = lonlat_to_metres(point["lon"], point["lat"])
            self.assertAlmostEqual(east, point["easting"], delta=1e-6)
            self.assertAlmostEqual(north, point["northing"], delta=1e-6)
            self.assertEqual(point["cell"], [math.floor(east / 6), math.floor(-north / 6)])
            self.assertEqual(point["chunk"], [point["cell"][0] // 64, point["cell"][1] // 64])
        self.assertTrue(any(p["cell"][1] < 0 for p in points))

    def test_provenance_is_kept(self):
        for source in self.manifest["sources"]:
            self.assertTrue(source["source_url"].startswith("https://api.openstreetmap.org/"))
            self.assertEqual(source["license"], "ODbL 1.0")
            self.assertTrue(source["downloaded_utc"])
        for feature in self.all_features():
            self.assertRegex(feature["osm_id"], r"^(way|relation)/\d+")
            self.assertIn(feature["source"], self.sources)
        self.assertEqual(self.manifest["coverage"], "partial")


if __name__ == "__main__":
    unittest.main()
