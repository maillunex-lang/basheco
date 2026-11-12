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

def construct(data: ConstructRequest, account_id: str):
    with connect() as conn:
        company = conn.execute(
            "SELECT id FROM companies WHERE id=%s AND owner_account_id=%s",
            (data.company_id, account_id),
        ).fetchone()
        if not company:
            raise HTTPException(403, "Company not owned by player")
        plot = conn.execute(
            "SELECT id,sector_id,zone,owner_company_id FROM world_plots "
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
        return {"building_id": str(building["id"]), "plot_id": str(data.plot_id),
                "company_id": str(data.company_id), "building_type": data.building_type}
