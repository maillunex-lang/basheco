"""Transactional prototype production. No client-provided output quantities."""
from uuid import UUID
from fastapi import HTTPException
from pydantic import BaseModel, Field
from basheco.db import connect

class ProduceRequest(BaseModel):
    building_id: UUID
    recipe_code: str = Field(min_length=2,max_length=80)
    idempotency_key: str = Field(min_length=8,max_length=128,pattern=r"^[a-zA-Z0-9._:-]+$")

def catalog():
    with connect() as conn:
        recipes=conn.execute(
            "SELECT code,building_type,input_resource,input_quantity,output_resource,"
            "output_quantity,cooldown_seconds FROM production_recipes ORDER BY code"
        ).fetchall()
        resources=conn.execute("SELECT code,title FROM resource_types ORDER BY code").fetchall()
    return {"recipes":recipes,"resources":resources}

def inventory(account_id: str):
    with connect() as conn:
        rows=conn.execute(
            "SELECT i.company_id,i.resource_code,i.quantity FROM company_inventory i "
            "JOIN companies c ON c.id=i.company_id "
            "WHERE c.owner_account_id=%s ORDER BY i.company_id,i.resource_code",
            (account_id,),
        ).fetchall()
    return {"inventory":rows}

def produce(data: ProduceRequest, account_id: str):
    with connect() as conn:
        # Lock the company first, so parallel runs across its buildings serialize
        # inventory checks and changes in a consistent lock order.
        company=conn.execute(
            "SELECT c.id FROM companies c JOIN world_buildings b ON b.company_id=c.id "
            "WHERE b.id=%s AND c.owner_account_id=%s FOR UPDATE OF c",
            (data.building_id,account_id),
        ).fetchone()
        if not company:
            raise HTTPException(403,"Building not owned by player")
        company_id=company["id"]
        previous=conn.execute(
            "SELECT id,building_id,recipe_code FROM production_runs "
            "WHERE company_id=%s AND idempotency_key=%s",
            (company_id,data.idempotency_key),
        ).fetchone()
        if previous:
            if previous["building_id"] != data.building_id or previous["recipe_code"] != data.recipe_code:
                raise HTTPException(409,"Idempotency key reused for different request")
            return {"run_id":str(previous["id"]),"replayed":True}
        building=conn.execute(
            "SELECT b.id,b.building_type,p.sector_id FROM world_buildings b "
            "JOIN world_plots p ON p.id=b.plot_id WHERE b.id=%s",
            (data.building_id,),
        ).fetchone()
        if building["sector_id"]!="ufa-prototype-01":
            raise HTTPException(403,"Production outside prototype disabled")
        recipe=conn.execute(
            "SELECT code,building_type,input_resource,input_quantity,output_resource,"
            "output_quantity,cooldown_seconds FROM production_recipes WHERE code=%s",
            (data.recipe_code,),
        ).fetchone()
        if not recipe or recipe["building_type"]!=building["building_type"]:
            raise HTTPException(422,"Recipe not available for building")
        recent=conn.execute(
            "SELECT 1 FROM production_runs WHERE building_id=%s AND recipe_code=%s "
            "AND produced_at > now() - (%s * interval '1 second') LIMIT 1",
            (data.building_id,data.recipe_code,recipe["cooldown_seconds"]),
        ).fetchone()
        if recent:
            raise HTTPException(429,"Production cooldown active")
        if recipe["input_resource"]:
            updated=conn.execute(
                "UPDATE company_inventory SET quantity=quantity-%s "
                "WHERE company_id=%s AND resource_code=%s AND quantity >= %s "
                "RETURNING quantity",
                (recipe["input_quantity"],company_id,recipe["input_resource"],recipe["input_quantity"]),
            ).fetchone()
            if not updated:
                raise HTTPException(409,"Insufficient resources")
        conn.execute(
            "INSERT INTO company_inventory(company_id,resource_code,quantity) "
            "VALUES(%s,%s,%s) ON CONFLICT(company_id,resource_code) DO UPDATE "
            "SET quantity=company_inventory.quantity+EXCLUDED.quantity",
            (company_id,recipe["output_resource"],recipe["output_quantity"]),
        )
        run=conn.execute(
            "INSERT INTO production_runs(building_id,company_id,recipe_code,idempotency_key) "
            "VALUES(%s,%s,%s,%s) RETURNING id",
            (data.building_id,company_id,data.recipe_code,data.idempotency_key),
        ).fetchone()
        return {"run_id":str(run["id"]),"replayed":False,
                "resource":recipe["output_resource"],"quantity":recipe["output_quantity"]}
