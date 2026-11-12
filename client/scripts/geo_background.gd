extends RefCounted
## Read-only real-world background. Never turns OSM buildings into playable plots.
const SOURCES := {
    "ufa": "res://data/spatial/ufa/manifest.json",
    "mikhailovka": "res://data/spatial/mikhailovka/manifest.json"
}
var metres_per_tile := 6.0  # Visual pilot only; not a surveyed gameplay scale.
var origin_tile := Vector2(25.0, 25.0)
const MAX_FEATURES := 10000
const BUILDING_SPRITES := [preload("res://assets/kenney/building_45.png"), preload("res://assets/kenney/building_55.png"), preload("res://assets/kenney/building_115.png")]
const TREE_SPRITE := preload("res://assets/kenney/detail_10.png")
const MAX_BUILDING_SPRITES := 140
const GEOGRAPHY_CHUNK_TILES := 48
const MAX_ACTIVE_CHUNKS := 48
var geometry_index: Dictionary = {}
var spatial_paths: Dictionary = {}
var spatial_loaded: Dictionary = {}
var active_chunk_ids: Array[Vector2i] = []
var features: Array = []
var cached_geometry: Array = []
var terrain_segments: Array = []
var terrain_range := Vector2.ZERO
var settlement_boundary: Dictionary = {}
var boundary_rings: Array = []
var manifest: Dictionary = {}
var ready := false

func load_pilot(location_id: String = "ufa") -> void:
    ready = false
    origin_tile = Vector2(150.0, 180.0) if location_id == "mikhailovka" else Vector2(25.0, 25.0)
    metres_per_tile = 6.0
    features.clear()
    cached_geometry.clear()
    geometry_index.clear()
    spatial_paths.clear()
    spatial_loaded.clear()
    active_chunk_ids.clear()
    terrain_segments.clear()
    settlement_boundary.clear()
    boundary_rings.clear()
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
    if data.has("spatial_chunks"):
        for entry in data["spatial_chunks"]:
            spatial_paths[Vector2i(int(entry["x"]), int(entry["y"]))] = str(entry["path"])
    elif data.has("chunk_paths"):
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
    _rebuild_geometry()
    _load_elevation(location_id)
    _load_boundary(location_id)
    ready = true
    if not spatial_paths.is_empty():
        var x := int(origin_tile.x)
        var y := int(origin_tile.y)
        _refresh_spatial_chunks([x - 30, y - 30, x + 30, y + 30])

func _rebuild_geometry() -> void:
    cached_geometry.clear()
    geometry_index.clear()
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
            var feature_index := cached_geometry.size()
            cached_geometry.append({"kind": str(feature.get("kind", "")), "tiles": tiles, "minimum": minimum, "maximum": maximum})
            var left := floori(minimum.x / GEOGRAPHY_CHUNK_TILES)
            var top := floori(minimum.y / GEOGRAPHY_CHUNK_TILES)
            var right := floori(maximum.x / GEOGRAPHY_CHUNK_TILES)
            var bottom := floori(maximum.y / GEOGRAPHY_CHUNK_TILES)
            # Guard against malformed huge geometry occupying every chunk.
            if (right - left + 1) * (bottom - top + 1) > 256:
                continue
            for cy in range(top, bottom + 1):
                for cx in range(left, right + 1):
                    var key := Vector2i(cx, cy)
                    if not geometry_index.has(key):
                        geometry_index[key] = []
                    geometry_index[key].append(feature_index)

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

func tile_extent() -> Rect2:
    if settlement_boundary.has("bbox_lonlat"):
        var bounds: Array = settlement_boundary["bbox_lonlat"]
        if bounds.size() == 4:
            var a := lonlat_to_tile(float(bounds[0]), float(bounds[1]))
            var b := lonlat_to_tile(float(bounds[2]), float(bounds[3]))
            return Rect2(a.min(b), (b - a).abs())
    var metres: Array = manifest.get("bounds_m", [])
    if metres.size() != 4:
        return Rect2(origin_tile - Vector2(12, 12), Vector2(24, 24))
    var a := to_tile([float(metres[0]), float(metres[1])])
    var b := to_tile([float(metres[2]), float(metres[3])])
    return Rect2(a.min(b), (b - a).abs())

func lonlat_to_tile(lon: float, lat: float) -> Vector2:
    var origin_lon := float(manifest.get("origin_lon", 0.0))
    var origin_lat := float(manifest.get("origin_lat", 0.0))
    var east := 6378137.0 * deg_to_rad(lon - origin_lon) * cos(deg_to_rad(origin_lat))
    var south := -6378137.0 * deg_to_rad(lat - origin_lat)
    return to_tile([east, south])

func _load_boundary(location_id: String) -> void:
    var file := FileAccess.open("res://data/" + location_id + "_boundary.json", FileAccess.READ)
    if file == null:
        return
    var data: Variant = JSON.parse_string(file.get_as_text())
    if typeof(data) != TYPE_DICTIONARY or str(data.get("location_id", "")) != location_id:
        return
    if str(data.get("geometry", {}).get("type", "")) != "MultiPolygon":
        return
    settlement_boundary = data
    for polygon in data["geometry"]["coordinates"]:
        for ring in polygon:
            var points := PackedVector2Array()
            for coordinate in ring:
                points.append(lonlat_to_tile(float(coordinate[0]), float(coordinate[1])))
            if points.size() >= 3:
                boundary_rings.append(points)

func update_visible_chunks(bounds: Array[int]) -> void:
    if not spatial_paths.is_empty():
        _refresh_spatial_chunks(bounds)
        return
    active_chunk_ids.clear()
    var left := floori(float(bounds[0]) / GEOGRAPHY_CHUNK_TILES) - 1
    var top := floori(float(bounds[1]) / GEOGRAPHY_CHUNK_TILES) - 1
    var right := floori(float(bounds[2] - 1) / GEOGRAPHY_CHUNK_TILES) + 1
    var bottom := floori(float(bounds[3] - 1) / GEOGRAPHY_CHUNK_TILES) + 1
    var center := Vector2((left + right) * 0.5, (top + bottom) * 0.5)
    var candidates: Array[Vector2i] = []
    for cy in range(top, bottom + 1):
        for cx in range(left, right + 1):
            var key := Vector2i(cx, cy)
            if geometry_index.has(key):
                candidates.append(key)
    candidates.sort_custom(func(a: Vector2i, b: Vector2i) -> bool:
        return Vector2(a).distance_squared_to(center) < Vector2(b).distance_squared_to(center))
    for i in range(mini(candidates.size(), MAX_ACTIVE_CHUNKS)):
        active_chunk_ids.append(candidates[i])

func _refresh_spatial_chunks(bounds: Array[int]) -> void:
    # Chunk keys are local projected metres; rendering uses one shared 6 m/tile scale.
    var step := 256.0 / metres_per_tile
    var left := floori((float(bounds[0]) - origin_tile.x) / step) - 1
    var top := floori((float(bounds[1]) - origin_tile.y) / step) - 1
    var right := floori((float(bounds[2]) - origin_tile.x) / step) + 1
    var bottom := floori((float(bounds[3]) - origin_tile.y) / step) + 1
    var center := Vector2((left + right) * 0.5, (top + bottom) * 0.5)
    var desired: Array[Vector2i] = []
    for cy in range(top, bottom + 1):
        for cx in range(left, right + 1):
            var key := Vector2i(cx, cy)
            if spatial_paths.has(key):
                desired.append(key)
    desired.sort_custom(func(a: Vector2i, b: Vector2i) -> bool:
        return Vector2(a).distance_squared_to(center) < Vector2(b).distance_squared_to(center))
    if desired.size() > MAX_ACTIVE_CHUNKS:
        desired.resize(MAX_ACTIVE_CHUNKS)
    var changed := desired.size() != active_chunk_ids.size()
    if not changed:
        for key in desired:
            if not spatial_loaded.has(key):
                changed = true
                break
    if not changed:
        return
    for key in spatial_loaded.keys():
        if not desired.has(key):
            spatial_loaded.erase(key)
    for key in desired:
        if spatial_loaded.has(key):
            continue
        var file := FileAccess.open(spatial_paths[key], FileAccess.READ)
        if file == null:
            push_warning("Missing geography chunk: " + str(key))
            continue
        var chunk: Variant = JSON.parse_string(file.get_as_text())
        if typeof(chunk) == TYPE_DICTIONARY:
            spatial_loaded[key] = chunk.get("features", [])
    active_chunk_ids = desired
    features.clear()
    var unique: Dictionary = {}
    for key in desired:
        for feature in spatial_loaded.get(key, []):
            var id := int(feature.get("id", -1))
            if not unique.has(id):
                unique[id] = true
                features.append(feature)
    _rebuild_geometry()

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
    for ring in boundary_rings:
        for j in range(ring.size() - 1):
            var a: Vector2 = ring[j]
            var b: Vector2 = ring[j + 1]
            if maxf(a.x, b.x) < visible_bounds[0] or minf(a.x, b.x) > visible_bounds[2] or maxf(a.y, b.y) < visible_bounds[1] or minf(a.y, b.y) > visible_bounds[3]:
                continue
            world.draw_line(world.project_point(a.x, a.y), world.project_point(b.x, b.y), Color("#e2bf72", 0.9), 2.0, true)
    var drawn_buildings := 0
    var drawn_trees := 0
    update_visible_chunks(visible_bounds)
    var visible_features: Dictionary = {}
    if not spatial_paths.is_empty():
        for feature_index in range(cached_geometry.size()):
            visible_features[feature_index] = true
    else:
        for key in active_chunk_ids:
            for feature_index in geometry_index[key]:
                visible_features[feature_index] = true
    for feature_index in visible_features:
        var item: Dictionary = cached_geometry[feature_index]
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
                    _draw_safe_polygon(world, points, Color("#327fa8", 0.65))
                world.draw_polyline(points, Color("#4a9cc7", 0.9), 2.0, true)
            "forest":
                if points.size() >= 3 and points[0].distance_to(points[points.size() - 1]) < 1.0:
                    _draw_safe_polygon(world, points, Color("#36734c", 0.3))
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
                    _draw_safe_polygon(world, points, Color("#a3ad63", 0.24))
                world.draw_polyline(points, Color("#a3ad63", 0.8), 2.0, true)

func _draw_safe_polygon(world: Node2D, points: PackedVector2Array, color: Color) -> void:
    # OSM boundaries can self-intersect or repeat vertices. Never send invalid
    # polygons to the canvas renderer (which logs triangulation errors).
    var ring := points.duplicate()
    if ring.size() > 2 and ring[0].distance_to(ring[ring.size() - 1]) < 1.0:
        ring.resize(ring.size() - 1)
    if ring.size() < 3 or Geometry2D.triangulate_polygon(ring).is_empty():
        return
    world.draw_colored_polygon(ring, color)
