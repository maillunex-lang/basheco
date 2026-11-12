extends Node2D
## Offline OSM chunk renderer. OSM outlines are NOT ownership parcels.
const DATA_PATH := "res://data/ufa_center_osm.json"
const CHUNK_COUNT := 4
const MAP_TILES := 28.0
const MARGIN := 2.0
var features: Array = []
var chunks: Dictionary = {}
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
    features = data["features"]
    _index_chunks()
    attribution = Label.new()
    attribution.text = "© OpenStreetMap contributors · ODbL 1.0 · Уфа"
    attribution.add_theme_font_size_override("font_size", 13)
    attribution.add_theme_color_override("font_color", Color("#f3f6f0"))
    attribution.position = Vector2(20, 54)
    attribution.mouse_filter = Control.MOUSE_FILTER_IGNORE
    add_child(attribution)
    queue_redraw()

func _index_chunks() -> void:
    chunks.clear()
    for feature in features:
        var coords: Array = feature.get("coordinates", [])
        if coords.size() < 2:
            continue
        var min_x := CHUNK_COUNT - 1
        var min_y := CHUNK_COUNT - 1
        var max_x := 0
        var max_y := 0
        for coord in coords:
            var grid := _geo_to_grid(coord)
            var cx: int = clampi(int(floor((grid.x - MARGIN) / MAP_TILES * CHUNK_COUNT)), 0, CHUNK_COUNT - 1)
            var cy: int = clampi(int(floor((grid.y - MARGIN) / MAP_TILES * CHUNK_COUNT)), 0, CHUNK_COUNT - 1)
            min_x = mini(min_x, cx)
            max_x = maxi(max_x, cx)
            min_y = mini(min_y, cy)
            max_y = maxi(max_y, cy)
        for cy in range(min_y, max_y + 1):
            for cx in range(min_x, max_x + 1):
                var key := Vector2i(cx, cy)
                if not chunks.has(key):
                    chunks[key] = []
                chunks[key].append(feature)

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
    for key in chunks:
        if not _chunk_visible(key):
            continue
        for feature in chunks[key]:
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
