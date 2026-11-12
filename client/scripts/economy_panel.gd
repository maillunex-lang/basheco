extends CanvasLayer
## Small authenticated economy panel; requests are never trusted for resource amounts.
var api: Node
var http: HTTPRequest
var panel: PanelContainer
var details: Label
var recipe_select: OptionButton
var action: Button
var building_id := ""
var recipes: Array = []
var busy := false
var request_kind := ""

func _ready() -> void:
    api = get_parent().get_node("API")
    http = HTTPRequest.new()
    add_child(http)
    http.request_completed.connect(_on_response)
    panel = PanelContainer.new()
    panel.position = Vector2(18, 345)
    panel.custom_minimum_size = Vector2(350, 0)
    add_child(panel)
    var layout := VBoxContainer.new()
    panel.add_child(layout)
    var title := Label.new()
    title.text = "🏭 Предприятие и производство"
    layout.add_child(title)
    details = Label.new()
    details.text = "Выберите построенное предприятие"
    layout.add_child(details)
    recipe_select = OptionButton.new()
    layout.add_child(recipe_select)
    action = Button.new()
    action.text = "Запустить производство"
    action.custom_minimum_size.y = 48
    action.pressed.connect(_produce)
    layout.add_child(action)
    var refresh := Button.new()
    refresh.text = "Обновить рецепты"
    refresh.pressed.connect(load_catalog)
    layout.add_child(refresh)
    api.authenticated.connect(load_catalog)
    _update()

func choose_plot(plot: Dictionary) -> void:
    building_id = str(plot.get("building_id", "")) if plot.get("building_id") != null else ""
    details.text = "Здание: " + str(plot.get("building_type","не построено"))
    _update()

func _update() -> void:
    action.disabled = busy or building_id.is_empty() or api.access_token.is_empty() or recipe_select.item_count == 0

func load_catalog() -> void:
    if api.access_token.is_empty() or busy:
        return
    busy = true
    request_kind = "catalog"
    _update()
    var headers := PackedStringArray(["Authorization: Bearer " + api.access_token])
    var err := http.request(api.base_url + "/v1/economy/catalog", headers)
    if err != OK:
        _error("Нет соединения")

func _produce() -> void:
    if busy or building_id.is_empty() or recipe_select.selected < 0:
        return
    busy = true
    request_kind = "produce"
    _update()
    var code := str(recipe_select.get_item_metadata(recipe_select.selected))
    var key := "production-" + str(Time.get_ticks_usec()) + "-" + str(randi())
    var payload := JSON.stringify({"building_id":building_id,"recipe_code":code,"idempotency_key":key})
    var headers := PackedStringArray(["Authorization: Bearer " + api.access_token,"Content-Type: application/json"])
    var err := http.request(api.base_url + "/v1/economy/produce",headers,HTTPClient.METHOD_POST,payload)
    if err != OK:
        _error("Нет соединения")

func _on_response(_result: int, status: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    busy = false
    var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
    if status < 200 or status >= 300 or typeof(parsed) != TYPE_DICTIONARY:
        _error("Ошибка сервера: " + str(status))
        return
    if request_kind == "catalog":
        recipes = parsed.get("recipes",[])
        recipe_select.clear()
        for item in recipes:
            recipe_select.add_item(str(item["code"]))
            recipe_select.set_item_metadata(recipe_select.item_count - 1,str(item["code"]))
        details.text = "Рецепты загружены. Выберите предприятие."
    else:
        details.text = "Произведено: " + str(parsed.get("resource","")) + " × " + str(parsed.get("quantity",0))
    _update()

func _error(message: String) -> void:
    busy = false
    details.text = message
    _update()
