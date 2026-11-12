# BASHECO

Persistent economic MMO in Bashkortostan, Russia. Stage 1: **internal backend foundation**.

## Code
- docs/GAME_DESIGN.md: approved scope and rules.
- docs/ROADMAP.md: staged acceptance criteria.
- server/basheco/api.py: internal authentication, companies, wallets and idempotent transfers.
- server/sql/001_initial.sql: PostgreSQL migration with transfer postings.
- compose.yaml: isolated database and localhost-only API.

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

**Safety:** port 4219 binds only to localhost; no Nginx proxy or public registration until rate limits, abuse prevention and integration tests are complete. No premium payments, starter-money minting, production or world simulation yet. Existing site on rikagro.ru must not be modified without backup and validation.
