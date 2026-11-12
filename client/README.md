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
