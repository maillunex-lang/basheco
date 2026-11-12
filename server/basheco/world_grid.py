"""World grid index from EPSG:32640 projected metres.

One global origin (E=0,N=0) for all settlements. Screen Y increases south.
WGS84 -> EPSG:32640 conversion must be performed by a real CRS transformer,
never by the old per-settlement LocalProjection approximation.
"""
from __future__ import annotations
from math import floor, isfinite

CELL_METRES = 6
CHUNK_CELLS = 64
CRS = "EPSG:32640"
WORLD_ORIGIN_EASTING = 0
WORLD_ORIGIN_NORTHING = 0


def metres_to_cell(easting: float, northing: float) -> tuple[int, int]:
    if not (isfinite(easting) and isfinite(northing)):
        raise ValueError("Non-finite projected coordinates")
    return (floor((easting - WORLD_ORIGIN_EASTING) / CELL_METRES),
            floor((WORLD_ORIGIN_NORTHING - northing) / CELL_METRES))


def cell_to_metre_corner(cell_x: int, cell_y: int) -> tuple[int, int]:
    if type(cell_x) is not int or type(cell_y) is not int:
        raise ValueError("Integer cell coordinates required")
    return (WORLD_ORIGIN_EASTING + cell_x * CELL_METRES,
            WORLD_ORIGIN_NORTHING - cell_y * CELL_METRES)


def cell_to_chunk(cell_x: int, cell_y: int) -> tuple[int, int]:
    if type(cell_x) is not int or type(cell_y) is not int:
        raise ValueError("Integer cell coordinates required")
    return cell_x // CHUNK_CELLS, cell_y // CHUNK_CELLS
