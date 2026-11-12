"""Transition layer: legacy settlement-local plots -> the single world grid.

Before stage 1 a plot was addressed as (sector_id, tile_x, tile_y) in a private
0..4096 grid per settlement. Those numbers are kept forever as history, but they
are never interpreted as world cells. Instead each plot gets an explicit world
position derived from how the old client actually drew it:

  legacy tile corner -> local metres around the sector anchor -> WGS84 (exact
  inverse of the old projection) -> EPSG:32640 (pyproj) -> nearest world cell corner.

The old local grid was aligned to true north, the world grid to UTM grid north
(about 0.8 degrees apart near Ufa), so a plot is snapped as a whole: its
north-west corner moves by at most half a cell diagonal (4.25 m) and it keeps
its width and height in cells. The applied shift is stored per plot.

If two plots would claim the same world cell after snapping, the database
exclusion constraint rejects the second one. It then stays unmapped (NULL) and
is reported: positions are never guessed.

Usage: python -m basheco.world_compat      (idempotent, only touches unmapped plots)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from math import floor, hypot

from basheco.geodata import LocalProjection
from basheco.world_grid import CELL_METRES, GRID_VERSION
from basheco.world_projection import lonlat_to_metres

CELL_SOURCE = "legacy_anchor_v1"
MAX_SNAP_OFFSET_M = CELL_METRES * 2 ** 0.5 / 2 + 0.001


@dataclass(frozen=True)
class LegacyAnchor:
    origin_lon: float
    origin_lat: float
    origin_tile_x: float
    origin_tile_y: float
    metres_per_tile: float

    @classmethod
    def from_row(cls, row) -> "LegacyAnchor":
        if row["projection"] != "local_equirectangular_metres":
            raise ValueError("Unsupported legacy projection")
        return cls(row["origin_lon"], row["origin_lat"], row["origin_tile_x"],
                   row["origin_tile_y"], row["metres_per_tile"])


def legacy_tile_to_lonlat(anchor: LegacyAnchor, tile_x: float, tile_y: float) -> tuple[float, float]:
    projection = LocalProjection(anchor.origin_lon, anchor.origin_lat)
    return projection.unproject((tile_x - anchor.origin_tile_x) * anchor.metres_per_tile,
                                (tile_y - anchor.origin_tile_y) * anchor.metres_per_tile)


def legacy_tile_to_world_cell(anchor: LegacyAnchor, tile_x: int, tile_y: int) -> tuple[int, int, float]:
    """World cell whose north-west corner is nearest to the legacy tile corner.

    Returns (cell_x, cell_y, snap_offset_metres).
    """
    east, north = lonlat_to_metres(*legacy_tile_to_lonlat(anchor, tile_x, tile_y))
    cell_x = floor(east / CELL_METRES + 0.5)
    cell_y = floor(-north / CELL_METRES + 0.5)
    offset = hypot(cell_x * CELL_METRES - east, -cell_y * CELL_METRES - north)
    if offset > MAX_SNAP_OFFSET_M:
        raise ValueError("Snap offset exceeds half a cell diagonal")
    return cell_x, cell_y, offset


def load_anchors(conn) -> dict[str, LegacyAnchor]:
    return {row["sector_id"]: LegacyAnchor.from_row(row)
            for row in conn.execute("SELECT * FROM world_legacy_sector_anchors")}


def backfill_plots(conn) -> dict:
    """Place every still-unmapped plot on the world grid. Never moves a mapped plot."""
    from psycopg import errors
    anchors = load_anchors(conn)
    rows = conn.execute(
        "SELECT p.id,p.sector_id,p.tile_x,p.tile_y FROM world_plots p "
        "WHERE p.world_cell_x IS NULL "
        # Owned and built plots first: if two ever collide, player property wins.
        "ORDER BY (p.owner_company_id IS NULL),p.sector_id,p.tile_y,p.tile_x,p.id "
        "FOR UPDATE OF p"
    ).fetchall()
    report = {"grid_version": GRID_VERSION, "method": CELL_SOURCE, "examined": len(rows),
              "mapped": 0, "max_snap_offset_m": 0.0,
              "unmapped_no_anchor": [], "unmapped_conflict": []}
    for row in rows:
        anchor = anchors.get(row["sector_id"])
        if anchor is None:
            report["unmapped_no_anchor"].append(str(row["id"]))
            continue
        cell_x, cell_y, offset = legacy_tile_to_world_cell(anchor, row["tile_x"], row["tile_y"])
        try:
            with conn.transaction():
                conn.execute(
                    "UPDATE world_plots SET world_cell_x=%s,world_cell_y=%s,"
                    "world_cell_source=%s,world_cell_offset_m=%s "
                    "WHERE id=%s AND world_cell_x IS NULL",
                    (cell_x, cell_y, CELL_SOURCE, offset, row["id"]))
        except errors.ExclusionViolation:
            report["unmapped_conflict"].append(str(row["id"]))
            continue
        report["mapped"] += 1
        report["max_snap_offset_m"] = max(report["max_snap_offset_m"], round(offset, 3))
    report["still_unmapped"] = conn.execute(
        "SELECT count(*) AS n FROM world_plots WHERE world_cell_x IS NULL").fetchone()["n"]
    return report


def main() -> dict:
    from basheco.db import connect
    with connect() as conn:
        report = backfill_plots(conn)
    print("World grid backfill", json.dumps(report, ensure_ascii=False), flush=True)
    return report


if __name__ == "__main__":
    main()
