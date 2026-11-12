"""Offline ESA WorldCover GeoTIFF sampler for BASHECO's 6m world grid.

Requires rasterio, installed only in a separate geodata processing environment.
This is *land-cover screening*, never a legal construction permit. A WorldCover
pixel is ~10m and cannot resolve every 6m game cell or narrow watercourse.
"""
from __future__ import annotations

from pathlib import Path

from basheco.land_constraints import SCHEMA
from basheco.world_grid import cell_to_metre_corner

# ESA WorldCover 2021 v200, Product User Manual table of map classes.
WORLD_COVER_WATER = 80
WORLD_COVER_UNKNOWN = 0


def worldcover_evidence(cells: set[tuple[int, int]], raster_path: str | Path) -> dict:
    """Screen water from a local, versioned ESA WorldCover 2021 raster.

    For every 6m game cell, examine every intersecting pixel using conservative
    all_touched rasterization, not only the cell centre. A non-water land-cover
    pixel means *no water detected in this raster*, not confirmed dry land.
    """
    try:
        import rasterio
        from rasterio.features import geometry_mask
        from rasterio.windows import from_bounds, transform as window_transform
        from rasterio.warp import transform_bounds
    except ImportError as exc:
        raise RuntimeError("Geo processing requires rasterio") from exc

    path = Path(raster_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    water = {}
    with rasterio.open(path) as dataset:
        if dataset.count != 1 or dataset.crs is None or dataset.nodata is None:
            raise ValueError("Expected single-band georeferenced WorldCover raster with nodata")
        for x, y in sorted(cells):
            east, north = cell_to_metre_corner(x, y)
            left, bottom, right, top = transform_bounds(
                "EPSG:32640", dataset.crs, east, north - 6, east + 6, north,
                densify_pts=5)
            # Only read pixels overlapping the requested footprint.
            from math import ceil, floor
            window = from_bounds(left, bottom, right, top, dataset.transform)
            row0 = max(0, floor(window.row_off) - 1)
            col0 = max(0, floor(window.col_off) - 1)
            row1 = min(dataset.height, ceil(window.row_off + window.height) + 1)
            col1 = min(dataset.width, ceil(window.col_off + window.width) + 1)
            key = f"{x},{y}"
            if row0 >= row1 or col0 >= col1:
                water[key] = "unknown"
                continue
            from rasterio.windows import Window
            window = Window(col0, row0, col1 - col0, row1 - row0)
            values = dataset.read(1, window=window, masked=True)
            from rasterio.warp import transform_geom
            polygon = {"type": "Polygon", "coordinates": [[
                [east, north], [east + 6, north], [east + 6, north - 6],
                [east, north - 6], [east, north]]]}
            polygon = transform_geom("EPSG:32640", dataset.crs, polygon,
                                     precision=-1)
            touched = geometry_mask([polygon], out_shape=values.shape,
                                    transform=window_transform(window, dataset.transform),
                                    invert=True, all_touched=True)
            import numpy as np
            valid = touched & ~np.ma.getmaskarray(values)
            if not valid.any():
                water[key] = "unknown"
            elif ((values.data == WORLD_COVER_WATER) & valid).any():
                water[key] = "blocked"
            else:
                # The absence of mapped water is not a verified 'clear'.
                water[key] = "unknown"
    return {"schema": SCHEMA,
            "source": "ESA WorldCover 2021 v200 (land-cover screening only)",
            "source_version": "2021-v200",
            "layers": {"water": water},
            "raster_path": str(path),
            "limitations": ["10m pixels do not prove safety of 6m cells",
                            "Narrow streams and seasonal flooding may be missed",
                            "No terrain, protected-area or land-rights evidence"]}