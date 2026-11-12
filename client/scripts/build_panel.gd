extends CanvasLayer
const WorldGrid = preload("res://scripts/world_grid.gd")
## Build on selected game plot; server validates ownership and zoning.
var api: Node
var http: HTTPRequest
var plot_http: HTTPRequest
var plot_busy := false
var plot_request_kind := ""
var anchors: Dictionary = {}
var sector_picker: OptionButton
var zone_picker: OptionButton
var plot_button: Button
var scroll: ScrollContainer
var panel: PanelContainer
var company: OptionButton
var company_ids: Array[String] = []
var message: Label
var world: Node2D
var building_picker: OptionButton
var selected_info: Label
var build_button: Button
var busy := false
# Verified server building_types in migration 004_world_prototype.sql.
# Sizes are plot dimensions, not building footprint specifications.
const CATALOG := [
    {"code": "shop", "title": "Магазин", "zone": "commercial"},
    {"code": "workshop", "title": "Мастерская", "zone": "industrial"},
    {"code": "greenhouse", "title": "Теплица", "zone": "agricultural"}
]
const ZONE_NAMES := {"commercial": "Торговая", "industrial": "Промышленная", "agricultural": "Сельскохозяйственная"}


func _ready() -> void:
    world = get_parent()
    api = world.get_node("API")
    http = HTTPRequest.new()
    add_child(http)
    http.request_completed.connect(_on_result)
    plot_http = HTTPRequest.new()
    add_child(plot_http)
    plot_http.request_completed.connect(_on_plot_result)
    api.authenticated.connect(_load_anchors)
    panel = PanelContainer.new()
    panel.position = Vector2(390, 82)
    panel.custom_minimum_size = Vector2(360, 0)
    add_child(panel)
    scroll = ScrollContainer.new()
    scroll.custom_minimum_size = Vector2(340, 440)
    scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    panel.add_child(scroll)
    var layout := VBoxContainer.new()
    layout.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    scroll.add_child(layout)
    var title := Label.new()
    title.text = "Строительство и развитие"
    layout.add_child(title)
    var alpha_label := Label.new()
    alpha_label.text = "АЛЬФА · только тестовая игровая земля, не кадастровая собственность"
    alpha_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    layout.add_child(alpha_label)
    var pickers := HBoxContainer.new()
    layout.add_child(pickers)
    sector_picker = OptionButton.new()
    sector_picker.add_item("Уфа")
    sector_picker.add_item("Михайловка")
    sector_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    pickers.add_child(sector_picker)
    zone_picker = OptionButton.new()
    zone_picker.add_item("Торговая")
    zone_picker.add_item("Промышленная")
    zone_picker.add_item("Аграрная")
    zone_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    pickers.add_child(zone_picker)
    plot_button = Button.new()
    plot_button.text = "Создать тестовый участок у центра карты"
    plot_button.custom_minimum_size.y = 46
    plot_button.pressed.connect(_create_alpha_plot)
    layout.add_child(plot_button)
    company = OptionButton.new()
    company.add_item("Сначала создайте компанию")
    layout.add_child(company)
    building_picker = OptionButton.new()
    for item in CATALOG:
        building_picker.add_item(item["title"])
    building_picker.item_selected.connect(func(_index: int): _refresh_selection(); world.overlay.queue_redraw())
    layout.add_child(building_picker)
    selected_info = Label.new()
    selected_info.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    layout.add_child(selected_info)
    build_button = Button.new()
    build_button.text = "Построить на выбранном участке"
    build_button.pressed.connect(_build)
    layout.add_child(build_button)
    var reload := Button.new()
    reload.text = "Обновить кварталы"
    reload.pressed.connect(func(): world.refresh_parcels())
    layout.add_child(reload)
    message = Label.new()
    message.text = "Выберите свободный участок на карте"
    layout.add_child(message)
    panel.visible = false
    visibility_changed.connect(func(): world.overlay.queue_redraw())
    set_process(true)
    _refresh_selection()
    world.get_node("Company").companies_updated.connect(_set_companies)

func _process(_delta: float) -> void:
    if panel.visible:
        _refresh_selection()

func _current_building() -> Dictionary:
    var index := building_picker.selected
    if index < 0 or index >= CATALOG.size():
        return {}
    return CATALOG[index]

func _selection_error() -> String:
    if api.access_token.is_empty():
        return "Войдите в игру, чтобы строить"
    if _selected_company_id().is_empty():
        return "Сначала создайте компанию"
    if world.selected_plot < 0 or world.selected_plot >= world.plots.size():
        return "Выберите участок на карте"
    var plot: Dictionary = world.plots[world.selected_plot]
    if not plot.has("id") or str(plot.get("id", "")).is_empty():
        return "Нужен участок, подтверждённый сервером"
    if plot.get("owner_company_id") != null and str(plot.get("owner_company_id")) != "":
        return "Участок уже занят"
    var chosen := _current_building()
    if chosen.is_empty() or chosen["zone"] != str(plot.get("zone", "")):
        return "Тип здания не подходит для зоны участка"
    return ""

func _refresh_selection() -> void:
    var detail := "Выберите свободный участок на карте"
    if world.selected_plot >= 0 and world.selected_plot < world.plots.size():
        var plot: Dictionary = world.plots[world.selected_plot]
        var zone := str(plot.get("zone", ""))
        detail = "%s зона · участок %s×%s клеток" % [ZONE_NAMES.get(zone, zone), str(plot.get("width_tiles", "?")), str(plot.get("height_tiles", "?"))]
    selected_info.text = detail + "\nКонтур на карте показывает участок, не размеры здания.\nЦена и размеры здания пока не определены сервером."
    build_button.disabled = busy or _selection_error() != ""
    plot_button.disabled = plot_busy or api.access_token.is_empty()

func _set_companies(companies: Array) -> void:
    var previous := _selected_company_id()
    company.clear()
    company_ids.clear()
    var selected_index := 0
    for entry in companies:
        var id := str(entry["id"])
        company.add_item(str(entry.get("name", "Компания")))
        company_ids.append(id)
        if id == previous:
            selected_index = company_ids.size() - 1
    if company_ids.is_empty():
        company.add_item("Сначала создайте компанию")
    else:
        company.select(selected_index)

func _selected_company_id() -> String:
    if company_ids.is_empty() or company.selected < 0 or company.selected >= company_ids.size():
        return ""
    return company_ids[company.selected]

func _build() -> void:
    if busy:
        return
    var reason := _selection_error()
    if not reason.is_empty():
        message.text = reason
        return
    var plot: Dictionary = world.plots[world.selected_plot]
    var kind := str(_current_building()["code"])
    var payload := JSON.stringify({"company_id":_selected_company_id(), "plot_id":str(plot["id"]), "building_type":kind})
    var headers := PackedStringArray(["Authorization: Bearer " + api.access_token, "Content-Type: application/json"])
    busy = true
    _refresh_selection()
    var err := http.request(api.base_url + "/v1/world/buildings", headers, HTTPClient.METHOD_POST, payload)
    if err != OK:
        busy = false
        _refresh_selection()
    message.text = "Строительство..." if err == OK else "Нет соединения"

func _on_result(_result: int, status: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    busy = false
    _refresh_selection()
    if status == 201:
        var result: Variant = JSON.parse_string(body.get_string_from_utf8())
        message.text = "Построено! Новых участков: " + str(result.get("new_plots", 0))
        world.refresh_parcels()
    else:
        message.text = "Ошибка строительства: HTTP " + str(status)
func _load_anchors() -> void:
    if plot_busy or api.access_token.is_empty():
        return
    plot_busy = true
    plot_request_kind = "grid"
    var headers := PackedStringArray(["Authorization: Bearer " + api.access_token])
    var err := plot_http.request(api.base_url + "/v1/world/grid", headers)
    if err != OK:
        plot_busy = false
        message.text = "Не удалось получить географические параметры сервера"

func _legacy_tile_for_cell(anchor: Dictionary, cell: Vector2i) -> Vector2i:
    ## Inverse of the legacy projection; only for the alpha plot-creation API.
    ## The world itself always uses the continuous EPSG:32640 cell grid.
    var metres: PackedFloat64Array = WorldGrid.cell_to_metres(float(cell.x), float(cell.y))
    var point: PackedFloat64Array = WorldGrid.metres_to_lonlat(metres[0], metres[1])
    var base_lon := float(anchor.get("origin_lon", 0.0))
    var base_lat := float(anchor.get("origin_lat", 0.0))
    var scale := float(anchor.get("metres_per_tile", 0.0))
    if scale <= 0.0:
        return Vector2i(-1, -1)
    var east := 6378137.0 * deg_to_rad(point[0] - base_lon) * cos(deg_to_rad(base_lat))
    var south := -6378137.0 * deg_to_rad(point[1] - base_lat)
    return Vector2i(roundi(float(anchor.get("origin_tile_x", 0)) + east / scale),
        roundi(float(anchor.get("origin_tile_y", 0)) + south / scale))

func _create_alpha_plot() -> void:
    if plot_busy or api.access_token.is_empty():
        message.text = "Для получения участка войдите в игру"
        return
    if anchors.is_empty():
        message.text = "Сначала загружаем параметры карты. Повторите действие."
        _load_anchors()
        return
    var sector := "ufa" if sector_picker.selected == 0 else "mikhailovka"
    if not anchors.has(sector):
        message.text = "Для этого населённого пункта нет проверенной привязки"
        return
    var cell: Vector2i = world.camera_center_cell()
    var pos: Vector2i = _legacy_tile_for_cell(anchors[sector], cell)
    if pos.x < 0 or pos.y < 0 or pos.x > 4090 or pos.y > 4090:
        message.text = "Центр карты вне тестового сектора. Перейдите к Уфе или Михайловке."
        return
    var zone: String = str(["commercial", "industrial", "agricultural"][zone_picker.selected])
    var body := JSON.stringify({
        "sector_id": sector, "tile_x": pos.x, "tile_y": pos.y, "zone": zone
    })
    var headers := PackedStringArray(["Authorization: Bearer " + api.access_token, "Content-Type: application/json"])
    plot_request_kind = "create"
    plot_busy = true
    var err := plot_http.request(api.base_url + "/v1/world/plots", headers, HTTPClient.METHOD_POST, body)
    if err != OK:
        plot_busy = false
        message.text = "Не удалось отправить запрос на участок"
    else:
        message.text = "Проверяем возможность создания участка..."

func _on_plot_result(_result: int, status: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    plot_busy = false
    var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
    if plot_request_kind == "grid":
        if status != 200 or typeof(parsed) != TYPE_DICTIONARY:
            message.text = "Сервер карты устарел или недоступен. Требуется обновление API."
            return
        anchors.clear()
        for anchor in parsed.get("legacy_sector_anchors", []):
            if typeof(anchor) == TYPE_DICTIONARY:
                var code := str(anchor.get("sector_id", ""))
                if code in ["ufa", "mikhailovka"] and str(anchor.get("projection", "")) == "local_equirectangular_metres":
                    anchors[code] = anchor
        if anchors.is_empty():
            message.text = "Тестовые территории не разрешены сервером"
        return
    if status < 200 or status >= 300 or typeof(parsed) != TYPE_DICTIONARY:
        message.text = "Участок не создан (HTTP %d). Возможны занятая земля, лимит 3 участка или запрет территории." % status
        return
    if parsed.get("world_cell_x") == null or parsed.get("world_cell_y") == null:
        message.text = "Сервер не подтвердил размещение на общей карте"
        return
    var location := Vector2i(int(parsed["world_cell_x"]), int(parsed["world_cell_y"]))
    world.zoom_level = world.DEFAULT_ZOOM
    world.center_on_cell(location + Vector2i(2, 2))
    world.refresh_parcels()
    message.text = "Тестовый участок создан. Выберите его на карте и нажмите «Построить»."