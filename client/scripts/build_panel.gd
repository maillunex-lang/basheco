extends CanvasLayer
## Build on selected game plot; server validates ownership and zoning.
var api: Node
var http: HTTPRequest
var panel: PanelContainer
var company: LineEdit
var message: Label
var world: Node2D

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
    company = LineEdit.new()
    company.placeholder_text = "UUID своей компании (из раздела Рынок)"
    layout.add_child(company)
    var build := Button.new()
    build.text = "Построить на выбранном участке"
    build.pressed.connect(_build)
    layout.add_child(build)
    var reload := Button.new()
    reload.text = "Обновить кварталы"
    reload.pressed.connect(func(): api.load_sector())
    layout.add_child(reload)
    message = Label.new()
    message.text = "Выберите свободный участок на карте"
    layout.add_child(message)
    panel.visible = false

func _build() -> void:
    if api.access_token.is_empty() or world.selected_plot < 0:
        message.text = "Войдите и выберите участок"
        return
    var plot: Dictionary = world.plots[world.selected_plot]
    if not plot.has("id") or str(plot.get("owner_company_id", "")) not in ["", "<null>"]:
        message.text = "Нужен свободный участок с сервера"
        return
    var kind := {"commercial":"shop", "industrial":"workshop", "agricultural":"greenhouse"}.get(str(plot["zone"]), "")
    var payload := JSON.stringify({"company_id":company.text.strip_edges(), "plot_id":str(plot["id"]), "building_type":kind})
    var headers := PackedStringArray(["Authorization: Bearer " + api.access_token, "Content-Type: application/json"])
    var err := http.request(api.base_url + "/v1/world/buildings", headers, HTTPClient.METHOD_POST, payload)
    message.text = "Строительство..." if err == OK else "Нет соединения"

func _on_result(_result: int, status: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    if status == 201:
        var result: Variant = JSON.parse_string(body.get_string_from_utf8())
        message.text = "Построено! Новых участков: " + str(result.get("new_plots", 0))
        api.load_sector()
    else:
        message.text = "Ошибка строительства: HTTP " + str(status)
