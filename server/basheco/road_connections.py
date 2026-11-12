"""Deterministic four-neighbour road connections on the shared cell grid.

Existing OSM roads are a separate transport layer: do not silently replace or
snap their irregular geometry to these game roads.
"""
from __future__ import annotations

N = 1
E = 2
S = 4
W = 8
OFFSETS = ((0, -1, N), (1, 0, E), (0, 1, S), (-1, 0, W))


def road_mask(x: int, y: int, road_cells: set[tuple[int, int]]) -> int:
    """Bit mask of directly adjacent road cells, independent of placement order."""
    return sum(bit for dx, dy, bit in OFFSETS if (x + dx, y + dy) in road_cells)


def road_shape(mask: int) -> str:
    """Rendering hint for a straight, corner, T, crossing, or endpoint tile."""
    if type(mask) is not int or mask < 0 or mask > 15:
        raise ValueError("Invalid road mask")
    count = mask.bit_count()
    if count == 0:
        return "isolated"
    if count == 1:
        return "end"
    if count == 3:
        return "t_junction"
    if count == 4:
        return "crossroads"
    return "straight" if mask in (N | S, E | W) else "corner"


def affected_roads(changed: set[tuple[int, int]],
                   all_roads: set[tuple[int, int]]) -> dict[tuple[int, int], int]:
    """Recompute changed cells and immediate neighbours on add/remove."""
    candidates = set(changed)
    for x, y in changed:
        candidates.update((x + dx, y + dy) for dx, dy, _ in OFFSETS)
    return {cell: road_mask(*cell, all_roads) for cell in candidates if cell in all_roads}
