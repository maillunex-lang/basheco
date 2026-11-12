"""ESA WorldCover raster screening tests, with a synthetic raster fixture."""
import tempfile
import unittest
from pathlib import Path

from basheco.land_constraints import assess_cells
from basheco.worldcover_source import worldcover_evidence


class WorldCoverTests(unittest.TestCase):
    def test_missing_raster_fails(self):
        with self.assertRaises((RuntimeError, FileNotFoundError)):
            worldcover_evidence({(100, -100)}, "/nonexistent/basheco-worldcover.tif")

    def test_water_and_unknown_from_real_geotiff_reader(self):
        try:
            import numpy as np
            import rasterio
            from rasterio.transform import from_origin
        except ImportError:
            self.skipTest("Optional geodata dependencies not installed")
        # A synthetic 10m GeoTIFF, NOT actual ESA data.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "worldcover_fixture.tif"
            with rasterio.open(path, "w", driver="GTiff", width=4, height=4,
                               count=1, dtype="uint8", crs="EPSG:32640",
                               transform=from_origin(600, 600, 10, 10),
                               nodata=0) as dst:
                data = np.full((4, 4), 50, dtype="uint8")
                data[0, 0] = 80
                dst.write(data, 1)
            evidence = worldcover_evidence({(100, -100), (105, -105)}, path)
            self.assertEqual(evidence["layers"]["water"]["100,-100"], "blocked")
            self.assertEqual(evidence["layers"]["water"]["105,-105"], "unknown")
            decision = assess_cells({(100, -100), (105, -105)}, evidence)
            self.assertFalse(decision["safe_to_build"])
            self.assertEqual(decision["decision"], "blocked")