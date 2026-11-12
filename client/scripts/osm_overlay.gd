extends Node2D
## OSM demonstration overlay. Coordinates are NOT legal cadastral parcels.
const DATA_PATH := "res://data/ufa_center_osm.json"
var features: Array = []
var bounds := [55.9710, 54.7377, 55.9730, 54.7395]
var parent_world: Node2D
var visible_layer := true

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
    queue_redraw()

func _process(_delta: float) -> void:
    if Input.is_key_pressed(KEY_G) and not _key_down:
        visible_layer = not visible_layer
        queue_redraw()
    _key_down = Input.is_key_pressed(KEY_G)
var _key_down := false

func _geo_to_screen(coord: Array) -> Vector2:
    var x := (float(coord[0]) - float(bounds[0])) / (float(bounds[2]) - float(bounds[0])) * 28.0 + 2.0
    var y := (float(bounds[3]) - float(coord[1])) / (float(bounds[3]) - float(bounds[1])) * 28.0 + 2.0
    return parent_world.project_point(x, y)

func _draw() -> void:
    if not visible_layer:
        return
    for feature in features:
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
