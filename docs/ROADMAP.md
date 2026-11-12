# BASHECO roadmap

## Stage 1: server foundation (in progress)
- [x] Approved design and milestones documented
- [x] Draft PostgreSQL accounts, companies, wallets and transfer tables
- [x] Pure integer-kopeck transfer validation and unit tests
- [ ] Choose API framework, implement authentication and authorization
- [ ] Transactional DB ledger, idempotency, integration tests on PostgreSQL
- [ ] Background jobs, recovery, observability and backup testing

## Unified map checkpoint (2026-11-12)
One world grid for every settlement (EPSG:32640, 6 m cells, 64×64 chunks), real OSM atlas, seamless Godot map and legacy plot mapping are implemented and tested in GitHub; not deployed. Details and limits: `docs/STAGE_01_UNIFIED_MAP.md`.

## Stage 2
Godot 4 client, touch controls, Ufa test district, geodata import.

## Stage 3
Production recipes, goods batches, warehouses, player/system trade and offline catch-up.

## Stage 4
Two-player shared state, contracts, property, rate limiting and reconnect.

## Stage 5
Android APK, web client, onboarding, version manifest, load testing.

No production-backend or deployment claims before API, DB, integration and recovery tests pass.


### Stage 1 deployment notes (2026-11-12)
- Implementation added: FastAPI routes, Argon2 password hashing, opaque hashed sessions, PostgreSQL migrations and idempotent double-entry transfer postings.
- Local-only Docker Compose declared; integration and load tests must be run before any public ingress.
- Treasury and starting-money issuance deliberately deferred, so new wallets start at 0.
- Next: verify database/migration, authentication and two-user transfer integration tests; enforce rate limiting and add full backup/restore drills.


## World prototype checkpoint (2026-11-12)
- Implemented migration `004_world_prototype.sql`: one **fictional**, 32×32 tile Ufa test sector, 6 plots and 3 zoning-matched building types.
- Authenticated `GET /v1/world/sectors/ufa-prototype-01` and `POST /v1/world/buildings`.
- Construction is transactional and plot row is locked; only a company owner can build, one plot can hold one building, zone compatibility is enforced.
- Free claiming is **prototype-only**. Real-world parcels, property rights, geodata import, pricing, construction duration, resources, and world rendering are not implemented.
- 21 tests passed in disposable PostgreSQL including concurrent claims; migration applied on VPS. Existing website remains untouched.
- Next: source and validate OSM data, define tiles-to-geography pipeline, then Godot client map rendering. Do not claim this synthetic grid represents actual Ufa streets.
