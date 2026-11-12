"""Offline placement tests: no database, no running server changes."""
import unittest
from basheco.placement import PlacementError, preview, rotated_cells


class PlacementTests(unittest.TestCase):
    def test_rotations_and_roundtrip(self):
        shape = [(0, 0), (1, 0), (0, 1)]
        self.assertEqual(rotated_cells(shape, 0), frozenset(shape))
        self.assertEqual(rotated_cells(shape, 90), {(1, 0), (1, 1), (0, 0)})
        self.assertEqual(rotated_cells(shape, 180), {(1, 1), (0, 1), (1, 0)})
        self.assertEqual(rotated_cells(shape, 270), {(0, 1), (0, 0), (1, 1)})

    def test_world_bounds_and_overlap(self):
        shape = [(0, 0), (1, 0)]
        result = preview(shape, 90, (71469, -1012286), (71469, -1012286, 71474, -1012281))
        self.assertEqual(result.bounds, (71469, -1012286, 71470, -1012284))
        with self.assertRaisesRegex(PlacementError, "outside"):
            preview(shape, 0, (71473, -1012286), (71469, -1012286, 71474, -1012281))
        with self.assertRaisesRegex(PlacementError, "overlaps"):
            preview(shape, 0, (1, 1), (0, 0, 5, 5), [(2, 1)])

    def test_reject_bad_shapes_and_rotation(self):
        for shape, rotation in [([], 0), ([(0, 0), (0, 0)], 0), ([(0, -1)], 0), ([(64, 0)], 0), ([(0, 0)], 45), ([(0, 0)], True)]:
            with self.subTest(shape=shape, rotation=rotation):
                with self.assertRaises(PlacementError):
                    rotated_cells(shape, rotation)
        with self.assertRaises(PlacementError):
            preview([(0, 0)], 0, (0, 0), (0, 0, 0, 1))


if __name__ == "__main__":
    unittest.main()