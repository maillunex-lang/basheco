# BASHECO

Persistent economic MMO in Bashkortostan, Russia.

**Unified map (stage №1):** every settlement lives in one world grid — EPSG:32640, 6 m cells, 64×64-cell chunks, one origin. See docs/STAGE_01_UNIFIED_MAP.md.

## Code
- docs/GAME_DESIGN.md: approved scope and rules.
- docs/ROADMAP.md: staged acceptance criteria.
- server/basheco/api.py: internal authentication, companies, wallets and idempotent transfers.
- server/sql/001_initial.sql: PostgreSQL migration with transfer postings.
- compose.yaml: isolated database and localhost-only API.
- server/basheco/world_grid.py, world_projection.py: authoritative world grid (WGS84 → EPSG:32640 → cell → chunk).
- server/basheco/osm_source.py, world_atlas.py, server/geodata/: real OSM sources → client/data/world atlas.
- server/basheco/world_compat.py, sql/015_world_grid_link.sql: legacy settlement-local plots placed on the world grid.
- client/: Godot 4 client, one seamless map (see client/README.md).

## Running locally on a dedicated test host
Create an untracked .env with a random BASHECO_DB_PASSWORD, then run:
```sh
docker compose config --quiet
docker compose up -d --build
docker compose ps
curl -fsS http://127.0.0.1:4219/health
docker compose run --rm api python -m unittest discover -s tests -v
```
For unit tests, use `cd server && python -m unittest discover -s tests -v` with dependencies installed.
Integration tests need `BASHECO_TEST_DATABASE_URL` pointing at a disposable database named `basheco_integration_test`.
Client tests: `godot --headless --path client --import`, then `-s tests/grid_parity.gd`, `-s tests/smoke.gd`, `-s tests/streaming_soak.gd`.
Server + client end to end: `python server/tests/e2e_world_client.py`.

**Safety:** port 4219 binds only to localhost; no Nginx proxy or public registration until rate limits, abuse prevention and integration tests are complete. No premium payments, starter-money minting, production or world simulation yet. Existing site on rikagro.ru must not be modified without backup and validation.
