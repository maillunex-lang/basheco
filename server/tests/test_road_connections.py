import unittest
from basheco.road_connections import (
    N, E, S, W, road_mask, road_shape, affected_roads,
)


class RoadConnectionTests(unittest.TestCase):
    def test_shapes_and_direction(self):
        roads = {(0, 0), (1, 0), (2, 0)}
        self.assertEqual(road_mask(1, 0, roads), E | W)
        self.assertEqual(road_shape(road_mask(1, 0, roads)), "straight")
        roads.add((1, -1))
        self.assertEqual(road_mask(1, 0, roads), N | E | W)
        self.assertEqual(road_shape(road_mask(1, 0, roads)), "t_junction")
        roads.add((1, 1))
        self.assertEqual(road_shape(road_mask(1, 0, roads)), "crossroads")
        roads.remove((1, -1))
        roads.remove((1, 1))
        roads.remove((2, 0))
        self.assertEqual(road_shape(road_mask(1, 0, roads)), "end")

    def test_corner_and_no_diagonal_connection(self):
        roads = {(0, 0), (1, 0), (0, 1), (1, 1)}
        self.assertEqual(road_shape(road_mask(0, 0, roads)), "corner")
        self.assertEqual(road_mask(0, 0, {(0, 0), (1, 1)}), 0)

    def test_neighbours_update_on_add_and_remove(self):
        roads = {(0, 0), (1, 0)}
        self.assertEqual(affected_roads({(1, 0)}, roads)[(0, 0)], E)
        roads.remove((1, 0))
        self.assertEqual(affected_roads({(1, 0)}, roads)[(0, 0)], 0)

    def test_negative_coordinates(self):
        self.assertEqual(road_mask(-5, -5, {(-5, -5), (-6, -5)}), W)

    def test_bad_mask(self):
        with self.assertRaises(ValueError):
            road_shape(16)


if __name__ == "__main__":
    unittest.main()
