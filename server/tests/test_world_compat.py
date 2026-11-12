"""Legacy settlement-local plot coordinates -> single world grid (pure functions)."""
import math
import unittest

from basheco.geodata import LocalProjection
from basheco.world_compat import LegacyAnchor, legacy_tile_to_lonlat, legacy_tile_to_world_cell
from basheco.world_grid import cell_to_metre_corner
from basheco.world_projection import lonlat_to_metres, lonlat_to_world_cell, metres_to_lonlat

UFA = LegacyAnchor(55.971999999999994, 54.7386, 25, 25, 6)
MIKHAILOVKA = LegacyAnchor(55.8925, 54.805499999999995, 150, 180, 6)


class LegacyAnchorTests(unittest.TestCase):
    def test_local_projection_inverse_is_exact(self):
        projection = LocalProjection(55.8925, 54.8055)
        for lon, lat in ((55.881, 54.797), (55.904, 54.814), (55.8925, 54.8055)):
            back = projection.unproject(*projection.project(lon, lat))
            self.assertAlmostEqual(back[0], lon, places=12)
            self.assertAlmostEqual(back[1], lat, places=12)

    def test_anchor_tile_is_the_documented_wgs84_point(self):
        self.assertEqual(legacy_tile_to_lonlat(UFA, 25, 25), (55.971999999999994, 54.7386))
        cell_x, cell_y, _ = legacy_tile_to_world_cell(UFA, 25, 25)
        self.assertLessEqual(abs(cell_x - 72302), 1)
        self.assertLessEqual(abs(cell_y + 1011032), 1)
        mx, my, _ = legacy_tile_to_world_cell(MIKHAILOVKA, 150, 180)
        self.assertLessEqual(abs(mx - 71469), 1)
        self.assertLessEqual(abs(my + 1012286), 1)

    def test_legacy_indices_are_never_reused_as_world_cells(self):
        for anchor in (UFA, MIKHAILOVKA):
            for tile in ((0, 0), (2, 2), (4090, 4090)):
                cell_x, cell_y, _ = legacy_tile_to_world_cell(anchor, *tile)
                self.assertNotEqual((cell_x, cell_y), tile)
                self.assertGreater(cell_x, 60000)
                self.assertLess(cell_y, -900000)

    def test_snapped_position_stays_within_half_a_cell_of_where_it_was_drawn(self):
        worst = 0.0
        for anchor in (UFA, MIKHAILOVKA):
            for tile_x in range(0, 4091, 409):
                for tile_y in range(0, 4091, 409):
                    cell_x, cell_y, offset = legacy_tile_to_world_cell(anchor, tile_x, tile_y)
                    east, north = cell_to_metre_corner(cell_x, cell_y)
                    lon, lat = metres_to_lonlat(east, north)
                    old_lon, old_lat = legacy_tile_to_lonlat(anchor, tile_x, tile_y)
                    ground = math.hypot((lon - old_lon) * 111320 * math.cos(math.radians(lat)),
                                        (lat - old_lat) * 110540)
                    self.assertLess(ground, 4.3)
                    self.assertAlmostEqual(ground, offset, delta=0.05)
                    worst = max(worst, offset)
        self.assertLess(worst, 4.2427)

    def test_same_ground_point_gets_one_cell_from_either_settlement(self):
        # A tile of the Mikhailovka sector that lies on the Ufa anchor point must
        # land on the same world cell as the Ufa sector's own anchor tile.
        east, north = lonlat_to_metres(*legacy_tile_to_lonlat(UFA, 25, 25))
        projection = LocalProjection(MIKHAILOVKA.origin_lon, MIKHAILOVKA.origin_lat)
        local_x, local_y = projection.project(*metres_to_lonlat(east, north))
        tile_x = MIKHAILOVKA.origin_tile_x + local_x / 6
        tile_y = MIKHAILOVKA.origin_tile_y + local_y / 6
        self.assertTrue(0 < tile_x < 4096 and 0 < tile_y < 4096)  # sectors really overlap
        via_ufa = legacy_tile_to_world_cell(UFA, 25, 25)[:2]
        lon, lat = legacy_tile_to_lonlat(MIKHAILOVKA, tile_x, tile_y)
        self.assertEqual(lonlat_to_world_cell(lon, lat), lonlat_to_world_cell(*legacy_tile_to_lonlat(UFA, 25, 25)))
        self.assertLessEqual(abs(via_ufa[0] - lonlat_to_world_cell(lon, lat)[0]), 1)

    def test_neighbouring_tiles_keep_their_order(self):
        base = legacy_tile_to_world_cell(UFA, 200, 200)
        east = legacy_tile_to_world_cell(UFA, 210, 200)
        south = legacy_tile_to_world_cell(UFA, 200, 210)
        self.assertEqual(east[0] - base[0], 10)
        self.assertEqual(south[1] - base[1], 10)
        self.assertLessEqual(abs(east[1] - base[1]), 1)   # ~0.8 deg grid convergence
        self.assertLessEqual(abs(south[0] - base[0]), 1)


if __name__ == "__main__":
    unittest.main()
