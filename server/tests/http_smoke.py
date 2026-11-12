"""End-to-end HTTP smoke against a disposable database, never production.

Run with BASHECO_TEST_DATABASE_URL ending in /basheco_integration_test.
Launches a local Uvicorn child, then exercises actual HTTP routes.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4
from urllib.parse import urlsplit

from basheco.db import connect
from basheco.migrate import main as migrate


def call(base, method, path, payload=None, token=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def main():
    url = os.environ.get("BASHECO_TEST_DATABASE_URL", "")
    if urlsplit(url).path != "/basheco_integration_test":
        raise RuntimeError("Refusing to run against non-test database")
    os.environ["DATABASE_URL"] = url
    migrate()
    base = "http://127.0.0.1:18317"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "basheco.api:app", "--host", "127.0.0.1", "--port", "18317"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=os.environ.copy(),
    )
    ids = []
    try:
        for _ in range(50):
            try:
                status, _ = call(base, "GET", "/health")
                if status == 200:
                    break
            except (OSError, TimeoutError):
                time.sleep(.1)
        else:
            raise AssertionError("HTTP test server did not start")
        for i in range(2):
            email = "smoke-" + str(uuid4()) + "@example.invalid"
            password = "TestOnly-Long-Password-123"
            status, registered = call(base, "POST", "/v1/auth/register", {
                "email": email, "display_name": "Smoke Test", "password": password
            })
            assert status == 201, (status, registered)
            ids.append(registered["account_id"])
            status, login = call(base, "POST", "/v1/auth/login", {"email": email, "password": password})
            assert status == 200, (status, login)
            token = login["access_token"]
            status, company = call(base, "POST", "/v1/companies", {"name": "Smoke Enterprise"}, token)
            assert status == 201, (status, company)
            if i == 0:
                seller = (token, company["id"])
            else:
                buyer = (token, company["id"])
        with connect() as conn:
            plot = conn.execute(
                "SELECT id FROM world_plots WHERE sector_id='ufa-prototype-01' "
                "AND zone='agricultural' AND owner_company_id IS NULL "
                "ORDER BY tile_x LIMIT 1 FOR UPDATE"
            ).fetchone()
            assert plot
            plot_id = str(plot["id"])
        status, building = call(base, "POST", "/v1/world/buildings", {
            "company_id": seller[1], "plot_id": plot_id, "building_type": "greenhouse"
        }, seller[0])
        assert status == 201, (status, building)
        status, produced = call(base, "POST", "/v1/economy/produce", {
            "building_id": building["building_id"], "recipe_code": "grow_vegetables",
            "idempotency_key": "http-smoke-produce-" + str(uuid4())
        }, seller[0])
        assert status == 201 and produced["quantity"] == 10, (status, produced)
        status, listing = call(base, "POST", "/v1/market/listings", {
            "company_id": seller[1], "resource_code": "vegetables",
            "quantity": 4, "unit_price_kopecks": 100
        }, seller[0])
        assert status == 201, (status, listing)
        status, denied = call(base, "POST", "/v1/market/listings/" + listing["listing_id"] + "/buy", {
            "company_id": buyer[1], "quantity": 2, "idempotency_key": "http-smoke-buy-" + str(uuid4())
        }, buyer[0])
        assert status == 409, (status, denied)
        status, cancelled = call(base, "POST", "/v1/market/listings/" + listing["listing_id"] + "/cancel", {}, seller[0])
        assert status == 200 and cancelled["returned_quantity"] == 4, (status, cancelled)
        print("BASHECO_HTTP_SMOKE_OK registration login company construction production market insufficient-funds cancellation")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        if ids:
            with connect() as conn:
                conn.execute("DELETE FROM security_audit WHERE actor_account_id=ANY(%s::uuid[])", (ids,))
                conn.execute("DELETE FROM production_runs WHERE company_id IN (SELECT id FROM companies WHERE owner_account_id=ANY(%s::uuid[]))", (ids,))
                conn.execute("DELETE FROM market_purchases WHERE buyer_account_id=ANY(%s::uuid[])", (ids,))
                conn.execute("DELETE FROM market_listings WHERE seller_company_id IN (SELECT id FROM companies WHERE owner_account_id=ANY(%s::uuid[]))", (ids,))
                conn.execute("DELETE FROM company_inventory WHERE company_id IN (SELECT id FROM companies WHERE owner_account_id=ANY(%s::uuid[]))", (ids,))
                conn.execute("DELETE FROM world_buildings WHERE company_id IN (SELECT id FROM companies WHERE owner_account_id=ANY(%s::uuid[]))", (ids,))
                conn.execute("UPDATE world_plots SET owner_company_id=NULL WHERE owner_company_id IN (SELECT id FROM companies WHERE owner_account_id=ANY(%s::uuid[]))", (ids,))
                conn.execute("DELETE FROM wallets WHERE account_id=ANY(%s::uuid[]) OR company_id IN (SELECT id FROM companies WHERE owner_account_id=ANY(%s::uuid[]))", (ids,))
                conn.execute("DELETE FROM companies WHERE owner_account_id=ANY(%s::uuid[])", (ids,))
                conn.execute("DELETE FROM sessions WHERE account_id=ANY(%s::uuid[])", (ids,))
                conn.execute("DELETE FROM accounts WHERE id=ANY(%s::uuid[])", (ids,))


if __name__ == "__main__":
    main()
