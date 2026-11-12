# BASHECO Godot client

Godot 4 project. Run `godot --headless --path client --editor --quit` for import and script parse, then `godot --path client` for a graphical client.

The 32×32 map is a **fictional prototype**, not real Ufa geography. All six plots are local preview fixtures, not yet downloaded from the API. Mouse wheel zooms, middle mouse drags, left click selects a plot.

Next: authenticated API client, touch controls, server-driven plots, licensed OSM geometry, Android export.

## API integration

`World.connect_to_server(url, bearer_token)` requests the authenticated sector from
`GET /v1/world/sectors/ufa-prototype-01` and replaces preview plots only after validating the response.
The token stays in memory. Non-local connections require HTTPS. The game does not yet
provide a login screen or public API endpoint; no credentials are stored in project files.

Godot 4.8 beta3 was used for headless editor import and five-frame runtime smoke tests.
A stable Godot release is preferable for Android exports.


## Verified Android preview, 12 November 2026

- Real OSM snapshot: `data/ufa_center_osm.json`, 17 roads and 6 building outlines, © OpenStreetMap contributors, ODbL 1.0. The importer is `../tools/import_osm.py`. This is a tiny central-Ufa bounding box, not all of Ufa. Coordinates are projected to an approximate local 2.5D preview, not geodetically accurate parcels.
- Mobile: one-finger pan, two-finger pinch, tap selection; desktop: mouse wheel zoom, middle-button pan, left-click selection; G toggles the OSM overlay.
- Russian login panel uses an in-memory token; the **public API is not exposed** yet. Choose **Посмотреть карту без входа** to try the offline preview. The screen defaults to `https://rikagro.ru/basheco/api`, which is a reserved future path, not an active API endpoint.
- Built with Godot 4.8 beta3, Android SDK 36 and arm64-v8a debug template. Debug APK signed and verified with `apksigner`, package `org.basheco.game`, version `0.1.0`. This is a developer-signed debug APK, **not a release-signed app**.
- Headless test: `godot --headless --path client --script res://tests/smoke.gd` verifies scene, six prototype plots, OSM layer, plot selection and touch pan.
- Android install/runtime on a physical device has **not been tested**; no AAB, store release, automatic updater, registration flow or online multiplayer yet.
- HTTPS preview download: https://rikagro.ru/downloads/BASHECO-test.apk . The website labels it as an offline early demo.

## Export locally

Open `client/project.godot` with Godot 4.8 beta3, install the matching Android export templates and Android SDK/JDK, then export preset `Android` as a debug APK. Keep debug keystores private and do not distribute them with the repository.
