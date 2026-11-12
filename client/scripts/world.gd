extends Node2D
## Isometric prototype, deliberately synthetic. Server remains authoritative.
const GRID_SIZE := 32
const TILE_W := 64.0
const TILE_H := 32.0
const ZONES := {
    "commercial": Color("#e0ad57"),
    "industrial": Color("#5f93a9"),
    "agricultural": Color("#72b883")
}
var plots: Array[Dictionary] = [
    {"tile_x": 2, "tile_y": 2, "width_tiles": 5, "height_tiles": 5, "zone": "commercial"},
    {"tile_x": 9, "tile_y": 2, "width_tiles": 5, "height_tiles": 5, "zone": "commercial"},
    {"tile_x": 2, "tile_y": 10, "width_tiles": 6, "height_tiles": 6, "zone": "industrial"},
    {"tile_x": 11, "tile_y": 10, "width_tiles": 6, "height_tiles": 6, "zone": "industrial"},
    {"tile_x": 2, "tile_y": 20, "width_tiles": 6, "height_tiles": 6, "zone": "agricultural"},
    {"tile_x": 11, "tile_y": 20, "width_tiles": 6, "height_tiles": 6, "zone": "agricultural"}
]
var zoom_level := 0.85
var camera_offset := Vector2(650, 90)
var dragging := false
var touches: Dictionary = {}
var pinch_distance := 0.0
var selected_plot := -1
var hud: Label

func _ready() -> void:
    hud = Label.new()
    hud.position = Vector2(20, 16)
    hud.add_theme_color_override("font_color", Color.WHITE)
    hud.add_theme_font_size_override("font_size", 19)
    add_child(hud)
    _update_hud()
    $API.sector_loaded.connect(_on_sector_loaded)
    $API.request_failed.connect(_on_api_error)
    queue_redraw()

func connect_to_server(url: String, token: String) -> void:
    $API.configure(url, token)
    $API.load_sector()

func _on_sector_loaded(data: Dictionary) -> void:
    var received: Array = data["plots"]
    var verified: Array[Dictionary] = []
    for item in received:
        if typeof(item) != TYPE_DICTIONARY:
            return
        if not item.has("tile_x") or not item.has("tile_y") or not item.has("zone") or not item.has("width_tiles") or not item.has("height_tiles"):
            return
        verified.append(item)
    plots = verified
    selected_plot = -1
    _update_hud()
    queue_redraw()

func _on_api_error(_status: int, message: String) -> void:
    hud.text = "BASHECO | " + message

func iso(x: float, y: float) -> Vector2:
    return Vector2((x - y) * TILE_W * 0.5, (x + y) * TILE_H * 0.5)

func project_point(x: float, y: float) -> Vector2:
    return iso(x, y) * zoom_level + camera_offset

func _draw() -> void:
    draw_rect(Rect2(Vector2.ZERO, get_viewport_rect().size), Color("#121e29"))
    for y in range(GRID_SIZE):
        for x in range(GRID_SIZE):
            _tile(x, y, Color("#263e42") if (x + y) % 2 == 0 else Color("#294449"))
    for i in range(plots.size()):
        var p: Dictionary = plots[i]
        var color: Color = ZONES.get(str(p["zone"]), Color.GRAY)
        if i == selected_plot:
            color = color.lightened(0.32)
        for dy in range(int(p["height_tiles"])):
            for dx in range(int(p["width_tiles"])):
                _tile(int(p["tile_x"]) + dx, int(p["tile_y"]) + dy, color)
        var center := project_point(float(p["tile_x"]) + float(p["width_tiles"]) / 2.0,
            float(p["tile_y"]) + float(p["height_tiles"]) / 2.0)
        draw_circle(center, 5.0, Color.WHITE)

func _tile(x: int, y: int, color: Color) -> void:
    var corners := PackedVector2Array([
        project_point(x, y), project_point(x + 1, y),
        project_point(x + 1, y + 1), project_point(x, y + 1)
    ])
    draw_colored_polygon(corners, color)
    draw_polyline(PackedVector2Array([corners[0],corners[1],corners[2],corners[3],corners[0]]),
        Color("#142a32"), 1.0)

func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventMouseButton:
        if event.button_index == MOUSE_BUTTON_WHEEL_UP and event.pressed:
            zoom_level = minf(2.0, zoom_level * 1.12)
        elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN and event.pressed:
            zoom_level = maxf(0.3, zoom_level / 1.12)
        elif event.button_index == MOUSE_BUTTON_MIDDLE:
            dragging = event.pressed
        elif event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
            _select_at(event.position)
        queue_redraw()
    elif event is InputEventMouseMotion and dragging:
        camera_offset += event.relative
        elif event is InputEventScreenTouch:
        if event.pressed:
            touches[event.index] = event.position
        else:
            var was_tap := touches.size() == 1 and touches.has(event.index)
            var start: Vector2 = touches.get(event.index, event.position)
            touches.erase(event.index)
            if was_tap and start.distance_to(event.position) < 18.0:
                _select_at(event.position)
        if touches.size() != 2:
            pinch_distance = 0.0
    elif event is InputEventScreenDrag:
        var previous: Vector2 = touches.get(event.index, event.position)
        touches[event.index] = event.position
        if touches.size() == 1:
            camera_offset += event.position - previous
        elif touches.size() == 2:
            var positions: Array = touches.values()
            var distance: float = positions[0].distance_to(positions[1])
            if pinch_distance > 0.0:
                zoom_level = clampf(zoom_level * distance / pinch_distance, 0.3, 2.0)
            pinch_distance = distance
        queue_redraw()
    $OSM.refresh()
    queue_redraw()

func _select_at(point: Vector2) -> void:
    var local := (point - camera_offset) / zoom_level
    var tx := local.x / TILE_W + local.y / TILE_H
    var ty := local.y / TILE_H - local.x / TILE_W
    selected_plot = -1
    for i in range(plots.size()):
        var p: Dictionary = plots[i]
        if tx >= float(p["tile_x"]) and tx < float(p["tile_x"] + p["width_tiles"]) and \
            ty >= float(p["tile_y"]) and ty < float(p["tile_y"] + p["height_tiles"]):
            selected_plot = i
            break
    _update_hud()
    $OSM.refresh()
    queue_redraw()

func _update_hud() -> void:
    var suffix := "Выберите участок"
    if selected_plot >= 0:
        var p: Dictionary = plots[selected_plot]
        suffix = "Участок %d · %s" % [selected_plot + 1, str(p["zone"])]
    hud.text = "BASHECO  |  Уфа · тестовый квартал  |  %s\nКолесо: масштаб · Средняя кнопка: перемещение" % suffix
