import unittest
from basheco.geodata import LocalProjection, clip_segment, clipped_linestring, clip_polygon

class GeoDataTests(unittest.TestCase):
    def test_origin_and_distance(self):
        geo = LocalProjection(55.971, 54.738)
        self.assertEqual(geo.project(55.971, 54.738), (0, 0))
        east, north = geo.project(55.972, 54.738)
        self.assertTrue(60 < east < 70)
        self.assertAlmostEqual(north, 0)
        x, y = geo.project(55.971, 54.739)
        self.assertAlmostEqual(x, 0)
        self.assertTrue(-115 < y < -110)

    def test_crossing_road_not_discarded(self):
        segment = clip_segment((-100, 50), (200, 50), (0, 0, 100, 100))
        self.assertEqual(segment, ((0, 50), (100, 50)))

    def test_outside_road_discarded(self):
        self.assertIsNone(clip_segment((-100, -100), (-20, -20), (0, 0, 100, 100)))

    def test_disconnected_segments_not_joined(self):
        result = clipped_linestring([(-20, 10), (20, 10), (20, -20), (80, -20), (80, 20)], (0, 0, 100, 100))
        self.assertEqual(len(result), 3)

    def test_invalid_coordinates(self):
        with self.assertRaises(ValueError):
            LocalProjection(400, 55)
        with self.assertRaises(ValueError):
            LocalProjection(55, 55).project(float('nan'), 55)

    def test_polygon_clipping_limits_large_forests(self):
        result = clip_polygon([(-100,-100),(200,-100),(200,200),(-100,200),(-100,-100)],(0,0,100,100))
        self.assertGreaterEqual(len(result), 4)
        self.assertTrue(all(0 <= x <= 100 and 0 <= y <= 100 for x,y in result))
        self.assertEqual(result[0], result[-1])

    def test_polygon_fully_outside(self):
        self.assertEqual(clip_polygon([(-10,-10),(-5,-10),(-5,-5),(-10,-10)],(0,0,100,100)), [])
