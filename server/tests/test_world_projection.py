import unittest
from basheco.world_projection import (
    lonlat_to_metres, metres_to_lonlat, lonlat_to_world_cell, lonlat_to_world_chunk,
)
from basheco.world_grid import cell_to_chunk


class WorldProjectionTests(unittest.TestCase):
    def test_round_trip_real_settlements(self):
        # Approximate geographic reference points, not parcel boundaries.
        for lon, lat in ((55.97, 54.74), (55.91, 54.82)):
            east, north = lonlat_to_metres(lon, lat)
            lon2, lat2 = metres_to_lonlat(east, north)
            self.assertAlmostEqual(lon, lon2, places=7)
            self.assertAlmostEqual(lat, lat2, places=7)
            cell = lonlat_to_world_cell(lon, lat)
            self.assertEqual(cell_to_chunk(*cell), lonlat_to_world_chunk(lon, lat))

    def test_no_settlement_specific_offsets(self):
        # One WGS84 point always maps to the same world cell.
        self.assertEqual(lonlat_to_world_cell(55.97, 54.74),
                         lonlat_to_world_cell(55.97, 54.74))

    def test_invalid_coordinates(self):
        for lon, lat in ((181, 55), (56, 91), (float("nan"), 55)):
            with self.assertRaises(ValueError):
                lonlat_to_metres(lon, lat)


if __name__ == "__main__":
    unittest.main()
