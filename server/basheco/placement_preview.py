"""Read-only placement inspection, never a construction permit."""
from uuid import UUID
from fastapi import HTTPException
from pydantic import BaseModel, Field
from basheco.db import connect
from basheco.placement import PlacementError, catalog_footprint, preview


class PreviewRequest(BaseModel):
    company_id: UUID
    plot_id: UUID
    catalog_code: str = Field(min_length=1, max_length=100)
    cell_x: int
    cell_y: int
    rotation: int = 0


def inspect_placement(data: PreviewRequest, account_id: str) -> dict:
    """Geometric preview on an explicitly company-owned game parcel only.

    A successful preview does NOT authorize a build: terrain/legal masks,
    road access, finances and final concurrent occupancy require commit checks.
    """
    with connect() as conn:
        company = conn.execute(
            "SELECT id FROM companies WHERE id=%s AND owner_account_id=%s",
            (data.company_id, account_id),
        ).fetchone()
        if company is None:
            raise HTTPException(403, "Company not owned by player")
        plot = conn.execute(
            "SELECT id,owner_company_id,zone,world_cell_x,world_cell_y,width_tiles,height_tiles "
            "FROM world_plots WHERE id=%s", (data.plot_id,),
        ).fetchone()
        if plot is None:
            raise HTTPException(404, "Plot not found")
        if plot["owner_company_id"] != data.company_id:
            raise HTTPException(403, "Plot not owned by company")
        if plot["world_cell_x"] is None or plot["world_cell_y"] is None:
            raise HTTPException(409, "Plot not on world grid")
        item = conn.execute(
            "SELECT code,zone,footprint,version,cost_kopecks,requires_road "
            "FROM world_object_catalog WHERE code=%s AND active=true AND kind='building'",
            (data.catalog_code,),
        ).fetchone()
        if item is None:
            raise HTTPException(404, "Catalog object unavailable")
        if item["zone"] != plot["zone"]:
            raise HTTPException(422, "Wrong zone")
        left, top = int(plot["world_cell_x"]), int(plot["world_cell_y"])
        bounds = (left, top, left + int(plot["width_tiles"]), top + int(plot["height_tiles"]))
        occupied = conn.execute(
            "SELECT cell_x,cell_y FROM world_object_cells "
            "WHERE layer='surface' AND cell_x >= %s AND cell_x < %s "
            "AND cell_y >= %s AND cell_y < %s",
            bounds,
        ).fetchall()
        try:
            result = preview(catalog_footprint(item["footprint"]), data.rotation,
                             (data.cell_x, data.cell_y), bounds,
                             ((int(row["cell_x"]), int(row["cell_y"])) for row in occupied))
        except PlacementError as exc:
            raise HTTPException(422, str(exc)) from exc
        # A geometry pass is not sufficient for placement authorization.
        return {"geometry_valid": True, "construction_allowed": False,
                "reason": "Additional land, rights, access, funds and commit checks required",
                "catalog_code": item["code"], "catalog_version": item["version"],
                "cost_kopecks": item["cost_kopecks"], "requires_road": item["requires_road"],
                "rotation": result.rotation, "bounds": list(result.bounds),
                "cells": [list(cell) for cell in sorted(result.cells)]}