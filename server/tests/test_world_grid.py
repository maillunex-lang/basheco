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
