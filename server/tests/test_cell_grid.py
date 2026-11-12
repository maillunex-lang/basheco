"""Pure geometry regression tests; no database required."""
import unittest
from basheco.cell_grid import (
    CELL_SIZE_M, normalize_mask, rotate_cells, occupied_cells,
    check_placement, rectangle_mask,
)


class CellGridTests(unittest.TestCase):
    def test_scale_and_catalog_rectangles(self):
        self.assertEqual(CELL_SIZE_M, 6)
        for w, h in ((1, 1), (2, 1), (2, 2), (3, 3), (4, 5), (5, 5)):
            self.assertEqual(len(occupied_cells(rectangle_mask(w, h), -10, 20)), w * h)

    def test_rotation_and_translation(self):
        mask = [[1, 1, 1], [1, 0, 0]]
        original = normalize_mask(mask)
        self.assertEqual(rotate_cells(original, 0), original)
        self.assertEqual(rotate_cells(rotate_cells(original, 90), 90),
                         rotate_cells(original, 180))
        rotated = original
        for _ in range(4):
            rotated = rotate_cells(rotated, 90)
        self.assertEqual(rotated, original)
        self.assertEqual(len(occupied_cells(mask, 100, -20, 270)), 4)

    def test_hollow_mask_and_parcel(self):
        footprint = occupied_cells([[1, 1], [1, 0]], 2, 3)
        parcel = frozenset((x, y) for x in range(2, 4) for y in range(3, 5))
        self.assertTrue(check_placement(footprint, parcel, frozenset())["allowed"])
        self.assertFalse(check_placement(footprint, parcel, frozenset({(2, 3)}))["allowed"])
        self.assertFalse(check_placement(footprint, frozenset({(2, 3)}), frozenset())["allowed"])
        self.assertTrue(check_placement(footprint, parcel, frozenset({(3, 4)}))["allowed"])

    def test_invalid_catalog_and_rotation(self):
        for mask in ([], [[0]], [[1, 0], [1]], [[True]], [[2]], [[1] * 65]):
            with self.assertRaises(ValueError):
                normalize_mask(mask)
        with self.assertRaises(ValueError):
            occupied_cells([[1]], 0, 0, 45)
        with self.assertRaises(ValueError):
            occupied_cells([[1]], 1.5, 0)
        with self.assertRaises(ValueError):
            rectangle_mask(0, 1)


if __name__ == "__main__":
    unittest.main()
