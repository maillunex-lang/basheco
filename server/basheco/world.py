"""Server-authoritative settlement world operations.

Legacy prototype plots have been removed from the active world.
Production land acquisition will require a separate economic transaction.
"""
from uuid import UUID
from fastapi import HTTPException
from psycopg import errors
from pydantic import BaseModel, Field
from basheco.db import connect
from basheco.generated_occupancy import lock_occupancy, reject_published_overlap, generated_overlap
from basheco.world_grid import grid_spec
from basheco.world_compat import CELL_SOURCE, LegacyAnchor, legacy_tile_to_world_cell

MAX_VIEWPORT_CELLS = 512
_PLOT_COLUMNS = (
    "p.id,p.sector_id,p.tile_x,p.tile_y,p.width_tiles,p.height_tiles,p.zone,"
    "p.owner_company_id,p.world_cell_x,p.world_cell_y,"
    "b.id AS building_id,b.building_type "
    "FROM world_plots p LEFT JOIN world_buildings b ON b.plot_id=p.id "
)

class ConstructRequest(BaseModel):
    company_id: UUID
    plot_id: UUID
    building_type: str

class NewPlotRequest(BaseModel):
    sector_id: str
    tile_x: int = Field(ge=0, le=4090)
    tile_y: int = Field(ge=0, le=4090)
    zone: str


def create_plot(data: NewPlotRequest, account_id: str):
    """Create a server-validated vacant game parcel, not an OSM/cadastral parcel.

    Requires a logged-in player; an account may provision at most three
    vacant parcels in a settlement. All spatial checks are transactional.
    """
    if data.sector_id not in ("ufa", "mikhailovka"):
        raise HTTPException(422, "Unknown settlement")
    if data.zone not in ("commercial", "industrial", "agricultural"):
        raise HTTPException(422, "Invalid zone")
    with connect() as conn:
        lock_occupancy(conn)
        # Lock the sector first to serialize competing overlapping requests.
        sector = conn.execute(
            "SELECT id,width_tiles,height_tiles FROM world_sectors WHERE id=%s FOR UPDATE",
            (data.sector_id,),
        ).fetchone()
        if not sector:
            raise HTTPException(404, "Settlement not found")
        if data.tile_x + 5 > sector["width_tiles"] or data.tile_y + 5 > sector["height_tiles"]:
            raise HTTPException(422, "Parcel outside settlement coordinate extent")
        account = conn.execute("SELECT id FROM accounts WHERE id=%s", (account_id,)).fetchone()
        if not account:
            raise HTTPException(403, "Account not found")
        created = conn.execute(
            "SELECT count(*) AS n FROM world_plots WHERE sector_id=%s AND created_by_account_id=%s",
            (data.sector_id, account_id),
        ).fetchone()["n"]
        if created >= 3:
            raise HTTPException(409, "Alpha parcel quota reached")
        count = conn.execute(
            "SELECT count(*) AS n FROM world_plots WHERE sector_id=%s",
            (data.sector_id,),
        ).fetchone()["n"]
        if count >= 2000:
            raise HTTPException(409, "Settlement parcel capacity reached")
        overlap = conn.execute(
            "SELECT id FROM world_plots WHERE sector_id=%s "
            "AND tile_x < %s AND tile_x + width_tiles > %s "
            "AND tile_y < %s AND tile_y + height_tiles > %s LIMIT 1",
            (data.sector_id, data.tile_x + 5, data.tile_x, data.tile_y + 5, data.tile_y),
        ).fetchone()
        if overlap:
            raise HTTPException(409, "Parcel overlaps an existing parcel")
        # The request still uses legacy settlement coordinates (API unchanged), but the
        # parcel is stored with its position on the single world grid. The exclusion
        # constraint rejects any overlap with parcels of every settlement.
        anchor_row = conn.execute(
            "SELECT * FROM world_legacy_sector_anchors WHERE sector_id=%s", (data.sector_id,),
        ).fetchone()
        if not anchor_row:
            raise HTTPException(409, "Settlement is not georeferenced on the world grid")
        cell_x, cell_y, offset = legacy_tile_to_world_cell(
            LegacyAnchor.from_row(anchor_row), data.tile_x, data.tile_y)
        reject_published_overlap(conn, cell_x, cell_y, 5, 5)
        try:
            with conn.transaction():
                row = conn.execute(
                    "INSERT INTO world_plots(sector_id,tile_x,tile_y,width_tiles,height_tiles,zone,"
                    "generated_by_growth,created_by_account_id,"
                    "world_cell_x,world_cell_y,world_cell_source,world_cell_offset_m) "
                    "VALUES(%s,%s,%s,5,5,%s,true,%s,%s,%s,%s,%s) RETURNING id",
                    (data.sector_id, data.tile_x, data.tile_y, data.zone, account_id,
                     cell_x, cell_y, CELL_SOURCE, offset),
                ).fetchone()
        except errors.ExclusionViolation:
            raise HTTPException(409, "Parcel overlaps an existing parcel")
        return {"plot_id": str(row["id"]), "sector_id": data.sector_id,
                "tile_x": data.tile_x, "tile_y": data.tile_y, "zone": data.zone,
                "world_cell_x": cell_x, "world_cell_y": cell_y}


def world_viewport(min_cell_x: int, min_cell_y: int, max_cell_x: int, max_cell_y: int):
    """Parcels of ALL settlements intersecting a rectangle of global world cells.

    Half-open rectangle [min, max). Coordinates may be negative. Parcels that
    are not placed on the world grid yet are never returned here; their number
    is reported so that a client cannot mistake them for empty land.
    """
    limit = 2 ** 40
    if not all(-limit <= v <= limit for v in (min_cell_x, min_cell_y, max_cell_x, max_cell_y)):
        raise HTTPException(422, "Invalid viewport")
    if max_cell_x <= min_cell_x or max_cell_y <= min_cell_y:
        raise HTTPException(422, "Invalid viewport")
    if max_cell_x - min_cell_x > MAX_VIEWPORT_CELLS or max_cell_y - min_cell_y > MAX_VIEWPORT_CELLS:
        raise HTTPException(422, "Viewport too large")
    with connect() as conn:
        plots = conn.execute(
            "SELECT " + _PLOT_COLUMNS +
            "WHERE p.world_cell_x IS NOT NULL "
            "AND int8range(p.world_cell_x, p.world_cell_x + p.width_tiles) && int8range(%s,%s) "
            "AND int8range(p.world_cell_y, p.world_cell_y + p.height_tiles) && int8range(%s,%s) "
            "ORDER BY p.world_cell_y,p.world_cell_x,p.id LIMIT 2001",
            (min_cell_x, max_cell_x, min_cell_y, max_cell_y),
        ).fetchall()
        if len(plots) > 2000:
            raise HTTPException(413, "Viewport plot count exceeds limit")
        unplaced = conn.execute(
            "SELECT count(*) AS n FROM world_plots WHERE world_cell_x IS NULL").fetchone()["n"]
    return {"grid": grid_spec(), "plots": plots, "unplaced_plot_count": unplaced,
            "viewport": {"min_cell_x": min_cell_x, "min_cell_y": min_cell_y,
                         "max_cell_x": max_cell_x, "max_cell_y": max_cell_y}}


def world_grid_info():
    """Authoritative grid contract and the documented legacy sector anchors."""
    with connect() as conn:
        anchors = conn.execute(
            "SELECT sector_id,origin_lon,origin_lat,origin_tile_x,origin_tile_y,"
            "metres_per_tile,projection FROM world_legacy_sector_anchors ORDER BY sector_id"
        ).fetchall()
    return {"grid": grid_spec(), "legacy_sector_anchors": anchors,
            "legacy_note": "sector tile_x/tile_y are historical local indices, not world cells"}


def sector_map(sector_id: str):
    with connect() as conn:
        sector = conn.execute(
            "SELECT id,name,city,width_tiles,height_tiles,geometry_source "
            "FROM world_sectors WHERE id=%s", (sector_id,),
        ).fetchone()
        if sector is None:
            raise HTTPException(404, "Sector not found")
        plots = conn.execute(
            "SELECT " + _PLOT_COLUMNS +
            "WHERE p.sector_id=%s ORDER BY p.tile_y,p.tile_x", (sector_id,),
        ).fetchall()
        return {"sector": sector, "plots": plots}

def sector_viewport(sector_id: str, min_x: int, min_y: int, max_x: int, max_y: int):
    """Return only server-owned parcels intersecting a bounded camera rectangle.

    This is a read-only companion to sector_map. It does not change plot IDs,
    grant land, or assume that OSM geometry is player-owned.
    """
    if max_x <= min_x or max_y <= min_y:
        raise HTTPException(422, "Invalid viewport")
    if max_x - min_x > 512 or max_y - min_y > 512:
        raise HTTPException(422, "Viewport too large")
    with connect() as conn:
        sector = conn.execute(
            "SELECT id,name,city,width_tiles,height_tiles,geometry_source "
            "FROM world_sectors WHERE id=%s", (sector_id,),
        ).fetchone()
        if sector is None:
            raise HTTPException(404, "Sector not found")
        plots = conn.execute(
            "SELECT " + _PLOT_COLUMNS +
            "WHERE p.sector_id=%s "
            "AND p.tile_x < %s AND p.tile_x + p.width_tiles > %s "
            "AND p.tile_y < %s AND p.tile_y + p.height_tiles > %s "
            "ORDER BY p.tile_y,p.tile_x LIMIT 2001",
            (sector_id, max_x, min_x, max_y, min_y),
        ).fetchall()
        if len(plots) > 2000:
            raise HTTPException(413, "Viewport plot count exceeds limit")
        return {"sector": sector, "plots": plots, "viewport": {
            "min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y,
        }}


def grow_district(conn, plot):
    """Legacy helper: open parcels under the common occupancy lock.

    These are game parcels, never OSM/cadastral land. Existing parcels are
    preserved. A fixed sector lock serializes simultaneous builders.
    """
    lock_occupancy(conn)
    sector = conn.execute(
        "SELECT width_tiles,height_tiles FROM world_sectors WHERE id=%s FOR UPDATE",
        (plot["sector_id"],),
    ).fetchone()
    count = conn.execute(
        "SELECT count(*) AS n FROM world_plots WHERE sector_id=%s",
        (plot["sector_id"],),
    ).fetchone()["n"]
    if count >= 2000:
        return 0
    created = 0
    origin_x = (plot["tile_x"] // 8) * 8
    origin_y = (plot["tile_y"] // 8) * 8
    zones = ("commercial", "industrial", "agricultural")
    anchor_row = conn.execute(
        "SELECT * FROM world_legacy_sector_anchors WHERE sector_id=%s",
        (plot["sector_id"],),
    ).fetchone()
    if not anchor_row:
        return 0  # Never create an unplaced parcel around a player building.
    anchor = LegacyAnchor.from_row(anchor_row)
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-2, -1, 0, 1, 2):
            if dx == 0 and dy == 0:
                continue
            x = origin_x + dx * 8
            y = origin_y + dy * 8
            if x < 0 or y < 0 or x + 5 > sector["width_tiles"] or y + 5 > sector["height_tiles"]:
                continue
            if created >= 8 or count + created >= 2000:
                return created
            overlaps = conn.execute(
                "SELECT 1 FROM world_plots WHERE sector_id=%s "
                "AND tile_x < %s AND tile_x + width_tiles > %s "
                "AND tile_y < %s AND tile_y + height_tiles > %s LIMIT 1",
                (plot["sector_id"], x + 5, x, y + 5, y),
            ).fetchone()
            if overlaps:
                continue
            cell_x, cell_y, offset = legacy_tile_to_world_cell(anchor, x, y)
            if generated_overlap(conn, cell_x, cell_y, 5, 5):
                continue
            zone = zones[((x // 8) + (y // 8)) % len(zones)]
            conn.execute(
                "INSERT INTO world_plots(sector_id,tile_x,tile_y,width_tiles,height_tiles,zone,"
                "generated_by_growth,world_cell_x,world_cell_y,world_cell_source,world_cell_offset_m) "
                "VALUES(%s,%s,%s,5,5,%s,true,%s,%s,%s,%s)",
                (plot["sector_id"], x, y, zone, cell_x, cell_y, CELL_SOURCE, offset),
            )
            created += 1
    return created


def construct(data: ConstructRequest, account_id: str):
    with connect() as conn:
        company = conn.execute(
            "SELECT id FROM companies WHERE id=%s AND owner_account_id=%s",
            (data.company_id, account_id),
        ).fetchone()
        if not company:
            raise HTTPException(403, "Company not owned by player")
        plot = conn.execute(
            "SELECT id,sector_id,zone,owner_company_id,tile_x,tile_y,width_tiles,height_tiles FROM world_plots "
            "WHERE id=%s FOR UPDATE", (data.plot_id,),
        ).fetchone()
        if not plot:
            raise HTTPException(404, "Plot not found")
        if plot["sector_id"] not in ("ufa", "mikhailovka"):
            raise HTTPException(403, "Construction outside active settlements is disabled")
        if plot["owner_company_id"] is not None:
            raise HTTPException(409, "Plot already occupied")
        building_type = conn.execute(
            "SELECT code,zone FROM building_types WHERE code=%s",
            (data.building_type,),
        ).fetchone()
        if not building_type:
            raise HTTPException(422, "Unknown building type")
        if building_type["zone"] != plot["zone"]:
            raise HTTPException(422, "Building type not permitted in plot zone")
        conn.execute(
            "UPDATE world_plots SET owner_company_id=%s WHERE id=%s",
            (data.company_id, data.plot_id),
        )
        building = conn.execute(
            "INSERT INTO world_buildings(plot_id,company_id,building_type) "
            "VALUES(%s,%s,%s) RETURNING id",
            (data.plot_id,data.company_id,data.building_type),
        ).fetchone()
        # Grow sector in bounded increments when development approaches an edge.
        # Existing plot and building identifiers remain unchanged.
        conn.execute(
            "UPDATE world_sectors s SET "
            "width_tiles=LEAST(4096, GREATEST(s.width_tiles, %s + 64)), "
            "height_tiles=LEAST(4096, GREATEST(s.height_tiles, %s + 64)) "
            "WHERE s.id=%s AND "
            "(%s >= s.width_tiles - 16 OR %s >= s.height_tiles - 16)",
            (plot["tile_x"] + plot["width_tiles"],
             plot["tile_y"] + plot["height_tiles"],
             plot["sector_id"],
             plot["tile_x"] + plot["width_tiles"],
             plot["tile_y"] + plot["height_tiles"]),
        )
        new_plots = 0  # New plots are explicitly created, never spawned around a building.
        return {"new_plots": new_plots, "building_id": str(building["id"]), "plot_id": str(data.plot_id),
                "company_id": str(data.company_id), "building_type": data.building_type}