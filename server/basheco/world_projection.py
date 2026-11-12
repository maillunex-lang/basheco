"""Canonical WGS84 -> BASHECO global grid conversion.

Coordinates are always longitude, latitude (EPSG:4326) on input and
EPSG:32640 projected metres internally. Never use settlement-local origins.
"""
from __future__ import annotations

from math import isfinite
from functools import lru_cache

from basheco.world_grid import CRS, metres_to_cell, cell_to_chunk


@lru_cache(maxsize=1)
def _forward_transformer():
    from pyproj import Transformer
    return Transformer.from_crs("EPSG:4326", CRS, always_xy=True)


@lru_cache(maxsize=1)
def _inverse_transformer():
    from pyproj import Transformer
    return Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)


def lonlat_to_metres(lon: float, lat: float) -> tuple[float, float]:
    if not (isfinite(lon) and isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError("Invalid WGS84 coordinates")
    east, north = _forward_transformer().transform(lon, lat, errcheck=True)
    if not (isfinite(east) and isfinite(north)):
        raise ValueError("Projection failed")
    return east, north


def metres_to_lonlat(east: float, north: float) -> tuple[float, float]:
    if not (isfinite(east) and isfinite(north)):
        raise ValueError("Invalid projected coordinates")
    return _inverse_transformer().transform(east, north, errcheck=True)


def lonlat_to_world_cell(lon: float, lat: float) -> tuple[int, int]:
    return metres_to_cell(*lonlat_to_metres(lon, lat))


def lonlat_to_world_chunk(lon: float, lat: float) -> tuple[int, int]:
    return cell_to_chunk(*lonlat_to_world_cell(lon, lat))
