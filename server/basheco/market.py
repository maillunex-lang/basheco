"""Fixed-price resource market with escrow and double-entry settlement.

Lock order for purchases: listing -> company rows sorted -> wallets sorted.
A listing reserves its stock at creation, preventing double-selling.
"""
from uuid import UUID
from fastapi import HTTPException
from pydantic import BaseModel,Field
from basheco.db import connect

MAX_PRICE=10**12
MAX_TOTAL=10**15
class ListRequest(BaseModel):
    company_id: UUID
    resource_code: str=Field(min_length=2,max_length=80)
    quantity: int=Field(strict=True,gt=0,le=10**9)
    unit_price_kopecks: int=Field(strict=True,gt=0,le=MAX_PRICE)

class BuyRequest(BaseModel):
    company_id: UUID
    quantity: int=Field(strict=True,gt=0,le=10**9)
    idempotency_key: str=Field(min_length=8,max_length=128,pattern=r"^[a-zA-Z0-9._:-]+$")

def listings():
    with connect() as conn:
        return {"listings":conn.execute(
            "SELECT id,seller_company_id,resource_code,quantity_remaining,unit_price_kopecks,"
            "created_at FROM market_listings WHERE status='active' AND quantity_remaining>0 "
            "ORDER BY created_at LIMIT 200"
        ).fetchall()}

def create_listing(data:ListRequest,account_id:str):
    with connect() as conn:
        owner=conn.execute(
            "SELECT id FROM companies WHERE id=%s AND owner_account_id=%s FOR UPDATE",
            (data.company_id,account_id),
        ).fetchone()
        if not owner:
            raise HTTPException(403,"Company not owned by player")
        available=conn.execute(
            "UPDATE company_inventory SET quantity=quantity-%s WHERE company_id=%s "
            "AND resource_code=%s AND quantity>=%s RETURNING quantity",
            (data.quantity,data.company_id,data.resource_code,data.quantity),
        ).fetchone()
        if not available:
            raise HTTPException(409,"Insufficient stock")
        row=conn.execute(
            "INSERT INTO market_listings(seller_company_id,resource_code,quantity_remaining,unit_price_kopecks) "
            "VALUES(%s,%s,%s,%s) RETURNING id",
            (data.company_id,data.resource_code,data.quantity,data.unit_price_kopecks),
        ).fetchone()
        return {"listing_id":str(row["id"])}

def cancel_listing(listing_id:UUID,account_id:str):
    with connect() as conn:
        listing=conn.execute(
            "SELECT id,seller_company_id,resource_code,quantity_remaining,status "
            "FROM market_listings WHERE id=%s FOR UPDATE",(listing_id,),
        ).fetchone()
        if not listing:
            raise HTTPException(404,"Listing not found")
        owner=conn.execute(
            "SELECT id FROM companies WHERE id=%s AND owner_account_id=%s FOR UPDATE",
            (listing["seller_company_id"],account_id),
        ).fetchone()
        if not owner:
            raise HTTPException(403,"Company not owned by player")
        if listing["status"]!="active":
            raise HTTPException(409,"Listing not active")
        conn.execute("UPDATE market_listings SET status='cancelled' WHERE id=%s",(listing_id,))
        if listing["quantity_remaining"]:
            conn.execute(
                "INSERT INTO company_inventory(company_id,resource_code,quantity) VALUES(%s,%s,%s) "
                "ON CONFLICT(company_id,resource_code) DO UPDATE "
                "SET quantity=company_inventory.quantity+EXCLUDED.quantity",
                (listing["seller_company_id"],listing["resource_code"],listing["quantity_remaining"]),
            )
        return {"cancelled":True,"returned_quantity":listing["quantity_remaining"]}

def buy(listing_id:UUID,data:BuyRequest,account_id:str):
    with connect() as conn:
        # Replay must work even if listing has since been sold/cancelled.
        previous=conn.execute(
            "SELECT id,listing_id,buyer_company_id,quantity,total_kopecks FROM market_purchases "
            "WHERE buyer_account_id=%s AND idempotency_key=%s",
            (account_id,data.idempotency_key),
        ).fetchone()
        if previous:
            if (previous["listing_id"],previous["buyer_company_id"],previous["quantity"])!=(
                listing_id,data.company_id,data.quantity
            ):
                raise HTTPException(409,"Idempotency key conflict")
            return {"purchase_id":str(previous["id"]),"total_kopecks":previous["total_kopecks"],"replayed":True}
        listing=conn.execute(
            "SELECT id,seller_company_id,resource_code,quantity_remaining,unit_price_kopecks,status "
            "FROM market_listings WHERE id=%s FOR UPDATE",(listing_id,),
        ).fetchone()
        if not listing:
            raise HTTPException(404,"Listing not found")
        if listing["status"]!="active" or listing["quantity_remaining"]<data.quantity:
            raise HTTPException(409,"Insufficient listing quantity")
        if listing["seller_company_id"]==data.company_id:
            raise HTTPException(422,"Cannot buy own listing")
        company_ids=sorted([str(data.company_id),str(listing["seller_company_id"])])
        companies=conn.execute(
            "SELECT id,owner_account_id FROM companies WHERE id=ANY(%s::uuid[]) "
            "ORDER BY id FOR UPDATE",(company_ids,),
        ).fetchall()
        company_by_id={str(x["id"]):x for x in companies}
        if str(data.company_id) not in company_by_id or str(company_by_id[str(data.company_id)]["owner_account_id"])!=account_id:
            raise HTTPException(403,"Buyer company not owned by player")
        total=data.quantity*listing["unit_price_kopecks"]
        if total>MAX_TOTAL:
            raise HTTPException(422,"Purchase exceeds maximum")
        wallets=conn.execute(
            "SELECT id,company_id,balance_kopecks FROM wallets "
            "WHERE company_id=ANY(%s::uuid[]) ORDER BY id FOR UPDATE",(company_ids,),
        ).fetchall()
        wallet_by_company={str(x["company_id"]):x for x in wallets}
        buyer=wallet_by_company.get(str(data.company_id))
        seller=wallet_by_company.get(str(listing["seller_company_id"]))
        if not buyer or not seller:
            raise HTTPException(409,"Company wallet missing")
        if buyer["balance_kopecks"]<total:
            raise HTTPException(409,"Insufficient funds")
        if seller["balance_kopecks"]+total>2**63-1:
            raise HTTPException(409,"Seller balance overflow")
        # A separate namespace prevents collision with player-initiated transfers.
        transfer_key="market:"+str(listing_id)+":"+data.idempotency_key
        # 128-character DB limit; fixed-size digest is safer.
        import hashlib
        transfer_key="market:"+hashlib.sha256((account_id+":"+str(listing_id)+":"+data.idempotency_key).encode()).hexdigest()
        transfer=conn.execute(
            "INSERT INTO ledger_transfers(initiated_by,idempotency_key,debit_wallet_id,credit_wallet_id,amount_kopecks) "
            "VALUES(%s,%s,%s,%s,%s) RETURNING id",
            (account_id,transfer_key,buyer["id"],seller["id"],total),
        ).fetchone()
        conn.execute("UPDATE wallets SET balance_kopecks=balance_kopecks-%s WHERE id=%s",(total,buyer["id"]))
        conn.execute("UPDATE wallets SET balance_kopecks=balance_kopecks+%s WHERE id=%s",(total,seller["id"]))
        conn.execute(
            "INSERT INTO ledger_postings(transfer_id,wallet_id,delta_kopecks) VALUES(%s,%s,%s),(%s,%s,%s)",
            (transfer["id"],buyer["id"],-total,transfer["id"],seller["id"],total),
        )
        conn.execute(
            "UPDATE market_listings SET quantity_remaining=quantity_remaining-%s,"
            "status=CASE WHEN quantity_remaining=%s THEN 'sold' ELSE 'active' END WHERE id=%s",
            (data.quantity,data.quantity,listing_id),
        )
        conn.execute(
            "INSERT INTO company_inventory(company_id,resource_code,quantity) VALUES(%s,%s,%s) "
            "ON CONFLICT(company_id,resource_code) DO UPDATE "
            "SET quantity=company_inventory.quantity+EXCLUDED.quantity",
            (data.company_id,listing["resource_code"],data.quantity),
        )
        purchase=conn.execute(
            "INSERT INTO market_purchases(listing_id,buyer_company_id,buyer_account_id,quantity,"
            "total_kopecks,transfer_id,idempotency_key) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (listing_id,data.company_id,account_id,data.quantity,total,transfer["id"],data.idempotency_key),
        ).fetchone()
        return {"purchase_id":str(purchase["id"]),"total_kopecks":total,"replayed":False}
