"""Synthetic DEM tests: steep slopes block; flat and missing remain unknown."""
import tempfile
import unittest
from pathlib import Path

from basheco.dem_source import dem_evidence


class DemSourceTests(unittest.TestCase):
    def test_missing_dem(self):
        with self.assertRaises((FileNotFoundError, RuntimeError)):
            dem_evidence({(100, -100)}, "/nonexistent/dem.tif")

    def test_steep_flat_nodata_and_geographic_rejection(self):
        try:
            import numpy as np
            import rasterio
            from rasterio.transform import from_origin
        except ImportError:
            self.skipTest("Optional rasterio/numpy unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic_dem.tif"
            # E=600..720, N=600..480, each pixel 10m.
            data = np.zeros((12, 12), dtype="float32")
            for col in range(12):
                data[:, col] = col * 10  # 45-degree slope
            with rasterio.open(path, "w", driver="GTiff", width=12, height=12,
                               count=1, dtype="float32", crs="EPSG:32640",
                               transform=from_origin(600, 600, 10, 10),
                               nodata=-9999) as dst:
                dst.write(data, 1)
            # 100,-95 => (603,573), interior; 102,-95 => (615,573).
            evidence = dem_evidence({(102, -95), (150, -95)}, path,
                                    source="synthetic", source_version="1")
            self.assertEqual(evidence["layers"]["terrain"]["102,-95"], "blocked")
            self.assertEqual(evidence["layers"]["terrain"]["150,-95"], "unknown")
            self.assertGreater(evidence["slope_degrees"]["102,-95"], 40)
            with rasterio.open(path, "w", driver="GTiff", width=12, height=12,
                               count=1, dtype="float32", crs="EPSG:4326",
                               transform=from_origin(55, 55, .001, .001),
                               nodata=-9999) as dst:
                dst.write(data, 1)
            with self.assertRaises(ValueError):
                dem_evidence({(102, -95)}, path, source="synthetic", source_version="1")

    def test_flat_is_not_clear(self):
        try:
            import numpy as np
            import rasterio
            from rasterio.transform import from_origin
        except ImportError:
            self.skipTest("Optional rasterio/numpy unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "flat.tif"
            with rasterio.open(path, "w", driver="GTiff", width=12, height=12,
                               count=1, dtype="float32", crs="EPSG:32640",
                               transform=from_origin(600, 600, 10, 10),
                               nodata=-9999) as dst:
                dst.write(np.full((12, 12), 100, dtype="float32"), 1)
            evidence = dem_evidence({(102, -95)}, path,
                                    source="synthetic", source_version="1")
            self.assertEqual(evidence["layers"]["terrain"]["102,-95"], "unknown")
            self.assertEqual(evidence["slope_degrees"]["102,-95"], 0)