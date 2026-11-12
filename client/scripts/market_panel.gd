extends CanvasLayer
## Authenticated marketplace. All financial checks remain on the server.
var api: Node
var http: HTTPRequest
var panel: PanelContainer
var info: Label
var listing_selector: OptionButton
var company_field: LineEdit
var resource_field: LineEdit
var quantity_field: SpinBox
var price_field: SpinBox
var listings: Array = []
var pending := ""
var busy := false

func _ready() -> void:
    api = get_parent().get_node("API")
    http = HTTPRequest.new()
    add_child(http)
    http.request_completed.connect(_on_response)
    panel = PanelContainer.new()
    panel.position = Vector2(390, 82)
    panel.custom_minimum_size = Vector2(360, 0)
    add_child(panel)
    var layout := VBoxContainer.new()
    panel.add_child(layout)
    var title := Label.new()
    title.text = "Рынок BASHECO"
    title.add_theme_font_size_override("font_size", 20)
    layout.add_child(title)
    company_field = LineEdit.new()
    company_field.placeholder_text = "UUID вашей компании"
    layout.add_child(company_field)
    resource_field = LineEdit.new()
    resource_field.placeholder_text = "Код ресурса (например, vegetables)"
    resource_field.text = "vegetables"
    layout.add_child(resource_field)
    quantity_field = SpinBox.new()
    quantity_field.min_value = 1
    quantity_field.max_value = 1000000
    quantity_field.value = 1
    layout.add_child(_caption("Количество"))
    layout.add_child(quantity_field)
    price_field = SpinBox.new()
    price_field.min_value = 1
    price_field.max_value = 1000000000
    price_field.value = 100
    layout.add_child(_caption("Цена за единицу, игровые копейки"))
    layout.add_child(price_field)
    listing_selector = OptionButton.new()
    layout.add_child(_caption("Предложения игроков"))
    layout.add_child(listing_selector)
    var refresh := Button.new()
    refresh.text = "Обновить предложения"
    refresh.pressed.connect(refresh_listings)
    layout.add_child(refresh)
    var sell := Button.new()
    sell.text = "Выставить на продажу"
    sell.pressed.connect(_sell)
    layout.add_child(sell)
    var buy_button := Button.new()
    buy_button.text = "Купить выбранное"
    buy_button.pressed.connect(_buy)
    layout.add_child(buy_button)
    var cancel := Button.new()
    cancel.text = "Снять своё предложение"
    cancel.pressed.connect(_cancel)
    layout.add_child(cancel)
    info = Label.new()
    info.text = "Войдите в игру для торговли"
    layout.add_child(info)
    api.authenticated.connect(refresh_listings)
    panel.visible = false

func _caption(value: String) -> Label:
    var label := Label.new()
    label.text = value
    return label

func _headers(json_body: bool = false) -> PackedStringArray:
    var headers := PackedStringArray(["Authorization: Bearer " + api.access_token])
    if json_body:
        headers.append("Content-Type: application/json")
    return headers

func _request(kind: String, path: String, method: int = HTTPClient.METHOD_GET, payload: String = "") -> void:
    if busy or api.access_token.is_empty():
        return
    pending = kind
    busy = true
    var err := http.request(api.base_url + path, _headers(method != HTTPClient.METHOD_GET), method, payload)
    if err != OK:
        busy = false
        info.text = "Нет соединения"

func refresh_listings() -> void:
    panel.visible = true
    _request("list", "/v1/market/listings")

func _sell() -> void:
    var payload := JSON.stringify({
        "company_id": company_field.text.strip_edges(),
        "resource_code": resource_field.text.strip_edges(),
        "quantity": int(quantity_field.value),
        "unit_price_kopecks": int(price_field.value)
    })
    _request("sell", "/v1/market/listings", HTTPClient.METHOD_POST, payload)

func _selected_id() -> String:
    if listing_selector.selected < 0:
        return ""
    return str(listing_selector.get_item_metadata(listing_selector.selected))

func _buy() -> void:
    var listing_id := _selected_id()
    if listing_id.is_empty():
        return
    var payload := JSON.stringify({
        "company_id": company_field.text.strip_edges(),
        "quantity": int(quantity_field.value),
        "idempotency_key": "buy-" + str(Time.get_ticks_usec()) + "-" + str(randi())
    })
    _request("buy", "/v1/market/listings/" + listing_id + "/buy", HTTPClient.METHOD_POST, payload)

func _cancel() -> void:
    var listing_id := _selected_id()
    if not listing_id.is_empty():
        _request("cancel", "/v1/market/listings/" + listing_id + "/cancel", HTTPClient.METHOD_POST, "{}")

func _on_response(_result: int, status: int, _headers_result: PackedStringArray, body: PackedByteArray) -> void:
    busy = false
    var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
    if status < 200 or status >= 300 or typeof(parsed) != TYPE_DICTIONARY:
        info.text = "Ошибка рынка: HTTP " + str(status)
        return
    if pending == "list":
        listings = parsed.get("listings", [])
        listing_selector.clear()
        for listing in listings:
            listing_selector.add_item("%s · %s шт. · %s коп." % [
                str(listing.get("resource_code", "?")),
                str(listing.get("quantity_remaining", 0)),
                str(listing.get("unit_price_kopecks", 0))
            ])
            listing_selector.set_item_metadata(listing_selector.item_count - 1, str(listing["id"]))
        info.text = "Активных предложений: " + str(listings.size())
    else:
        info.text = "Операция выполнена: " + pending
        refresh_listings()
