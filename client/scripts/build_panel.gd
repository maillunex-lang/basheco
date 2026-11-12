extends CanvasLayer
## Build on selected game plot; server validates ownership and zoning.
var api: Node
var http: HTTPRequest
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
    panel = PanelContainer.new()
    panel.position = Vector2(390, 82)
    panel.custom_minimum_size = Vector2(360, 0)
    add_child(panel)
    var layout := VBoxContainer.new()
    panel.add_child(layout)
    var title := Label.new()
    title.text = "Строительство и развитие"
    layout.add_child(title)
    company = OptionButton.new()
    company.add_item("Сначала создайте компанию")
    layout.add_child(company)
    building_picker = OptionButton.new()
    for item in CATALOG:
        building_picker.add_item(item["title"])
    building_picker.item_selected.connect(func(_index: int): _refresh_selection())
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
    selected_info.text = detail + "\nЦена и размеры здания пока не определены сервером."
    build_button.disabled = busy or _selection_error() != ""

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