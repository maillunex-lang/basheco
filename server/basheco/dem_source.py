"""Conservative local DEM slope screening for generated BASHECO footprints.

Slope is computed over the native DEM pixels, not invented 6m elevations.
An uncertain, coarse or missing DEM never yields a construction clearance.
"""
from __future__ import annotations

from math import atan, degrees, hypot, isfinite
from pathlib import Path

from basheco.land_constraints import SCHEMA
from basheco.world_grid import CELL_METRES, cell_to_metre_corner


def dem_evidence(cells: set[tuple[int, int]], raster_path: str | Path,
                 *, slope_limit_degrees: float = 15.0,
                 source: str = "", source_version: str = "") -> dict:
    """Return blocked steep cells, otherwise unknown pending high-resolution data.

    Use a 3x3 Horn slope estimate at the pixel containing the cell centre.
    Raster must be in a projected metric CRS with metre vertical units.
    Do not use this to certify 6m footprints with 30m+ DEM.
    """
    if not (isfinite(slope_limit_degrees) and 0 < slope_limit_degrees < 90):
        raise ValueError("Invalid slope limit")
    try:
        import rasterio
        from rasterio.warp import transform
    except ImportError as exc:
        raise RuntimeError("DEM processing requires rasterio") from exc
    path = Path(raster_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    terrain = {}
    slopes = {}
    with rasterio.open(path) as ds:
        if ds.count != 1 or ds.crs is None or ds.nodata is None:
            raise ValueError("DEM requires one georeferenced band and nodata")
        if ds.crs.is_geographic:
            raise ValueError("DEM must use projected metric horizontal coordinates")
        units = (ds.crs.linear_units or "").lower()
        if units not in ("metre", "meter", "metres", "meters"):

            raise ValueError("DEM horizontal CRS must use metres")
        # Rotation/skew is unsupported in this conservative implementation.
        if ds.transform.b or ds.transform.d:
            raise ValueError("Rotated DEM is unsupported")
        px, py = abs(ds.transform.a), abs(ds.transform.e)
        if px <= 0 or py <= 0:
            raise ValueError("Invalid DEM pixel size")
        for x, y in sorted(cells):
            key = f"{x},{y}"
            terrain[key] = "unknown"
            east, north = cell_to_metre_corner(x, y)
            xs, ys = transform("EPSG:32640", ds.crs,
                               [east + CELL_METRES / 2], [north - CELL_METRES / 2])
            row, col = ds.index(xs[0], ys[0])
            if row < 1 or col < 1 or row >= ds.height - 1 or col >= ds.width - 1:
                continue
            from rasterio.windows import Window
            values = ds.read(1, window=Window(col - 1, row - 1, 3, 3), masked=True)
            import numpy as np
            if np.ma.getmaskarray(values).any() or not np.isfinite(values.data).all():
                continue
            a, b, c = map(float, values.data[0])
            d, e, f = map(float, values.data[1])
            g, h, i = map(float, values.data[2])
            dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * px)
            dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * py)
            slope = degrees(atan(hypot(dzdx, dzdy)))
            slopes[key] = round(slope, 3)
            if slope > slope_limit_degrees:
                terrain[key] = "blocked"
            # Even low-slope DEM values cannot certify 6m cells: unknown.
    return {"schema": SCHEMA,
            "source": source, "source_version": source_version,
            "layers": {"terrain": terrain},
            "slope_degrees": slopes,
            "slope_limit_degrees": slope_limit_degrees,
            "pixel_size_metres": [px, py],
            "limitations": ["Native DEM slope does not resolve individual 6m cells",
                            "Vertical units/datum and source provenance require independent verification",
                            "Low measured slope is never an automatic build permit"]}