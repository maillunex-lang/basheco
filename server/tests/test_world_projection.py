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

    def test_epsg_32640_definition(self):
        # UTM zone 40N: central meridian 57 E, false easting 500 km, k0 0.9996.
        east, north = lonlat_to_metres(57.0, 0.0)
        self.assertAlmostEqual(east, 500000.0, places=6)
        self.assertAlmostEqual(north, 0.0, places=6)
        _, north_1deg = lonlat_to_metres(57.0, 1.0)
        self.assertAlmostEqual(north_1deg, 110574.3886 * 0.9996, delta=0.01)

    def test_matches_closed_form_series_used_by_the_client(self):
        # The Godot client implements the same Krueger series (world_grid.gd).
        # Agreement with PROJ must be far below one 6 m cell everywhere in the republic.
        for lon, lat in ((55.972, 54.7386), (55.8925, 54.8055), (53.2, 52.0),
                         (59.9, 56.5), (57.0, 54.0), (54.0, 55.5), (58.3, 51.6)):
            east, north = lonlat_to_metres(lon, lat)
            series_east, series_north = krueger_forward(lon, lat)
            self.assertAlmostEqual(east, series_east, delta=0.001)
            self.assertAlmostEqual(north, series_north, delta=0.001)
            back_lon, back_lat = krueger_inverse(east, north)
            self.assertAlmostEqual(back_lon, lon, delta=2e-8)
            self.assertAlmostEqual(back_lat, lat, delta=2e-8)

    def test_real_relative_position_of_ufa_and_mikhailovka(self):
        # Independent ellipsoidal check: grid distance equals geodesic distance
        # times the UTM scale factor, and Mikhailovka lies north-west of the Ufa extract.
        from pyproj import Geod
        ufa, mikhailovka = (55.972, 54.7386), (55.8925, 54.8055)
        azimuth, _, geodesic = Geod(ellps="WGS84").inv(*ufa, *mikhailovka)
        ue, un = lonlat_to_metres(*ufa)
        me, mn = lonlat_to_metres(*mikhailovka)
        grid = ((ue - me) ** 2 + (un - mn) ** 2) ** 0.5
        self.assertAlmostEqual(geodesic, 9035.4, delta=1.0)
        self.assertAlmostEqual(grid / geodesic, 0.99966, delta=0.0001)
        self.assertLess(me, ue)
        self.assertGreater(mn, un)
        self.assertTrue(-40 < azimuth < -30)
        ucx, ucy = lonlat_to_world_cell(*ufa)
        mcx, mcy = lonlat_to_world_cell(*mikhailovka)
        self.assertEqual((ucx - mcx, ucy - mcy), (833, 1254))


def _krueger_constants():
    from math import sqrt
    a, f = 6378137.0, 1 / 298.257223563
    n = f / (2 - f)
    return (a / (1 + n) * (1 + n * n / 4 + n ** 4 / 64), n, sqrt(f * (2 - f)))


def krueger_forward(lon, lat):
    from math import radians, sin, cos, sinh, cosh, atan, atanh, sqrt
    big_a, n, e = _krueger_constants()
    alpha = (n / 2 - 2 * n * n / 3 + 5 * n ** 3 / 16, 13 * n * n / 48 - 3 * n ** 3 / 5, 61 * n ** 3 / 240)
    phi, lam = radians(lat), radians(lon - 57.0)
    t = sinh(atanh(sin(phi)) - e * atanh(e * sin(phi)))
    xi = atan(t / cos(lam))
    eta = atanh(sin(lam) / sqrt(1 + t * t))
    east = 500000.0 + 0.9996 * big_a * (eta + sum(alpha[j] * cos(2 * (j + 1) * xi) * sinh(2 * (j + 1) * eta) for j in range(3)))
    north = 0.9996 * big_a * (xi + sum(alpha[j] * sin(2 * (j + 1) * xi) * cosh(2 * (j + 1) * eta) for j in range(3)))
    return east, north


def krueger_inverse(east, north):
    from math import degrees, sin, cos, sinh, cosh, atan, asin
    big_a, n, _ = _krueger_constants()
    beta = (n / 2 - 2 * n * n / 3 + 37 * n ** 3 / 96, n * n / 48 + n ** 3 / 15, 17 * n ** 3 / 480)
    delta = (2 * n - 2 * n * n / 3 - 2 * n ** 3, 7 * n * n / 3 - 8 * n ** 3 / 5, 56 * n ** 3 / 15)
    xi, eta = north / (0.9996 * big_a), (east - 500000.0) / (0.9996 * big_a)
    xi1 = xi - sum(beta[j] * sin(2 * (j + 1) * xi) * cosh(2 * (j + 1) * eta) for j in range(3))
    eta1 = eta - sum(beta[j] * cos(2 * (j + 1) * xi) * sinh(2 * (j + 1) * eta) for j in range(3))
    chi = asin(sin(xi1) / cosh(eta1))
    lat = chi + sum(delta[j] * sin(2 * (j + 1) * chi) for j in range(3))
    return 57.0 + degrees(atan(sinh(eta1) / cos(xi1))), degrees(lat)


if __name__ == "__main__":
    unittest.main()
