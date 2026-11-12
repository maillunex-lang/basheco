"""LEGACY local projection, kept only to convert pre-stage-1 data.

Before stage 1 every settlement had its own equirectangular origin. The world
now uses one EPSG:32640 grid (world_grid.py / world_projection.py). Nothing new
may be built on LocalProjection: it exists so that world_compat.py can map old
settlement-local plot coordinates back to WGS84 exactly as the old client drew them.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import cos, radians, degrees, isfinite

EARTH_RADIUS_M = 6378137.0

@dataclass(frozen=True)
class LocalProjection:
    origin_lon: float
    origin_lat: float

    def __post_init__(self):
        if not (-180 <= self.origin_lon <= 180 and -85 <= self.origin_lat <= 85):
            raise ValueError("Invalid origin")

    def project(self, lon: float, lat: float) -> tuple[float, float]:
        if not (isfinite(lon) and isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError("Invalid coordinates")
        # Equirectangular local tangent approximation, suitable for small settlements.
        # For large cities and regions use a documented projected CRS instead.
        x = EARTH_RADIUS_M * radians(lon - self.origin_lon) * cos(radians(self.origin_lat))
        y = -EARTH_RADIUS_M * radians(lat - self.origin_lat)
        return x, y

    def unproject(self, x: float, y: float) -> tuple[float, float]:
        """Exact inverse of project(): local metres -> WGS84 lon, lat."""
        if not (isfinite(x) and isfinite(y)):
            raise ValueError("Invalid local coordinates")
        lon = self.origin_lon + degrees(x / (EARTH_RADIUS_M * cos(radians(self.origin_lat))))
        lat = self.origin_lat - degrees(y / EARTH_RADIUS_M)
        return lon, lat


def clip_segment(a: tuple[float, float], b: tuple[float, float],
                 bbox: tuple[float, float, float, float]):
    """Liang-Barsky clipping. Includes segments crossing the viewport from outside."""
    xmin, ymin, xmax, ymax = bbox
    if xmin >= xmax or ymin >= ymax:
        raise ValueError("Invalid bbox")
    dx, dy = b[0] - a[0], b[1] - a[1]
    p = (-dx, dx, -dy, dy)
    q = (a[0] - xmin, xmax - a[0], a[1] - ymin, ymax - a[1])
    u0, u1 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if pi == 0:
            if qi < 0:
                return None
            continue
        t = qi / pi
        if pi < 0:
            u0 = max(u0, t)
        else:
            u1 = min(u1, t)
        if u0 > u1:
            return None
    return (a[0] + u0 * dx, a[1] + u0 * dy), (a[0] + u1 * dx, a[1] + u1 * dy)


def clipped_linestring(points, bbox):
    """Return visible independent segments; never join disjoint clipped parts."""
    return [clipped for a, b in zip(points, points[1:])
            if (clipped := clip_segment(a, b, bbox)) is not None]


def clip_polygon(points: list[tuple[float, float]],
                 bbox: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    """Sutherland-Hodgman polygon clipping against a finite rectangular extract."""
    xmin, ymin, xmax, ymax = bbox
    if xmin >= xmax or ymin >= ymax:
        raise ValueError('Invalid bbox')
    polygon = list(points)
    if len(polygon) > 1 and polygon[0] == polygon[-1]:
        polygon.pop()
    for axis, boundary, keep_greater in ((0,xmin,True),(0,xmax,False),
                                          (1,ymin,True),(1,ymax,False)):
        if not polygon:
            break
        result = []
        previous = polygon[-1]
        def inside(point):
            return point[axis] >= boundary if keep_greater else point[axis] <= boundary
        for current in polygon:
            curr_inside = inside(current)
            prev_inside = inside(previous)
            if curr_inside != prev_inside:
                delta = current[axis] - previous[axis]
                if delta:
                    t = (boundary - previous[axis]) / delta
                    result.append((previous[0] + t * (current[0]-previous[0]),
                                   previous[1] + t * (current[1]-previous[1])))
            if curr_inside:
                result.append(current)
            previous = current
        polygon = result
    if len(polygon) < 3:
        return []
    return polygon + [polygon[0]]
