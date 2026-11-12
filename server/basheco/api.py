"""Stage 1 loopback API. Not ready for public exposure; rate limits pending."""
from __future__ import annotations
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from psycopg import errors
from basheco.db import connect
from basheco.ledger import Transfer, validate_transfer

app = FastAPI(title="BASHECO API", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None)
ph = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)
EMAIL_RE = re.compile(r"^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,}$")

class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    display_name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_RE.fullmatch(value):
            raise ValueError("Invalid email")
        return value

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Display name too short")
        return value

class LoginRequest(BaseModel):
    email: str
    password: str

class CompanyRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Company name too short")
        return value

class TransferRequest(BaseModel):
    debit_wallet: UUID
    credit_wallet: UUID
    amount_kopecks: int = Field(strict=True, gt=0, le=10**15)
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[a-zA-Z0-9._:-]+$")

def throttle(bucket: str, identity: str, limit: int, window_seconds: int = 900) -> None:
    """Atomic database-backed rate limit, independent of worker count.

    Use the direct peer address only, not untrusted forwarded headers.
    """
    key_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    with connect() as conn:
        row = conn.execute(
            "INSERT INTO request_limits(bucket,key_hash,window_start,attempts) "
            "VALUES(%s,%s,now(),1) "
            "ON CONFLICT (bucket,key_hash) DO UPDATE SET "
            "attempts=CASE WHEN request_limits.window_start <= now() - (%s * interval '1 second') "
            "THEN 1 ELSE request_limits.attempts+1 END, "
            "window_start=CASE WHEN request_limits.window_start <= now() - (%s * interval '1 second') "
            "THEN now() ELSE request_limits.window_start END "
            "RETURNING attempts",
            (bucket, key_hash, window_seconds, window_seconds),
        ).fetchone()
    if row["attempts"] > limit:
        raise HTTPException(429, "Too many requests. Try again later.", headers={"Retry-After": str(window_seconds)})


@app.get("/health")
def health():
    try:
        with connect() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok"}
    except Exception:
        raise HTTPException(503, "Database unavailable")

def current_user(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")
    token = authorization[7:]
    if len(token) != 64 or not re.fullmatch(r"[0-9a-f]+", token):
        raise HTTPException(401, "Invalid session")
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    with connect() as conn:
        record = conn.execute(
            "SELECT account_id FROM sessions WHERE token_hash=%s AND expires_at > now()",
            (token_hash,),
        ).fetchone()
    if not record:
        raise HTTPException(401, "Invalid session")
    return str(record["account_id"])

@app.post("/v1/auth/register", status_code=201)
def register(data: RegisterRequest, request: Request):
    throttle("register-ip", request.client.host if request.client else "unknown", 5, 900)
    hashed = ph.hash(data.password)
    try:
        with connect() as conn:
            row = conn.execute(
                "INSERT INTO accounts(email,display_name,password_hash) VALUES(%s,%s,%s) RETURNING id",
                (data.email, data.display_name, hashed),
            ).fetchone()
            conn.execute("INSERT INTO wallets(account_id) VALUES(%s)", (row["id"],))
        return {"account_id": str(row["id"])}
    except errors.UniqueViolation:
        raise HTTPException(409, "Account already exists")

@app.post("/v1/auth/login")
def login(data: LoginRequest, request: Request):
    peer = request.client.host if request.client else "unknown"
    throttle("login-ip", peer, 40, 900)
    throttle("login-account", data.email.strip().lower(), 8, 900)
    with connect() as conn:
        user = conn.execute(
            "SELECT id,password_hash FROM accounts WHERE lower(email)=lower(%s)",
            (data.email.strip(),),
        ).fetchone()
    if not user:
        raise HTTPException(401, "Invalid credentials")
    try:
        valid = ph.verify(user["password_hash"], data.password)
    except (VerifyMismatchError, InvalidHashError):
        valid = False
    if not valid:
        raise HTTPException(401, "Invalid credentials")
    token = secrets.token_hex(32)
    with connect() as conn:
        conn.execute(
            "INSERT INTO sessions(token_hash,account_id,expires_at) VALUES(%s,%s,%s)",
            (hashlib.sha256(token.encode("ascii")).hexdigest(), user["id"], datetime.now(timezone.utc)+timedelta(days=7)),
        )
    return {"access_token": token, "token_type": "bearer", "expires_in": 604800}

@app.post("/v1/auth/logout", status_code=204)
def logout(account_id: str = Depends(current_user), authorization: str = Header()):
    token_hash = hashlib.sha256(authorization[7:].encode("ascii")).hexdigest()
    with connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash=%s AND account_id=%s", (token_hash, account_id))

@app.get("/v1/me")
def me(account_id: str = Depends(current_user)):
    with connect() as conn:
        return conn.execute(
            "SELECT id,email,display_name,created_at FROM accounts WHERE id=%s", (account_id,),
        ).fetchone()

@app.post("/v1/companies", status_code=201)
def create_company(data: CompanyRequest, account_id: str = Depends(current_user)):
    with connect() as conn:
        row = conn.execute(
            "INSERT INTO companies(owner_account_id,name) VALUES(%s,%s) RETURNING id,name",
            (account_id, data.name),
        ).fetchone()
        wallet = conn.execute(
            "INSERT INTO wallets(company_id) VALUES(%s) RETURNING id", (row["id"],),
        ).fetchone()
    return {"id": str(row["id"]), "name": row["name"], "wallet_id": str(wallet["id"])}

@app.get("/v1/companies")
def list_companies(account_id: str = Depends(current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id,name,created_at FROM companies WHERE owner_account_id=%s ORDER BY created_at",
            (account_id,),
        ).fetchall()
    return {"companies": rows}

@app.get("/v1/wallets")
def list_wallets(account_id: str = Depends(current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT w.id,w.account_id,w.company_id,w.balance_kopecks FROM wallets w "
            "LEFT JOIN companies c ON c.id=w.company_id "
            "WHERE w.account_id=%s OR c.owner_account_id=%s ORDER BY w.id",
            (account_id, account_id),
        ).fetchall()
    return {"wallets": rows}

@app.post("/v1/transfers", status_code=201)
def transfer(data: TransferRequest, account_id: str = Depends(current_user)):
    debit, credit = str(data.debit_wallet), str(data.credit_wallet)
    try:
        validate_transfer(Transfer(debit, credit, data.amount_kopecks, data.idempotency_key))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    with connect() as conn:
        previous = conn.execute(
            "SELECT id,debit_wallet_id,credit_wallet_id,amount_kopecks FROM ledger_transfers "
            "WHERE initiated_by=%s AND idempotency_key=%s",
            (account_id, data.idempotency_key),
        ).fetchone()
        if previous:
            if (str(previous["debit_wallet_id"]), str(previous["credit_wallet_id"]), previous["amount_kopecks"]) != (debit, credit, data.amount_kopecks):
                raise HTTPException(409, "Idempotency key reused for a different transfer")
            return {"transfer_id": str(previous["id"]), "replayed": True}
        wallets = conn.execute(
            "SELECT w.id,w.balance_kopecks,w.account_id,c.owner_account_id AS company_owner "
            "FROM wallets w LEFT JOIN companies c ON c.id=w.company_id "
            "WHERE w.id=ANY(%s::uuid[]) ORDER BY w.id FOR UPDATE OF w",
            ([debit,credit],),
        ).fetchall()
        by_id = {str(w["id"]): w for w in wallets}
        if debit not in by_id or credit not in by_id:
            raise HTTPException(404, "Wallet not found")
        source = by_id[debit]
        if account_id not in (str(source["account_id"]), str(source["company_owner"])):
            raise HTTPException(403, "No permission to debit wallet")
        if source["balance_kopecks"] < data.amount_kopecks:
            raise HTTPException(409, "Insufficient funds")
        if by_id[credit]["balance_kopecks"] + data.amount_kopecks > 2**63-1:
            raise HTTPException(409, "Recipient balance overflow")
        inserted = conn.execute(
            "INSERT INTO ledger_transfers(initiated_by,idempotency_key,debit_wallet_id,credit_wallet_id,amount_kopecks) "
            "VALUES(%s,%s,%s,%s,%s) ON CONFLICT (initiated_by,idempotency_key) DO NOTHING RETURNING id",
            (account_id, data.idempotency_key, debit, credit, data.amount_kopecks),
        ).fetchone()
        if not inserted:
            original = conn.execute(
                "SELECT id,debit_wallet_id,credit_wallet_id,amount_kopecks FROM ledger_transfers "
                "WHERE initiated_by=%s AND idempotency_key=%s",
                (account_id,data.idempotency_key),
            ).fetchone()
            if not original or (str(original["debit_wallet_id"]), str(original["credit_wallet_id"]), original["amount_kopecks"]) != (debit,credit,data.amount_kopecks):
                raise HTTPException(409, "Idempotency conflict")
            return {"transfer_id": str(original["id"]), "replayed": True}
        conn.execute("UPDATE wallets SET balance_kopecks=balance_kopecks-%s WHERE id=%s", (data.amount_kopecks,debit))
        conn.execute("UPDATE wallets SET balance_kopecks=balance_kopecks+%s WHERE id=%s", (data.amount_kopecks,credit))
        conn.execute(
            "INSERT INTO ledger_postings(transfer_id,wallet_id,delta_kopecks) VALUES(%s,%s,%s),(%s,%s,%s)",
            (inserted["id"],debit,-data.amount_kopecks,inserted["id"],credit,data.amount_kopecks),
        )
    return {"transfer_id": str(inserted["id"]), "replayed": False}
