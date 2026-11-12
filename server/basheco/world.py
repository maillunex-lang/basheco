"""Server-authoritative prototype world operations.

Plot claiming is free ONLY in the isolated prototype sector.
Production land acquisition will require a separate economic transaction.
"""
from uuid import UUID
from fastapi import HTTPException
from pydantic import BaseModel
from basheco.db import connect

class ConstructRequest(BaseModel):
    company_id: UUID
    plot_id: UUID
    building_type: str

def sector_map(sector_id: str):
    with connect() as conn:
        sector = conn.execute(
            "SELECT id,name,city,width_tiles,height_tiles,geometry_source "
            "FROM world_sectors WHERE id=%s", (sector_id,),
        ).fetchone()
        if sector is None:
            raise HTTPException(404, "Sector not found")
        plots = conn.execute(
            "SELECT p.id,p.tile_x,p.tile_y,p.width_tiles,p.height_tiles,p.zone,"
            "p.owner_company_id,b.id AS building_id,b.building_type "
            "FROM world_plots p LEFT JOIN world_buildings b ON b.plot_id=p.id "
            "WHERE p.sector_id=%s ORDER BY p.tile_y,p.tile_x", (sector_id,),
        ).fetchall()
        return {"sector": sector, "plots": plots}

def grow_district(conn, plot):
    """Open adjacent prototype parcels after construction, under a sector lock.

    These are game parcels, never OSM/cadastral land. Existing parcels are
    preserved. A fixed sector lock serializes simultaneous builders.
    """
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
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-2, -1, 0, 1, 2):
            if dx == 0 and dy == 0:
                continue
            x = origin_x + dx * 8
            y = origin_y + dy * 8
            if x < 0 or y < 0 or x + 5 > sector["width_tiles"] or y + 5 > sector["height_tiles"]:
                continue
            if count + created >= 2000:
                return created
            overlaps = conn.execute(
                "SELECT 1 FROM world_plots WHERE sector_id=%s "
                "AND tile_x < %s AND tile_x + width_tiles > %s "
                "AND tile_y < %s AND tile_y + height_tiles > %s LIMIT 1",
                (plot["sector_id"], x + 5, x, y + 5, y),
            ).fetchone()
            if overlaps:
                continue
            zone = zones[((x // 8) + (y // 8)) % len(zones)]
            conn.execute(
                "INSERT INTO world_plots(sector_id,tile_x,tile_y,width_tiles,height_tiles,zone,generated_by_growth) "
                "VALUES(%s,%s,%s,5,5,%s,true)",
                (plot["sector_id"], x, y, zone),
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
        if plot["sector_id"] != "ufa-prototype-01":
            raise HTTPException(403, "Construction outside prototype is disabled")
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
        new_plots = grow_district(conn, plot)
        return {"new_plots": new_plots, "building_id": str(building["id"]), "plot_id": str(data.plot_id),
                "company_id": str(data.company_id), "building_type": data.building_type}
