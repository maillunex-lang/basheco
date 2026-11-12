extends Node2D
## The single isometric world of BASHECO. Server remains authoritative.
## Every settlement lives in ONE continuous grid (EPSG:32640, 6 m cells, see
## world_grid.gd). Choosing a settlement moves the camera; it never loads another map.
##
## Precision: global cells are integers. Everything drawn is expressed relative
## to render_origin, a chunk-aligned global cell that follows the camera, so the
## 32-bit canvas never sees million-sized coordinates.
const CityChunks = preload("res://scripts/city_chunks.gd")
const GeoBackground = preload("res://scripts/geo_background.gd")
const WorldGrid = preload("res://scripts/world_grid.gd")
const WorldOverlay = preload("res://scripts/world_overlay.gd")
const GENERATED := "res://data/generated_locations.json"
var generated_objects: Array[Dictionary] = []
var geo_background = GeoBackground.new()
const DEFAULT_SETTLEMENT := "ufa"
var current_location_id := DEFAULT_SETTLEMENT
var admin_target_name := ""
var admin_target_cell := Vector2i.ZERO
const MAX_VISIBLE_TILES := 18000
const MIN_ZOOM := 0.004
const MAX_ZOOM := 2.4
const DEFAULT_ZOOM := 1.15
const TILE_W := 64.0
const TILE_H := 32.0
const REBASE_CELLS := 256.0
const PARCEL_REQUEST_HALF_SIZE := 96
## Level of detail by zoom: 0 full detail, 1 no sprites/grid, 2 main roads and
## areas only, 3 republic overview (settlement outlines and names, no chunks).
const LOD_MIN_ZOOM := [0.85, 0.3, 0.12]
const ZONES := {
    "commercial": Color("#e0ad57"),
    "industrial": Color("#5f93a9"),
    "agricultural": Color("#72b883")
}
var plots: Array[Dictionary] = []
var unplaced_plot_count := 0
var _last_viewport_bounds: Array[int] = []
var _viewport_cooldown := 0.0
var zoom_level := DEFAULT_ZOOM
var render_origin := Vector2i.ZERO
var camera_offset := Vector2.ZERO
var camera_initialized := false
var world_visible := false:
    set(value):
        world_visible = value
        queue_redraw()
        if overlay != null:
            overlay.queue_redraw()
var dragging := false
var touches: Dictionary = {}
var pinch_distance := 0.0
var selected_plot := -1
var fade_occluding_buildings := false
var occlusion_button: Button
var overlay: Node2D
const ZONE_ICONS := {
    "commercial": preload("res://assets/icons/shop.svg"),
    "industrial": preload("res://assets/icons/workshop.svg"),
    "agricultural": preload("res://assets/icons/greenhouse.svg")
}
var hud: Label

func _ready() -> void:
    var generated_file := FileAccess.open(GENERATED, FileAccess.READ)
    if generated_file != null:
        var data: Variant = JSON.parse_string(generated_file.get_as_text())
        if typeof(data) == TYPE_DICTIONARY and data.get("schema", "") == "basheco.generated_locations/1":
            for location in data.get("locations", []):
                for obj in location.get("objects", []):
                    generated_objects.append(obj)
    geo_background.load_world(self)
    overlay = WorldOverlay.new()
    overlay.name = "Overlay"
    add_child(overlay)
    hud = Label.new()
    hud.position = Vector2(18, 12)
    hud.add_theme_color_override("font_color", Color.WHITE)
    hud.add_theme_font_size_override("font_size", 19)
    add_child(hud)
    hud.visible = false
    occlusion_button = Button.new()
    occlusion_button.text = "Скрыть здания"
    occlusion_button.position = Vector2(18, 52)
    occlusion_button.pressed.connect(_toggle_occlusion)
    add_child(occlusion_button)
    occlusion_button.visible = false
    _focus_on_district()
    _update_hud()
    $API.sector_loaded.connect(_on_sector_loaded)
    $API.request_failed.connect(_on_api_error)
    get_viewport().size_changed.connect(_on_viewport_resized)
    queue_redraw()

func _process(_delta: float) -> void:
    if world_visible and geo_background.process_pending_chunks(self):
        overlay.queue_redraw()
    if world_visible:
        _viewport_cooldown = maxf(0.0, _viewport_cooldown - _delta)
        if _viewport_cooldown <= 0.0 and not $API.access_token.is_empty():
            _request_camera_parcels()

func _toggle_occlusion() -> void:
    fade_occluding_buildings = not fade_occluding_buildings
    occlusion_button.text = "Показать здания" if fade_occluding_buildings else "Скрыть здания"
    overlay.queue_redraw()

# --- Camera in the single world -------------------------------------------------

func lod() -> int:
    for level in range(LOD_MIN_ZOOM.size()):
        if zoom_level >= float(LOD_MIN_ZOOM[level]):
            return level
    return LOD_MIN_ZOOM.size()

## Zoom quantised to ~12% steps; cached line widths are redrawn only between steps.
func zoom_band() -> float:
    return pow(1.12, roundf(log(zoom_level) / log(1.12)))

func iso(x: float, y: float) -> Vector2:
    return Vector2((x - y) * TILE_W * 0.5, (x + y) * TILE_H * 0.5)

## Screen position of a point given in cells relative to render_origin.
func project_point(x: float, y: float) -> Vector2:
    return iso(x, y) * zoom_level + camera_offset

## Screen position of a global cell corner (plus an optional sub-cell offset).
func project_cell(cell: Vector2i, offset: Vector2 = Vector2.ZERO) -> Vector2:
    var local := Vector2(cell - render_origin) + offset
    return project_point(local.x, local.y)

func screen_to_local(point: Vector2) -> Vector2:
    var flat: Vector2 = (point - camera_offset) / zoom_level
    return Vector2(flat.x / TILE_W + flat.y / TILE_H, flat.y / TILE_H - flat.x / TILE_W)

func screen_to_cell(point: Vector2) -> Vector2i:
    var local := screen_to_local(point)
    return render_origin + Vector2i(floori(local.x), floori(local.y))

func camera_center_cell() -> Vector2i:
    return screen_to_cell(get_viewport_rect().size * 0.5)

## Camera centre as 64-bit continuous global cell coordinates [x, y].
func camera_center_exact() -> PackedFloat64Array:
    var local := screen_to_local(get_viewport_rect().size * 0.5)
    return PackedFloat64Array([float(render_origin.x) + local.x, float(render_origin.y) + local.y])

## WGS84 [lon, lat] under the camera centre (for display and on-device checks).
func camera_center_lonlat() -> PackedFloat64Array:
    var exact := camera_center_exact()
    var metres := WorldGrid.cell_to_metres(exact[0], exact[1])
    return WorldGrid.metres_to_lonlat(metres[0], metres[1])

func center_on_cell(cell: Vector2i, fraction: Vector2 = Vector2(0.5, 0.5)) -> void:
    render_origin = WorldGrid.chunk_origin_cell(WorldGrid.cell_to_chunk(cell.x, cell.y))
    var local := Vector2(cell - render_origin) + fraction
    camera_offset = get_viewport_rect().size * 0.5 - iso(local.x, local.y) * zoom_level
    camera_initialized = true
    _camera_changed()

func _focus_on_district() -> void:
    if not admin_target_name.is_empty():
        zoom_level = DEFAULT_ZOOM
        center_on_cell(admin_target_cell)
        return
    # "⌖ Район": back to the nearest settlement's sourced area at working zoom.
    var target := DEFAULT_SETTLEMENT
    if camera_initialized:
        target = geo_background.nearest_settlement(camera_center_cell())
    if not geo_background.settlements.has(target):
        camera_initialized = true
        return
    zoom_level = DEFAULT_ZOOM
    center_on_cell(geo_background.settlements[target]["focus_cell"])

func zoom_at(screen_point: Vector2, factor: float) -> void:
    var old_zoom := zoom_level
    zoom_level = clampf(old_zoom * factor, MIN_ZOOM, MAX_ZOOM)
    camera_offset = screen_point - (screen_point - camera_offset) * (zoom_level / old_zoom)
    _camera_changed()

func _clamp_camera() -> void:
    # The camera may roam the whole navigable region between settlements.
    var bounds: Array[int] = geo_background.nav_bounds
    if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
        return
    var exact := camera_center_exact()
    var shift := Vector2(clampf(exact[0], bounds[0], bounds[2]) - exact[0],
        clampf(exact[1], bounds[1], bounds[3]) - exact[1])
    if shift != Vector2.ZERO:
        camera_offset -= iso(shift.x, shift.y) * zoom_level

func _rebase_origin() -> void:
    # Keep drawn coordinates small: move the origin to the camera's chunk.
    var local := screen_to_local(get_viewport_rect().size * 0.5)
    if absf(local.x) <= REBASE_CELLS and absf(local.y) <= REBASE_CELLS:
        return
    var cell := render_origin + Vector2i(floori(local.x), floori(local.y))
    var origin := WorldGrid.chunk_origin_cell(WorldGrid.cell_to_chunk(cell.x, cell.y))
    var delta := origin - render_origin
    camera_offset += iso(float(delta.x), float(delta.y)) * zoom_level
    render_origin = origin

func _camera_changed() -> void:
    _clamp_camera()
    _rebase_origin()
    # Once the player pans away, do not keep showing the previous village title.
    if not admin_target_name.is_empty() and camera_center_cell().distance_to(admin_target_cell) > 256:
        admin_target_name = ""
        _update_hud()
    var here: String = geo_background.settlement_at(camera_center_cell())
    if here != current_location_id:
        current_location_id = here
        _update_hud()
        if has_node("HUD") and $HUD.is_node_ready():
            $HUD.update_geography_credit(here)
    geo_background.update_view(self)
    queue_redraw()
    if overlay != null:
        overlay.queue_redraw()

func _on_viewport_resized() -> void:
    if camera_initialized and not world_visible:
        _focus_on_district()
    _camera_changed()

## Global cells covered by the screen: [min_x, min_y, max_x, max_y) with a small margin.
func visible_cell_bounds() -> Array[int]:
    var screen := get_viewport_rect().size
    var min_x := INF
    var min_y := INF
    var max_x := -INF
    var max_y := -INF
    for corner in [Vector2.ZERO, Vector2(screen.x, 0), Vector2(0, screen.y), screen]:
        var local := screen_to_local(corner)
        min_x = minf(min_x, local.x)
        min_y = minf(min_y, local.y)
        max_x = maxf(max_x, local.x)
        max_y = maxf(max_y, local.y)
    return [render_origin.x + int(floor(min_x)) - 2, render_origin.y + int(floor(min_y)) - 2,
        render_origin.x + int(ceil(max_x)) + 3, render_origin.y + int(ceil(max_y)) + 3]

# --- Server data ---------------------------------------------------------------

func connect_to_server(url: String, token: String) -> void:
    $API.configure(url, token)
    refresh_parcels()

func refresh_parcels() -> void:
    _last_viewport_bounds.clear()
    _viewport_cooldown = 0.0
    _request_camera_parcels()

func _on_sector_loaded(data: Dictionary) -> void:
    # Plots are addressed only by server-assigned world cells. Legacy settlement
    # tile_x/tile_y are history and are never used for placement on the map.
    var selected_id := ""
    if selected_plot >= 0 and selected_plot < plots.size():
        selected_id = str(plots[selected_plot].get("id", ""))
    var verified: Array[Dictionary] = []
    for item in data["plots"]:
        if typeof(item) != TYPE_DICTIONARY:
            return
        if not item.has("zone") or not item.has("width_tiles") or not item.has("height_tiles"):
            return
        if item.get("world_cell_x") == null or item.get("world_cell_y") == null:
            continue  # not placed on the world grid by the server: never guess a position
        var plot: Dictionary = item.duplicate()
        plot["cell_x"] = int(item["world_cell_x"])
        plot["cell_y"] = int(item["world_cell_y"])
        plot["width_cells"] = int(item["width_tiles"])
        plot["height_cells"] = int(item["height_tiles"])
        verified.append(plot)
    plots = verified
    unplaced_plot_count = int(data.get("unplaced_plot_count", 0))
    world_visible = true
    occlusion_button.visible = true
    selected_plot = -1
    for i in range(plots.size()):
        if not selected_id.is_empty() and str(plots[i].get("id", "")) == selected_id:
            selected_plot = i
    _update_hud()
    _camera_changed()

## Move the camera to a settlement of the same world. Returns false if unknown.
func open_location(location_id: String) -> bool:
    if not geo_background.ready or not geo_background.settlements.has(location_id):
        return false
    admin_target_name = ""
    selected_plot = -1
    world_visible = true
    occlusion_button.visible = true
    zoom_level = DEFAULT_ZOOM
    center_on_cell(geo_background.settlements[location_id]["focus_cell"])
    refresh_parcels()
    _update_hud()
    return true

## Administrative catalog navigation: the registry provides a global cell, not an atlas-local id.
## A valid settlement without imported OSM detail is still a navigable map location.
func open_world_cell(cell: Vector2i, settlement_name: String = "") -> bool:
    if not geo_background.ready:
        return false
    selected_plot = -1
    admin_target_name = settlement_name
    admin_target_cell = cell
    world_visible = true
    occlusion_button.visible = true
    zoom_level = DEFAULT_ZOOM
    center_on_cell(cell)
    refresh_parcels()
    _update_hud()
    return true

func _request_camera_parcels() -> void:
    if $API.access_token.is_empty() or lod() > 1:
        return
    var center := camera_center_cell()
    var bounds: Array[int] = [center.x - PARCEL_REQUEST_HALF_SIZE, center.y - PARCEL_REQUEST_HALF_SIZE,
        center.x + PARCEL_REQUEST_HALF_SIZE, center.y + PARCEL_REQUEST_HALF_SIZE]
    if bounds == _last_viewport_bounds:
        _viewport_cooldown = 1.0
        return
    if $API._http.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED:
        return
    _last_viewport_bounds = bounds
    _viewport_cooldown = 0.5
    $API.load_viewport(bounds)

func _on_api_error(_status: int, message: String) -> void:
    hud.text = "BASHECO | " + message
    if has_node("HUD"):
        $HUD.district_label.text = "Ошибка карты: " + message

# --- Drawing -------------------------------------------------------------------

func _draw() -> void:
    if not world_visible:
        return
    draw_rect(Rect2(Vector2.ZERO, get_viewport_rect().size), Color("#121e29"))
    var view := visible_cell_bounds()
    var nav: Array[int] = geo_background.nav_bounds
    var left := maxi(view[0], nav[0])
    var top := maxi(view[1], nav[1])
    var right := mini(view[2], nav[2])
    var bottom := mini(view[3], nav[3])
    if right <= left or bottom <= top:
        return
    # One continuous ground plane. Cells are never instantiated: only the lines of
    # the on-screen part of the grid are drawn, and only at full detail.
    var corners := PackedVector2Array([project_cell(Vector2i(left, top)), project_cell(Vector2i(right, top)),
        project_cell(Vector2i(right, bottom)), project_cell(Vector2i(left, bottom))])
    draw_colored_polygon(corners, Color("#27414a"))
    if lod() == 0 and (right - left) * (bottom - top) <= MAX_VISIBLE_TILES:
        for x in range(left, right + 1):
            draw_line(project_cell(Vector2i(x, top)), project_cell(Vector2i(x, bottom)), Color("#142a32"), 1.0)
        for y in range(top, bottom + 1):
            draw_line(project_cell(Vector2i(left, y)), project_cell(Vector2i(right, y)), Color("#142a32"), 1.0)

## Called by the Overlay node, which sits above the geography chunks.
func draw_overlay(canvas: CanvasItem) -> void:
    if not world_visible:
        return
    var view := visible_cell_bounds()
    geo_background.render_sprites(self, canvas)
    # Stage 1.3 pilot: deterministic visual-only buildings and roads.
    # This layer is NOT player property and is not written to the game database.
    if lod() <= 1:
        for obj in generated_objects:
            var cell_data: Array = obj["cell"]
            var size_data: Array = obj["size"]
            var cell := Vector2i(int(cell_data[0]), int(cell_data[1]))
            var footprint := Vector2i(int(size_data[0]), int(size_data[1]))
            if cell.x + footprint.x < view[0] or cell.x > view[2] or cell.y + footprint.y < view[1] or cell.y > view[3]:
                continue
            var corners := PackedVector2Array([
                project_cell(cell), project_cell(cell + Vector2i(footprint.x, 0)),
                project_cell(cell + footprint), project_cell(cell + Vector2i(0, footprint.y))
            ])
            var color := Color("#53616b") if str(obj["kind"]) == "road" else Color("#d7a76e")
            canvas.draw_colored_polygon(corners, color)
            if str(obj["kind"]) == "house":
                canvas.draw_polyline(PackedVector2Array([corners[0], corners[1], corners[2], corners[3], corners[0]]), Color("#fff0cb"), 2.0)
    # Construction preview is only an outline of an existing server parcel.
    # It is NOT a building footprint, cadastral clearance or server approval.
    var build_panel = get_node("Build")
    if build_panel.panel.visible and selected_plot >= 0 and selected_plot < plots.size():
        var preview: Dictionary = plots[selected_plot]
        var origin := Vector2i(int(preview["cell_x"]), int(preview["cell_y"]))
        var extent := Vector2i(int(preview["width_cells"]), int(preview["height_cells"]))
        if extent.x > 0 and extent.y > 0:
            var points := PackedVector2Array([
                project_cell(origin), project_cell(origin + Vector2i(extent.x, 0)),
                project_cell(origin + extent), project_cell(origin + Vector2i(0, extent.y)),
                project_cell(origin)
            ])
            var valid: bool = build_panel._selection_error().is_empty()
            var tint := Color("#62e0b6") if valid else Color("#ffb56b")
            canvas.draw_polyline(points, tint, 4.0, true)
    # Playable parcels always render above the read-only geography.
    if lod() <= 2:
        for i in range(plots.size()):
            var p: Dictionary = plots[i]
            if not CityChunks.plot_intersects_bounds(p, view):
                continue
            var cell := Vector2i(int(p["cell_x"]), int(p["cell_y"]))
            var width := int(p["width_cells"])
            var height := int(p["height_cells"])
            var color: Color = ZONES.get(str(p["zone"]), Color.GRAY)
            if i == selected_plot:
                color = color.lightened(0.32)
            var outline := PackedVector2Array([
                project_cell(cell), project_cell(cell + Vector2i(width, 0)),
                project_cell(cell + Vector2i(width, height)), project_cell(cell + Vector2i(0, height)),
                project_cell(cell)
            ])
            canvas.draw_colored_polygon(PackedVector2Array([outline[0], outline[1], outline[2], outline[3]]), color)
            if lod() == 0:
                for d in range(1, width):
                    canvas.draw_line(project_cell(cell + Vector2i(d, 0)), project_cell(cell + Vector2i(d, height)), Color("#142a32"), 1.0)
                for d in range(1, height):
                    canvas.draw_line(project_cell(cell + Vector2i(0, d)), project_cell(cell + Vector2i(width, d)), Color("#142a32"), 1.0)
            canvas.draw_polyline(outline, Color("#142a32"), 1.0)
            var center := project_cell(cell, Vector2(float(width) / 2.0, float(height) / 2.0))
            var icon: Texture2D = ZONE_ICONS.get(str(p["zone"]))
            if icon != null and lod() <= 1:
                var icon_size := 44.0 * zoom_level
                canvas.draw_texture_rect(icon, Rect2(center - Vector2(icon_size * 0.5, icon_size * 0.8), Vector2(icon_size, icon_size)), false)
            canvas.draw_circle(center, 3.0, Color.WHITE)
            if i == selected_plot and p.get("building_id") != null:
                # Selected building: visible outline even when icon texture is small.
                canvas.draw_polyline(outline, Color("#ffed83"), 3.5, true)
                canvas.draw_circle(center, 7.0 * zoom_level, Color("#ffed83", 0.85))
    if lod() >= 2:
        # Far zoom: every settlement of the one world, at its real position.
        var font := ThemeDB.fallback_font
        var screen := Rect2(Vector2.ZERO, get_viewport_rect().size).grow(40.0)
        for id in geo_background.settlement_order:
            var settlement: Dictionary = geo_background.settlements[id]
            var where := project_cell(settlement["focus_cell"], Vector2(0.5, 0.5))
            if not screen.has_point(where):
                continue
            canvas.draw_circle(where, 6.0, Color("#e2bf72"))
            canvas.draw_circle(where, 3.0, Color("#142634"))
            canvas.draw_string(font, where + Vector2(10, 6), str(settlement["name"]), HORIZONTAL_ALIGNMENT_LEFT, -1, 18, Color("#f3f6f0"))

# --- Input ---------------------------------------------------------------------

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

func _select_at(point: Vector2) -> void:
    var cell := screen_to_cell(point)
    selected_plot = -1
    for i in range(plots.size()):
        var p: Dictionary = plots[i]
        if cell.x >= int(p["cell_x"]) and cell.x < int(p["cell_x"]) + int(p["width_cells"]) and \
            cell.y >= int(p["cell_y"]) and cell.y < int(p["cell_y"]) + int(p["height_cells"]):
            selected_plot = i
            break
    _update_hud()
    if selected_plot >= 0:
        $Economy.choose_plot(plots[selected_plot])
    overlay.queue_redraw()

func location_title() -> String:
    if not admin_target_name.is_empty():
        return admin_target_name.to_upper()
    if geo_background.settlements.has(current_location_id):
        return str(geo_background.settlements[current_location_id]["name"]).to_upper()
    return "РЕСПУБЛИКА БАШКОРТОСТАН"

func _update_hud() -> void:
    var suffix := "Выберите участок"
    if selected_plot >= 0:
        var p: Dictionary = plots[selected_plot]
        suffix = "Участок %d · %s" % [selected_plot + 1, str(p["zone"])]
    if hud != null:
        hud.text = location_title() + "  /  " + suffix
    if has_node("HUD") and $HUD.is_node_ready():
        $HUD.district_label.text = location_title() + "  /  " + suffix