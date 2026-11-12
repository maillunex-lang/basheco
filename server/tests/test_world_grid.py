import unittest
from basheco.world_grid import (
    CRS, CELL_METRES, metres_to_cell, cell_to_metre_corner, cell_to_chunk,
)


class GlobalGridTests(unittest.TestCase):
    def test_shared_projection_and_scale(self):
        self.assertEqual(CRS, "EPSG:32640")
        self.assertEqual(CELL_METRES, 6)
        self.assertEqual(metres_to_cell(600000, 6060000), (100000, -1010000))
        self.assertEqual(cell_to_metre_corner(100000, -1010000), (600000, 6060000))

    def test_negative_and_boundary_cells(self):
        self.assertEqual(metres_to_cell(-0.1, 0.1), (-1, -1))
        self.assertEqual(metres_to_cell(5.999, -5.999), (0, 0))
        self.assertEqual(metres_to_cell(6, -6), (1, 1))
        self.assertEqual(cell_to_chunk(-1, -1), (-1, -1))
        self.assertEqual(cell_to_chunk(64, 64), (1, 1))

    def test_reject_non_finite(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.assertRaises(ValueError):
                metres_to_cell(value, 0)


if __name__ == "__main__":
    unittest.main()


class ChunkGeometryTests(unittest.TestCase):
    def test_chunk_is_64_cells_of_6_metres(self):
        from basheco.world_grid import CHUNK_CELLS, CHUNK_METRES, chunk_bounds_metres, chunk_origin_cell
        self.assertEqual((CHUNK_CELLS, CHUNK_METRES), (64, 384))
        self.assertEqual(chunk_origin_cell(-1, -1), (-64, -64))
        self.assertEqual(chunk_bounds_metres(0, 0), (0, -384, 384, 0))
        self.assertEqual(chunk_bounds_metres(-1, -1), (-384, 0, 0, 384))

    def test_every_cell_of_a_chunk_maps_back_to_it(self):
        from basheco.world_grid import chunk_bounds_metres, chunk_origin_cell, metres_to_chunk
        for chunk in ((1129, -15798), (-3, 2), (0, 0), (-1, -1)):
            x0, y0 = chunk_origin_cell(*chunk)
            for dx, dy in ((0, 0), (63, 0), (0, 63), (63, 63)):
                self.assertEqual(cell_to_chunk(x0 + dx, y0 + dy), chunk)
            self.assertNotEqual(cell_to_chunk(x0 + 64, y0), chunk)
            self.assertNotEqual(cell_to_chunk(x0 - 1, y0), chunk)
            east_min, north_min, east_max, north_max = chunk_bounds_metres(*chunk)
            self.assertEqual(metres_to_chunk(east_min, north_max), chunk)
            self.assertEqual(metres_to_chunk(east_max - 0.001, north_min + 0.001), chunk)
            self.assertNotEqual(metres_to_chunk(east_max, north_max), chunk)

    def test_cell_round_trip_with_negative_indices(self):
        for cell in ((-5, -7), (72302, -1011032), (0, 0), (-1, 1)):
            east, north = cell_to_metre_corner(*cell)
            self.assertEqual(metres_to_cell(east + 0.01, north - 0.01), cell)

    def test_spec_is_versioned(self):
        from basheco.world_grid import grid_spec
        spec = grid_spec()
        self.assertEqual((spec["grid_version"], spec["crs"], spec["source_crs"]),
                         ("basheco-grid/1", "EPSG:32640", "EPSG:4326"))
        self.assertEqual((spec["cell_metres"], spec["chunk_cells"]), (6, 64))
        self.assertEqual((spec["origin_easting"], spec["origin_northing"]), (0, 0))
