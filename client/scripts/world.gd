extends Node2D
## Isometric prototype, deliberately synthetic. Server remains authoritative.
const INITIAL_GRID_SIZE := 200
var world_width := INITIAL_GRID_SIZE
var world_height := INITIAL_GRID_SIZE
const MIN_ZOOM := 0.65
const MAX_ZOOM := 2.4
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
var zoom_level := 1.15
var camera_offset := Vector2.ZERO
var camera_initialized := false
var world_visible := false
var dragging := false
var touches: Dictionary = {}
var pinch_distance := 0.0
var selected_plot := -1
const ZONE_ICONS := {
    "commercial": preload("res://assets/icons/shop.svg"),
    "industrial": preload("res://assets/icons/workshop.svg"),
    "agricultural": preload("res://assets/icons/greenhouse.svg")
}
var hud: Label

func _ready() -> void:
    _focus_on_district()
    hud = Label.new()
    hud.position = Vector2(18, 12)
    hud.add_theme_color_override("font_color", Color.WHITE)
    hud.add_theme_font_size_override("font_size", 19)
    add_child(hud)
    _update_hud()
    $API.sector_loaded.connect(_on_sector_loaded)
    $API.request_failed.connect(_on_api_error)
    get_viewport().size_changed.connect(_on_viewport_resized)
    queue_redraw()

func _focus_on_district() -> void:
    camera_offset = get_viewport_rect().size * 0.5 - iso(12.0, 12.0) * zoom_level
    camera_initialized = true
    _camera_changed()

func zoom_at(screen_point: Vector2, factor: float) -> void:
    var old_zoom := zoom_level
    zoom_level = clampf(old_zoom * factor, MIN_ZOOM, MAX_ZOOM)
    camera_offset = screen_point - (screen_point - camera_offset) * (zoom_level / old_zoom)
    _camera_changed()

func _clamp_camera() -> void:
    var size := get_viewport_rect().size
    var center := size * 0.5
    var margin := size * 0.8
    var corners := [
        iso(0.0, 0.0) * zoom_level,
        iso(float(world_width), 0.0) * zoom_level,
        iso(0.0, float(world_height)) * zoom_level,
        iso(float(world_width), float(world_height)) * zoom_level
    ]
    var minimum: Vector2 = corners[0]
    var maximum: Vector2 = corners[0]
    for corner in corners:
        minimum = minimum.min(corner)
        maximum = maximum.max(corner)
    camera_offset.x = clampf(camera_offset.x, center.x - maximum.x - margin.x, center.x - minimum.x + margin.x)
    camera_offset.y = clampf(camera_offset.y, center.y - maximum.y - margin.y, center.y - minimum.y + margin.y)

func _camera_changed() -> void:
    _clamp_camera()
    if has_node("OSM") and is_node_ready():
        $OSM.refresh()
    queue_redraw()

func _on_viewport_resized() -> void:
    if camera_initialized and not world_visible:
        _focus_on_district()
    _camera_changed()

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
    world_visible = true
    var sector: Dictionary = data.get("sector", {})
    world_width = maxi(INITIAL_GRID_SIZE, int(sector.get("width_tiles", INITIAL_GRID_SIZE)))
    world_height = maxi(INITIAL_GRID_SIZE, int(sector.get("height_tiles", INITIAL_GRID_SIZE)))
    selected_plot = -1
    _update_hud()
    _camera_changed()

func _on_api_error(_status: int, message: String) -> void:
    hud.text = "BASHECO | " + message

func iso(x: float, y: float) -> Vector2:
    return Vector2((x - y) * TILE_W * 0.5, (x + y) * TILE_H * 0.5)

func project_point(x: float, y: float) -> Vector2:
    return iso(x, y) * zoom_level + camera_offset

func _draw() -> void:
    if not world_visible:
        return
    draw_rect(Rect2(Vector2.ZERO, get_viewport_rect().size), Color("#121e29"))
    var view := _visible_tile_bounds()
    for y in range(view[1], view[3]):
        for x in range(view[0], view[2]):
            _tile(x, y, Color("#263e42") if (x + y) % 2 == 0 else Color("#294449"))
    for i in range(plots.size()):
        var p: Dictionary = plots[i]
        var px := int(p["tile_x"])
        var py := int(p["tile_y"])
        if px >= view[2] or py >= view[3] or px + int(p["width_tiles"]) <= view[0] or py + int(p["height_tiles"]) <= view[1]:
            continue
        var color: Color = ZONES.get(str(p["zone"]), Color.GRAY)
        if i == selected_plot:
            color = color.lightened(0.32)
        for dy in range(int(p["height_tiles"])):
            for dx in range(int(p["width_tiles"])):
                _tile(int(p["tile_x"]) + dx, int(p["tile_y"]) + dy, color)
        var center := project_point(float(p["tile_x"]) + float(p["width_tiles"]) / 2.0,
            float(p["tile_y"]) + float(p["height_tiles"]) / 2.0)
        var icon: Texture2D = ZONE_ICONS.get(str(p["zone"]))
        if icon != null:
            var icon_size := 44.0 * zoom_level
            draw_texture_rect(icon, Rect2(center - Vector2(icon_size * 0.5, icon_size * 0.8), Vector2(icon_size, icon_size)), false)
        draw_circle(center, 3.0, Color.WHITE)

func _visible_tile_bounds() -> Array[int]:
    var screen := get_viewport_rect().size
    var min_x := float(world_width)
    var min_y := float(world_height)
    var max_x := 0.0
    var max_y := 0.0
    for corner in [Vector2.ZERO, Vector2(screen.x, 0), Vector2(0, screen.y), screen]:
        var local: Vector2 = (corner - camera_offset) / zoom_level
        var tx: float = local.x / TILE_W + local.y / TILE_H
        var ty: float = local.y / TILE_H - local.x / TILE_W
        min_x = minf(min_x, tx)
        min_y = minf(min_y, ty)
        max_x = maxf(max_x, tx)
        max_y = maxf(max_y, ty)
    return [
        clampi(int(floor(min_x)) - 2, 0, world_width),
        clampi(int(floor(min_y)) - 2, 0, world_height),
        clampi(int(ceil(max_x)) + 3, 0, world_width),
        clampi(int(ceil(max_y)) + 3, 0, world_height)
    ]

func _tile(x: int, y: int, color: Color) -> void:
    var corners := PackedVector2Array([
        project_point(x, y), project_point(x + 1, y),
        project_point(x + 1, y + 1), project_point(x, y + 1)
    ])
    draw_colored_polygon(corners, color)
    draw_polyline(PackedVector2Array([corners[0],corners[1],corners[2],corners[3],corners[0]]),
        Color("#142a32"), 1.0)

func _unhandled_input(event: InputEvent) -> void:
    if not world_visible or get_node("Login").panel.visible:
        return
    if event is InputEventMouseButton:
        if event.button_index == MOUSE_BUTTON_WHEEL_UP and event.pressed:
            zoom_at(event.position, 1.12)
        elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN and event.pressed:
            zoom_at(event.position, 1.0 / 1.12)
        elif event.button_index == MOUSE_BUTTON_MIDDLE:
            dragging = event.pressed
        elif event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
            _select_at(event.position)
        queue_redraw()
    elif event is InputEventMouseMotion and dragging:
        camera_offset += event.relative
        _camera_changed()
    elif event is InputEventScreenTouch:
        if event.pressed:
            touches[event.index] = event.position
        else:
            var was_tap := touches.size() == 1 and touches.has(event.index)
            var start: Vector2 = touches.get(event.index, event.position)
            touches.erase(event.index)
            if was_tap and start.distance_to(event.position) < 18.0:
                _select_at(event.position)
        if touches.size() == 2:
            var positions: Array = touches.values()
            pinch_distance = (positions[0] as Vector2).distance_to(positions[1] as Vector2)
        else:
            pinch_distance = 0.0
    elif event is InputEventScreenDrag:
        var previous: Vector2 = touches.get(event.index, event.position)
        touches[event.index] = event.position
        if touches.size() == 1:
            camera_offset += event.position - previous
            _camera_changed()
        elif touches.size() == 2:
            var positions: Array = touches.values()
            var distance: float = positions[0].distance_to(positions[1])
            if pinch_distance > 0.0:
                var midpoint: Vector2 = (positions[0] + positions[1]) * 0.5
                zoom_at(midpoint, distance / pinch_distance)
            pinch_distance = distance
        queue_redraw()
    _camera_changed()

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
    if selected_plot >= 0:
        $Economy.choose_plot(plots[selected_plot])
    $OSM.refresh()
    queue_redraw()

func _update_hud() -> void:
    var suffix := "Выберите участок"
    if selected_plot >= 0:
        var p: Dictionary = plots[selected_plot]
        suffix = "Участок %d · %s" % [selected_plot + 1, str(p["zone"])]
    hud.text = "УФА  /  %s" % suffix
