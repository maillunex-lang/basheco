"""Pure, deterministic cell-footprint geometry. No database or CRS assumptions.

Coordinates are integer cells in a global 6-metre grid. The caller is responsible
for converting projected real-world coordinates into these cells.
"""
from __future__ import annotations

CELL_SIZE_M = 6
ROTATIONS = (0, 90, 180, 270)
MAX_FOOTPRINT_CELLS = 4096


def normalize_mask(mask: list[list[int]]) -> frozenset[tuple[int, int]]:
    """Validate and normalize a catalog mask (rows top to bottom)."""
    if not mask or len(mask) > 64 or not isinstance(mask[0], list):
        raise ValueError("Invalid footprint height")
    width = len(mask[0])
    if width < 1 or width > 64 or any(not isinstance(row, list) or len(row) != width for row in mask):
        raise ValueError("Footprint must be rectangular")
    cells = set()
    for y, row in enumerate(mask):
        for x, value in enumerate(row):
            if type(value) is not int or value not in (0, 1):
                raise ValueError("Mask values must be 0 or 1")
            if value:
                cells.add((x, y))
    if not cells or len(cells) > MAX_FOOTPRINT_CELLS:
        raise ValueError("Footprint must occupy at least one cell")
    return frozenset(cells)


def rotate_cells(cells: frozenset[tuple[int, int]], rotation: int) -> frozenset[tuple[int, int]]:
    """Clockwise rotation in screen coordinates (x right, y down)."""
    if rotation not in ROTATIONS:
        raise ValueError("Rotation must be 0, 90, 180 or 270")
    if not cells:
        raise ValueError("Empty footprint")
    rotated = set()
    for x, y in cells:
        if rotation == 0:
            rotated.add((x, y))
        elif rotation == 90:
            rotated.add((-y, x))
        elif rotation == 180:
            rotated.add((-x, -y))
        else:
            rotated.add((y, -x))
    left = min(x for x, _ in rotated)
    top = min(y for _, y in rotated)
    return frozenset((x - left, y - top) for x, y in rotated)


def occupied_cells(mask: list[list[int]], x: int, y: int, rotation: int = 0) -> frozenset[tuple[int, int]]:
    if type(x) is not int or type(y) is not int:
        raise ValueError("Cell coordinates must be integers")
    return frozenset((x + dx, y + dy) for dx, dy in rotate_cells(normalize_mask(mask), rotation))


def check_placement(occupied: frozenset[tuple[int, int]],
                    parcel: frozenset[tuple[int, int]],
                    blocked: frozenset[tuple[int, int]]) -> dict:
    """Client-preview helper only; server must recheck transactionally."""
    outside = occupied - parcel
    conflicts = occupied & blocked
    return {"allowed": not outside and not conflicts,
            "outside": sorted(outside), "conflicts": sorted(conflicts)}


def rectangle_mask(width: int, height: int) -> list[list[int]]:
    if type(width) is not int or type(height) is not int or not (1 <= width <= 64 and 1 <= height <= 64):
        raise ValueError("Invalid dimensions")
    return [[1] * width for _ in range(height)]
