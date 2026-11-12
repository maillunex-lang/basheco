extends RefCounted
## Read-only real-world background. Never turns OSM buildings into playable plots.
const SOURCE := "res://data/ufa_projected_pilot.json"
const METRES_PER_TILE := 4.0  # Visual pilot only; not a surveyed gameplay scale.
const ORIGIN_TILE := Vector2(25.0, 25.0)
const MAX_FEATURES := 10000
var features: Array = []
var manifest: Dictionary = {}
var ready := false

func load_pilot() -> void:
    var file := FileAccess.open(SOURCE, FileAccess.READ)
    if file == null:
        return
    var data: Variant = JSON.parse_string(file.get_as_text())
    if typeof(data) != TYPE_DICTIONARY:
        return
    manifest = data.get("manifest", {})
    if str(manifest.get("projection", "")) != "local_equirectangular_metres":
        return
    features = data.get("features", [])
    if features.size() > MAX_FEATURES:
        features.clear()
        return
    ready = true

func to_tile(point_m: Array) -> Vector2:
    return ORIGIN_TILE + Vector2(float(point_m[0]), float(point_m[1])) / METRES_PER_TILE

func render(world: Node2D, visible_bounds: Array[int]) -> void:
    if not ready:
        return
    for feature in features:
        var kind := str(feature.get("kind", ""))
        var coords: Array = feature.get("points_m", [])
        if coords.size() < 2:
            continue
        var points := PackedVector2Array()
        var min_tile := Vector2(INF, INF)
        var max_tile := Vector2(-INF, -INF)
        for coord in coords:
            if typeof(coord) != TYPE_ARRAY or coord.size() != 2:
                points.clear()
                break
            var tile := to_tile(coord)
            min_tile = min_tile.min(tile)
            max_tile = max_tile.max(tile)
            points.append(world.project_point(tile.x, tile.y))
        if points.size() < 2:
            continue
        if max_tile.x < visible_bounds[0] or max_tile.y < visible_bounds[1] or min_tile.x > visible_bounds[2] or min_tile.y > visible_bounds[3]:
            continue
        match kind:
            "road":
                world.draw_polyline(points, Color("#dfc79e", 0.85), maxf(1.5, 2.7 * world.zoom_level), true)
            "building":
                # Outline only; no large opaque polygons masking gameplay.
                world.draw_polyline(points, Color("#b6c6cb", 0.72), maxf(1.0, 1.4 * world.zoom_level), true)
            "water":
                world.draw_polyline(points, Color("#4a9cc7", 0.9), 2.0, true)
            "forest":
                world.draw_polyline(points, Color("#4b9164", 0.8), 2.0, true)
            "farmland":
                world.draw_polyline(points, Color("#a3ad63", 0.8), 2.0, true)
