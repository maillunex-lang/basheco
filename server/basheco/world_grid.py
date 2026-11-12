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


# --- Stage 1 additions: one versioned spec shared by server, exporter and client ---
GRID_VERSION = "basheco-grid/1"
SOURCE_CRS = "EPSG:4326"
CHUNK_METRES = CELL_METRES * CHUNK_CELLS  # 384 m


def metres_to_chunk(easting: float, northing: float) -> tuple[int, int]:
    return cell_to_chunk(*metres_to_cell(easting, northing))


def chunk_origin_cell(chunk_x: int, chunk_y: int) -> tuple[int, int]:
    """North-west cell of a chunk (smallest cell_x, smallest cell_y)."""
    if type(chunk_x) is not int or type(chunk_y) is not int:
        raise ValueError("Integer chunk coordinates required")
    return chunk_x * CHUNK_CELLS, chunk_y * CHUNK_CELLS


def chunk_bounds_metres(chunk_x: int, chunk_y: int) -> tuple[int, int, int, int]:
    """(east_min, north_min, east_max, north_max) of a chunk in EPSG:32640.

    cell_y grows to the south, therefore chunk_y*CHUNK_CELLS is the northern edge.
    """
    cell_x, cell_y = chunk_origin_cell(chunk_x, chunk_y)
    east_min, north_max = cell_to_metre_corner(cell_x, cell_y)
    return east_min, north_max - CHUNK_METRES, east_min + CHUNK_METRES, north_max


def grid_spec() -> dict:
    """Machine-readable contract. Clients must refuse to mix other versions."""
    return {
        "grid_version": GRID_VERSION, "crs": CRS, "source_crs": SOURCE_CRS,
        "cell_metres": CELL_METRES, "chunk_cells": CHUNK_CELLS,
        "origin_easting": WORLD_ORIGIN_EASTING, "origin_northing": WORLD_ORIGIN_NORTHING,
        "cell_x": "floor((E - origin_easting) / cell_metres)",
        "cell_y": "floor((origin_northing - N) / cell_metres)",
        "chunk": "floor(cell / chunk_cells)",
    }
