extends Node2D
## Offline OSM chunk renderer. OSM outlines are NOT ownership parcels.
const DATA_PATH := "res://data/ufa_chunks/manifest.json"
const CHUNK_COUNT := 4
const MAP_TILES := 28.0
const MARGIN := 2.0
var features: Array = []
var chunks: Dictionary = {}
var chunk_paths: Dictionary = {}
var loaded_chunks: Dictionary = {}
var bounds := [55.9710, 54.7377, 55.9730, 54.7395]
var parent_world: Node2D
var visible_layer := true
var _key_down := false
var attribution: Label

func _ready() -> void:
    parent_world = get_parent()
    var file := FileAccess.open(DATA_PATH, FileAccess.READ)
    if file == null:
        push_warning("OSM snapshot unavailable")
        return
    var data: Variant = JSON.parse_string(file.get_as_text())
    if typeof(data) != TYPE_DICTIONARY or not data.has("features"):
        return
    bounds = data.get("bbox", bounds)
    for chunk in data.get("chunks", []):
        chunk_paths[Vector2i(int(chunk["x"]), int(chunk["y"]))] = str(chunk["path"])
    _load_chunk(Vector2i(0, 0))
    attribution = Label.new()
    attribution.text = "© OpenStreetMap contributors · ODbL 1.0 · Уфа"
    attribution.add_theme_font_size_override("font_size", 13)
    attribution.add_theme_color_override("font_color", Color("#f3f6f0"))
    attribution.position = Vector2(20, 54)
    attribution.mouse_filter = Control.MOUSE_FILTER_IGNORE
    add_child(attribution)
    queue_redraw()

func _load_chunk(key: Vector2i) -> void:
    if loaded_chunks.has(key) or not chunk_paths.has(key):
        return
    var file := FileAccess.open(chunk_paths[key], FileAccess.READ)
    if file == null:
        push_warning("OSM chunk unavailable: " + str(key))
        return
    var data: Variant = JSON.parse_string(file.get_as_text())
    if typeof(data) != TYPE_DICTIONARY:
        return
    chunks[key] = data.get("features", [])
    loaded_chunks[key] = true
    if features.is_empty():
        features = chunks[key]

func _geo_to_grid(coord: Array) -> Vector2:
    var mid_lat: float = deg_to_rad((float(bounds[1]) + float(bounds[3])) * 0.5)
    var dx: float = (float(coord[0]) - float(bounds[0])) * cos(mid_lat)
    var span_x: float = (float(bounds[2]) - float(bounds[0])) * cos(mid_lat)
    var dy: float = float(bounds[3]) - float(coord[1])
    var span_y: float = float(bounds[3]) - float(bounds[1])
    return Vector2(dx / maxf(span_x, 0.000001), dy / maxf(span_y, 0.000001)) * MAP_TILES + Vector2(MARGIN, MARGIN)

func _geo_to_screen(coord: Array) -> Vector2:
    var grid := _geo_to_grid(coord)
    return parent_world.project_point(grid.x, grid.y)

func _process(_delta: float) -> void:
    if Input.is_key_pressed(KEY_G) and not _key_down:
        visible_layer = not visible_layer
        queue_redraw()
    _key_down = Input.is_key_pressed(KEY_G)

func _chunk_visible(key: Vector2i) -> bool:
    var x0 := MARGIN + float(key.x) * MAP_TILES / CHUNK_COUNT
    var y0 := MARGIN + float(key.y) * MAP_TILES / CHUNK_COUNT
    var step := MAP_TILES / CHUNK_COUNT
    var points := [
        parent_world.project_point(x0, y0),
        parent_world.project_point(x0 + step, y0),
        parent_world.project_point(x0 + step, y0 + step),
        parent_world.project_point(x0, y0 + step)
    ]
    var min_pos: Vector2 = points[0]
    var max_pos: Vector2 = points[0]
    for p in points:
        min_pos = min_pos.min(p)
        max_pos = max_pos.max(p)
    var viewport := Rect2(Vector2.ZERO, get_viewport_rect().size).grow(160.0)
    return viewport.intersects(Rect2(min_pos, max_pos - min_pos))

func _draw() -> void:
    if not visible_layer:
        return
    var drawn: Dictionary = {}
    for key in chunk_paths:
        if not _chunk_visible(key):
            continue
        _load_chunk(key)
        for feature in chunks.get(key, []):
            var id := str(feature.get("osm_id", ""))
            if drawn.has(id):
                continue
            drawn[id] = true
            var pts := PackedVector2Array()
            for coord in feature.get("coordinates", []):
                pts.append(_geo_to_screen(coord))
            if pts.size() < 2:
                continue
            if feature.get("kind") == "road":
                draw_polyline(pts, Color("#d5c4a1"), 3.0, true)
            elif feature.get("kind") == "building" and pts.size() >= 4:
                draw_colored_polygon(pts, Color("#a8abb2"))
                draw_polyline(pts, Color("#394852"), 1.0, true)

func refresh() -> void:
    queue_redraw()
