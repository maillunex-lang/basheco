extends RefCounted
## Read-only real-world background. Never turns OSM buildings into playable plots.
const SOURCES := {
    "ufa": "res://data/ufa_projected_pilot.json",
    "mikhailovka": "res://data/mikhailovka_wide/manifest.json"
}
var metres_per_tile := 4.0  # Visual pilot only; not a surveyed gameplay scale.
var origin_tile := Vector2(25.0, 25.0)
const MAX_FEATURES := 10000
const BUILDING_SPRITES := [preload("res://assets/kenney/building_45.png"), preload("res://assets/kenney/building_55.png"), preload("res://assets/kenney/building_115.png")]
const TREE_SPRITE := preload("res://assets/kenney/detail_10.png")
const MAX_BUILDING_SPRITES := 140
var features: Array = []
var cached_geometry: Array = []
var terrain_segments: Array = []
var terrain_range := Vector2.ZERO
var manifest: Dictionary = {}
var ready := false

func load_pilot(location_id: String = "ufa") -> void:
    ready = false
    origin_tile = Vector2(150.0, 180.0) if location_id == "mikhailovka" else Vector2(25.0, 25.0)
    metres_per_tile = 6.0 if location_id == "mikhailovka" else 4.0
    features.clear()
    cached_geometry.clear()
    terrain_segments.clear()
    terrain_range = Vector2.ZERO
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
    _load_elevation(location_id)
    ready = true

func _load_elevation(location_id: String) -> void:
    var file := FileAccess.open("res://data/" + location_id + "_elevation_pilot.json", FileAccess.READ)
    if file == null:
        return
    var data: Variant = JSON.parse_string(file.get_as_text())
    if typeof(data) != TYPE_DICTIONARY or str(data.get("location_id", "")) != location_id:
        return
    if str(data.get("dataset", "")) != "srtm30m":
        return
    var width := int(data.get("width", 0))
    var height := int(data.get("height", 0))
    var elevations: Array = data.get("elevations_m", [])
    var bbox: Array = data.get("bbox_lonlat", [])
    if width < 2 or height < 2 or elevations.size() != width * height or bbox.size() != 4:
        return
    var origin_lon := float(manifest.get("origin_lon", 0))
    var origin_lat := float(manifest.get("origin_lat", 0))
    var grid: Array = []
    var lowest := INF
    var highest := -INF
    for y in range(height):
        for x in range(width):
            var lon := lerpf(float(bbox[0]), float(bbox[2]), float(x) / float(width - 1))
            var lat := lerpf(float(bbox[1]), float(bbox[3]), float(y) / float(height - 1))
            var east := 6378137.0 * deg_to_rad(lon - origin_lon) * cos(deg_to_rad(origin_lat))
            var south := -6378137.0 * deg_to_rad(lat - origin_lat)
            grid.append({"tile": to_tile([east, south]), "height": float(elevations[y * width + x])})
            lowest = minf(lowest, float(elevations[y * width + x]))
            highest = maxf(highest, float(elevations[y * width + x]))
    terrain_range = Vector2(lowest, highest)
    for level in range(int(ceil(lowest / 10.0)) * 10, int(floor(highest / 10.0)) * 10 + 1, 10):
        for y in range(height - 1):
            for x in range(width - 1):
                var a: Dictionary = grid[y * width + x]
                var b: Dictionary = grid[y * width + x + 1]
                var c: Dictionary = grid[(y + 1) * width + x + 1]
                var d: Dictionary = grid[(y + 1) * width + x]
                var crossings: Array[Vector2] = []
                for edge in [[a, b], [b, c], [c, d], [d, a]]:
                    var h0 := float(edge[0]["height"])
                    var h1 := float(edge[1]["height"])
                    if (h0 < level and h1 >= level) or (h1 < level and h0 >= level):
                        var t := (float(level) - h0) / (h1 - h0)
                        crossings.append((edge[0]["tile"] as Vector2).lerp(edge[1]["tile"], t))
                if crossings.size() == 2:
                    terrain_segments.append([crossings[0], crossings[1]])
                elif crossings.size() == 4:
                    terrain_segments.append([crossings[0], crossings[1]])
                    terrain_segments.append([crossings[2], crossings[3]])

func to_tile(point_m: Array) -> Vector2:
    return origin_tile + Vector2(float(point_m[0]), float(point_m[1])) / metres_per_tile

func render(world: Node2D, visible_bounds: Array[int]) -> void:
    if not ready:
        return
    for segment in terrain_segments:
        var a: Vector2 = segment[0]
        var b: Vector2 = segment[1]
        if maxf(a.x, b.x) < visible_bounds[0] or minf(a.x, b.x) > visible_bounds[2] or maxf(a.y, b.y) < visible_bounds[1] or minf(a.y, b.y) > visible_bounds[3]:
            continue
        world.draw_line(world.project_point(a.x, a.y), world.project_point(b.x, b.y), Color("#91ae86", 0.48), 1.2, true)
    var drawn_buildings := 0
    var drawn_trees := 0
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
                world.draw_polyline(points, Color("#263e46", 0.95), maxf(3.0, 8.0 * world.zoom_level), true)
                world.draw_polyline(points, Color("#9ca6a3", 0.95), maxf(2.0, 5.0 * world.zoom_level), true)
            "building":
                world.draw_polyline(points, Color("#b6c6cb", 0.65), 1.0, true)
                if drawn_buildings < MAX_BUILDING_SPRITES and world.zoom_level >= 0.85:
                    var center := (min_tile + max_tile) * 0.5
                    var anchor: Vector2 = world.project_point(center.x, center.y)
                    var footprint := maxf(max_tile.x - min_tile.x, max_tile.y - min_tile.y)
                    var sprite_width: float = clampf(footprint * 9.0 * world.zoom_level, 22.0, 68.0)
                    var sprite_index := posmod(int(absf(center.x * 17.0 + center.y * 31.0)), BUILDING_SPRITES.size())
                    var texture: Texture2D = BUILDING_SPRITES[sprite_index]
                    var sprite_height: float = sprite_width * float(texture.get_height()) / float(texture.get_width())
                    world.draw_texture_rect(texture, Rect2(anchor.x - sprite_width * 0.5, anchor.y - sprite_height * 0.8, sprite_width, sprite_height), false)
                    drawn_buildings += 1
            "water":
                if points.size() >= 3 and points[0].distance_to(points[points.size() - 1]) < 1.0:
                    world.draw_colored_polygon(points, Color("#327fa8", 0.65))
                world.draw_polyline(points, Color("#4a9cc7", 0.9), 2.0, true)
            "forest":
                if points.size() >= 3 and points[0].distance_to(points[points.size() - 1]) < 1.0:
                    world.draw_colored_polygon(points, Color("#36734c", 0.3))
                world.draw_polyline(points, Color("#4b9164", 0.8), 2.0, true)
                if world.zoom_level >= 0.85 and drawn_trees < 60:
                    var forest_tiles: PackedVector2Array = item["tiles"]
                    for gx in range(int(ceil(min_tile.x / 8.0)), int(floor(max_tile.x / 8.0)) + 1):
                        for gy in range(int(ceil(min_tile.y / 8.0)), int(floor(max_tile.y / 8.0)) + 1):
                            if drawn_trees >= 60:
                                break
                            var tree_tile := Vector2(float(gx) * 8.0, float(gy) * 8.0)
                            if not Geometry2D.is_point_in_polygon(tree_tile, forest_tiles):
                                continue
                            var anchor: Vector2 = world.project_point(tree_tile.x, tree_tile.y)
                            var sprite_width: float = 28.0 * world.zoom_level
                            world.draw_texture_rect(TREE_SPRITE, Rect2(anchor.x - sprite_width * 0.5, anchor.y - sprite_width, sprite_width, sprite_width), false)
                            drawn_trees += 1
            "farmland":
                if points.size() >= 3 and points[0].distance_to(points[points.size() - 1]) < 1.0:
                    world.draw_colored_polygon(points, Color("#a3ad63", 0.24))
                world.draw_polyline(points, Color("#a3ad63", 0.8), 2.0, true)
