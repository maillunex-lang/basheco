# BASHECO roadmap

## Stage 1: server foundation (in progress)
- [x] Approved design and milestones documented
- [x] Draft PostgreSQL accounts, companies, wallets and transfer tables
- [x] Pure integer-kopeck transfer validation and unit tests
- [ ] Choose API framework, implement authentication and authorization
- [ ] Transactional DB ledger, idempotency, integration tests on PostgreSQL
- [ ] Background jobs, recovery, observability and backup testing

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
