# BASHECO internal alpha (3–5 testers): combined map + construction milestone

Status: GitHub-only foundation; **not deployed**. No changes to VPS.

## Commits and files
- `server/basheco/world_grid.py`: shared EPSG:32640 projected-metre grid, 6m cells, 64-cell chunks, signed indices.
- `server/tests/test_world_grid.py`: boundary and negative-coordinate tests.
- `server/sql/014_world_object_foundation.sql`: additive object catalog, per-plot objects, globally unique occupied cells, construction event table.
- Earlier `server/basheco/cell_grid.py`: catalog footprints, rotation, placement checks.

## Deployment gates (do not skip)
1. Validate migration 014 and existing migrations on a **disposable database**, then perform data-preserving migration/backfill for legacy `world_buildings`. Keep old API compatible.
2. Import real OSM obstacles for Ufa and Mikhailovka with trusted source/provenance. Implement EPSG:4326 -> EPSG:32640 on server/importer and equivalent coordinates on client. Compare control points. **No separate local origins**.
3. Generate and version buildability masks from verified geometry. Unknown/missing coverage is **not buildable** (fail closed). Enforce municipality and parcel boundaries, zoning and setbacks.
4. Implement authenticated preview and atomic commit endpoints. Validate company/parcel ownership, catalog version, footprint, layer compatibility, geodata restrictions, road access and funds **inside transaction**. Use idempotency and debit wallet atomically. Serialize on plot row; unique occupancy index protects against racing builders.
5. Build Godot touch-first preview, rotation, confirm/cancel, viewport streaming and revalidation on server.
6. Test two sessions placing on the same cell concurrently, retries, disconnects, persistence, restoration, and 3–5 real Android devices. Publish an APK only after checks.

> Update 2026-11-12: gate 2 (shared EPSG:32640 coordinates for server, importer and client, control points, no local origins) and the legacy plot mapping are implemented and tested in GitHub; migrations 014 and 015 were executed on a disposable database. See `docs/STAGE_01_UNIFIED_MAP.md`. Buildability masks and placement API (gates 3–6) are untouched.

## Existing risks
- `world_plots` is still settlement-local, nonnegative and limited to 4096. The new global object grid does not yet change legacy plot coordinates. Do not combine these coordinates in placement API until a backfill/mapping exists.
- `world_buildings.plot_id UNIQUE` still allows one legacy building per plot. New `world_objects` supports many; legacy buildings need occupancy backfill and conflict resolution.
- Existing `create_plot` checks overlap only against other game plots, not real OSM buildings/roads. Disable or guard it before accepting actual tester construction.
- `world_object_cells` unique occupancy is per layer; compatible multi-layer rules and road adjacency need dedicated policy.
- No new building placement API, geographic mask import, payment, live client controls or full-world map has been implemented by this milestone.
- SQL migration and new tests **have not been executed**: GitHub writes are not runtime validation.

## Internal alpha acceptance
- Same global cell identifies the same physical 6×6m square for both cities.
- At least 1×1, 2×1, 2×2, 3×3 and a non-rectangular rotated footprint.
- Multiple objects per plot; no overlap, no off-parcel, no real-geography collision.
- Concurrent builds: one succeeds, competing placement fails, funds are not double charged.
- Player B sees player A's buildings after reconnect; persistent data survives server restart.
- No alteration of unrelated VPS services; separate deployment authorization required.
