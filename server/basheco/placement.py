"""Pure, fail-closed grid placement geometry for a future transactional API.

No land rights, cost, or build permission is implied by a geometrically valid
candidate. The active construction endpoint is intentionally unchanged.
"""
from dataclasses import dataclass
from typing import Iterable


class PlacementError(ValueError):
    pass


@dataclass(frozen=True)
class Placement:
    cells: frozenset[tuple[int, int]]
    rotation: int
    bounds: tuple[int, int, int, int]


def rotated_cells(footprint: Iterable[tuple[int, int]], rotation: int) -> frozenset[tuple[int, int]]:
    """Rotate local occupied cells clockwise in screen/grid coordinates."""
    if type(rotation) is not int or rotation not in (0, 90, 180, 270):
        raise PlacementError("Rotation must be 0, 90, 180 or 270")
    raw = list(footprint)
    if not raw or len(raw) > 4096:
        raise PlacementError("Footprint must contain 1..4096 cells")
    if any(len(cell) != 2 or any(type(n) is not int or n < 0 or n >= 64 for n in cell) for cell in raw):
        raise PlacementError("Footprint cells must be nonnegative integers below 64")
    if len(set(raw)) != len(raw):
        raise PlacementError("Duplicate footprint cells")
    width = max(x for x, _ in raw) + 1
    height = max(y for _, y in raw) + 1
    if rotation == 0:
        return frozenset(raw)
    if rotation == 90:
        return frozenset((height - 1 - y, x) for x, y in raw)
    if rotation == 180:
        return frozenset((width - 1 - x, height - 1 - y) for x, y in raw)
    return frozenset((y, width - 1 - x) for x, y in raw)


def preview(footprint: Iterable[tuple[int, int]], rotation: int, origin: tuple[int, int],
            plot_bounds: tuple[int, int, int, int], occupied: Iterable[tuple[int, int]] = ()) -> Placement:
    """Check half-open parcel bounds and occupied grid cells, without side effects.

    This is a geometry check ONLY. Callers must separately verify authenticated
    ownership, legal/game land rights, zoning, geographic masks, versioned costs,
    road access, and transactional global occupancy before allowing construction.
    """
    if len(origin) != 2 or any(type(n) is not int for n in origin):
        raise PlacementError("Origin must be integer world cells")
    if len(plot_bounds) != 4 or any(type(n) is not int for n in plot_bounds):
        raise PlacementError("Plot bounds must be integer world cells")
    left, top, right, bottom = plot_bounds
    if left >= right or top >= bottom:
        raise PlacementError("Invalid plot bounds")
    local = rotated_cells(footprint, rotation)
    cells = frozenset((origin[0] + x, origin[1] + y) for x, y in local)
    if any(x < left or x >= right or y < top or y >= bottom for x, y in cells):
        raise PlacementError("Footprint extends outside plot")
    if not cells.isdisjoint(set(occupied)):
        raise PlacementError("Footprint overlaps occupied cells")
    xs = [x for x, _ in cells]
    ys = [y for _, y in cells]
    return Placement(cells, rotation, (min(xs), min(ys), max(xs) + 1, max(ys) + 1))

def catalog_footprint(raw: object) -> list[tuple[int, int]]:
    """Decode the versioned catalog JSON footprint, refusing malformed entries."""
    if not isinstance(raw, list) or not 1 <= len(raw) <= 4096:
        raise PlacementError("Invalid catalog footprint")
    if any(not isinstance(cell, list) or len(cell) != 2 for cell in raw):
        raise PlacementError("Invalid catalog footprint cell")
    cells = [tuple(cell) for cell in raw]
    rotated_cells(cells, 0)
    return cells