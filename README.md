# BASHECO

Persistent economic MMO set in Bashkortostan. Initial server foundation (work in progress).

## Structure
- `docs/GAME_DESIGN.md`: agreed concept
- `docs/ROADMAP.md`: delivery milestones
- `server/sql/001_initial.sql`: draft PostgreSQL schema (not applied)
- `server/basheco/ledger.py`: pure integer-kopeck transfer rules
- `server/tests/test_ledger.py`: unit tests

Run: `cd server && python -m unittest discover -s tests -v`.

No live server, API, PostgreSQL deployment, Godot APK, or VPS changes are part of this commit.
