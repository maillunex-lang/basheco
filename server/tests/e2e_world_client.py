"""End-to-end: real HTTP API + real Godot client on one world grid.

Run on a workstation, never against production:
  BASHECO_TEST_DATABASE_URL=postgresql://.../basheco_integration_test \
  GODOT_BIN=godot python tests/e2e_world_client.py

Starts the API on 127.0.0.1, registers a throw-away player, creates one parcel
through the unchanged legacy API in each settlement sector, then lets the Godot
client log in, fetch /v1/world/viewport and verify that it draws both parcels at
the server's world cells and at the same WGS84 position. Cleans up afterwards.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
PORT = 4219


def call(method, path, body=None, token=None):
    request = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, json.loads(response.read() or b"null")


def main() -> int:
    url = os.environ.get("BASHECO_TEST_DATABASE_URL", "")
    if not url.rstrip("/").endswith("/basheco_integration_test"):
        raise SystemExit("Refusing to run without the disposable basheco_integration_test database")
    godot = shutil.which(os.environ.get("GODOT_BIN", "godot"))
    if not godot:
        raise SystemExit("Godot binary not found (set GODOT_BIN)")
    os.environ["DATABASE_URL"] = url
    from basheco.db import connect
    from basheco.migrate import main as migrate
    from basheco.world_compat import legacy_tile_to_lonlat, load_anchors
    migrate()
    email = f"e2e-{uuid4().hex}@example.invalid"
    password = "e2e-" + uuid4().hex
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "basheco.api:app", "--host", "127.0.0.1",
                               "--port", str(PORT), "--log-level", "warning"], cwd=ROOT / "server")
    created = []
    try:
        for _ in range(50):
            try:
                if call("GET", "/health")[0] == 200:
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise SystemExit("API did not start")
        with connect() as conn:
            conn.execute("DELETE FROM request_limits")
        assert call("POST", "/v1/auth/register", {"email": email, "display_name": "E2E", "password": password})[0] == 201
        token = call("POST", "/v1/auth/login", {"email": email, "password": password})[1]["access_token"]
        grid = call("GET", "/v1/world/grid")[1]
        assert grid["grid"]["crs"] == "EPSG:32640" and grid["grid"]["cell_metres"] == 6
        with connect() as conn:
            anchors = load_anchors(conn)
        expected = []
        for sector, tile, location in (("ufa", (33, 21), "ufa"), ("mikhailovka", (151, 183), "mikhailovka")):
            status, plot = call("POST", "/v1/world/plots", {"sector_id": sector, "tile_x": tile[0],
                                                           "tile_y": tile[1], "zone": "commercial"}, token)
            assert status == 200, status
            created.append(plot["plot_id"])
            lon, lat = legacy_tile_to_lonlat(anchors[sector], *tile)
            with connect() as conn:
                offset = conn.execute("SELECT world_cell_offset_m FROM world_plots WHERE id=%s",
                                      (plot["plot_id"],)).fetchone()["world_cell_offset_m"]
            expected.append({"plot_id": plot["plot_id"], "sector_id": sector,
                             "world_cell_x": plot["world_cell_x"], "world_cell_y": plot["world_cell_y"],
                             "lon": lon, "lat": lat, "snap_offset_m": offset, "expected_location": location})
        # The legacy sector endpoint still answers with the old local coordinates.
        legacy = call("GET", "/v1/world/sectors/ufa/viewport?min_x=30&min_y=18&max_x=40&max_y=28")[1]
        assert [p["tile_x"] for p in legacy["plots"] if p["id"] == created[0]] == [33]
        result = subprocess.run([godot, "--headless", "--path", str(ROOT / "client"), "-s", "tests/e2e_server.gd",
                                 "--", f"http://127.0.0.1:{PORT}", token, json.dumps(expected)],
                                capture_output=True, text=True, timeout=300)
        print(result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "")
        if result.returncode != 0:
            print(result.stdout[-3000:], result.stderr[-3000:])
        return result.returncode
    finally:
        server.terminate()
        server.wait(timeout=10)
        with connect() as conn:
            conn.execute("DELETE FROM world_plots WHERE id=ANY(%s::uuid[])", (created,))
            account = conn.execute("SELECT id FROM accounts WHERE email=%s", (email,)).fetchone()
            if account:
                conn.execute("DELETE FROM world_plots WHERE created_by_account_id=%s", (account["id"],))
                conn.execute("DELETE FROM wallets WHERE account_id=%s", (account["id"],))
                conn.execute("DELETE FROM sessions WHERE account_id=%s", (account["id"],))
                conn.execute("DELETE FROM security_audit WHERE actor_account_id=%s", (account["id"],))
                conn.execute("DELETE FROM accounts WHERE id=%s", (account["id"],))
            conn.execute("DELETE FROM request_limits")


if __name__ == "__main__":
    raise SystemExit(main())
