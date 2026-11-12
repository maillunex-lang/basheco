extends RefCounted
## Read-only real-world background. Never turns OSM buildings into playable plots.
const SOURCES := {
    "ufa": "res://data/ufa_projected_pilot.json",
    "mikhailovka": "res://data/mikhailovka_wide/manifest.json"
}
const METRES_PER_TILE := 4.0  # Visual pilot only; not a surveyed gameplay scale.
const ORIGIN_TILE := Vector2(25.0, 25.0)
const MAX_FEATURES := 10000
var features: Array = []
var cached_geometry: Array = []
var manifest: Dictionary = {}
var ready := false

func load_pilot(location_id: String = "ufa") -> void:
    ready = false
    features.clear()
    cached_geometry.clear()
    manifest.clear()
    if not SOURCES.has(location_id):
        return
    var file := FileAccess.open(SOURCES[location_id], FileAccess.READ)
    if file == null:
        return
    var data: Variant = JSON.parse_string(file.get_as_text())
    if typeof(data) != TYPE_DICTIONARY:
        return
    manifest = data.get("manifest", data)
    if data.has("chunk_paths"):
        for path in data["chunk_paths"]:
            var chunk_file := FileAccess.open(str(path), FileAccess.READ)
            if chunk_file == null:
                features.clear()
                return
            var chunk: Variant = JSON.parse_string(chunk_file.get_as_text())
            if typeof(chunk) != TYPE_DICTIONARY:
                features.clear()
                return
            features.append_array(chunk.get("features", []))
    else:
        features = data.get("features", [])
    if str(manifest.get("location_id", "")) != location_id:
        return
    if str(manifest.get("projection", "")) != "local_equirectangular_metres":
        return
    if features.size() > MAX_FEATURES:
        features.clear()
        return
    for feature in features:
        var coords: Array = feature.get("points_m", [])
        if coords.size() < 2:
            continue
        var tiles := PackedVector2Array()
        var minimum := Vector2(INF, INF)
        var maximum := Vector2(-INF, -INF)
        for coord in coords:
            if typeof(coord) != TYPE_ARRAY or coord.size() != 2:
                tiles.clear()
                break
            var tile := to_tile(coord)
            tiles.append(tile)
            minimum = minimum.min(tile)
            maximum = maximum.max(tile)
        if tiles.size() >= 2:
            cached_geometry.append({"kind": str(feature.get("kind", "")), "tiles": tiles, "minimum": minimum, "maximum": maximum})
    ready = true

func to_tile(point_m: Array) -> Vector2:
    return ORIGIN_TILE + Vector2(float(point_m[0]), float(point_m[1])) / METRES_PER_TILE

func render(world: Node2D, visible_bounds: Array[int]) -> void:
    if not ready:
        return
    for item in cached_geometry:
        var kind: String = item["kind"]
        var min_tile: Vector2 = item["minimum"]
        var max_tile: Vector2 = item["maximum"]
        if max_tile.x < visible_bounds[0] or max_tile.y < visible_bounds[1] or min_tile.x > visible_bounds[2] or min_tile.y > visible_bounds[3]:
            continue
        var points := PackedVector2Array()
        for tile in item["tiles"]:
            points.append(world.project_point(tile.x, tile.y))
        match kind:
            "road":
                world.draw_polyline(points, Color("#dfc79e", 0.85), maxf(1.5, 2.7 * world.zoom_level), true)
            "building":
                # Outline only; no large opaque polygons masking gameplay.
                world.draw_polyline(points, Color("#b6c6cb", 0.72), maxf(1.0, 1.4 * world.zoom_level), true)
            "water":
                if points.size() >= 3 and points[0].distance_to(points[points.size() - 1]) < 1.0:
                    world.draw_colored_polygon(points, Color("#327fa8", 0.65))
                world.draw_polyline(points, Color("#4a9cc7", 0.9), 2.0, true)
            "forest":
                world.draw_polyline(points, Color("#4b9164", 0.8), 2.0, true)
            "farmland":
                world.draw_polyline(points, Color("#a3ad63", 0.8), 2.0, true)
