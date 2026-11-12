"""Deterministic, local geodata projection and clipping for settlement backgrounds.

Input geometry is WGS84 lon/lat, output coordinates are metres relative to a
location-specific origin. Game plots remain separate and are not inferred from OSM.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import cos, radians, pi, isfinite

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
