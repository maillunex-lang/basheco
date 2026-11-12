extends CanvasLayer
## Company creation after login; no local persistence.
var api: Node
var http: HTTPRequest
var starter_http: HTTPRequest
var panel: PanelContainer
var name_field: LineEdit
signal companies_updated(companies: Array)
signal wallets_updated(wallets: Array)
var wallet_http: HTTPRequest
var balances_label: Label
var companies: Array = []
var pending := ""
var busy := false
var status_label: Label

func _ready() -> void:
    api = get_parent().get_node("API")
    http = HTTPRequest.new()
    add_child(http)
    http.request_completed.connect(_on_response)
    starter_http = HTTPRequest.new()
    add_child(starter_http)
    starter_http.request_completed.connect(_on_starter_response)
    wallet_http = HTTPRequest.new()
    add_child(wallet_http)
    wallet_http.request_completed.connect(_on_wallet_response)
    api.authenticated.connect(load_companies)
    panel = PanelContainer.new()
    panel.position = Vector2(770, 82)
    panel.custom_minimum_size = Vector2(290, 0)
    add_child(panel)
    var layout := VBoxContainer.new()
    panel.add_child(layout)
    var title := Label.new()
    title.text = "Моя компания"
    layout.add_child(title)
    name_field = LineEdit.new()
    name_field.placeholder_text = "Название компании"
    layout.add_child(name_field)
    var button := Button.new()
    button.text = "Создать компанию"
    button.pressed.connect(_create)
    layout.add_child(button)
    status_label = Label.new()
    status_label.text = "Войдите в игру"
    layout.add_child(status_label)
    balances_label = Label.new()
    balances_label.text = "Баланс: войдите в игру"
    balances_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    layout.add_child(balances_label)
    panel.visible = false

func _create() -> void:
    if busy or api.access_token.is_empty() or name_field.text.strip_edges().length() < 2:
        status_label.text = "Введите название и войдите"
        return
    var headers := PackedStringArray(["Authorization: Bearer " + api.access_token, "Content-Type: application/json"])
    var body := JSON.stringify({"name": name_field.text.strip_edges()})
    pending = "create"
    busy = true
    var err := http.request(api.base_url + "/v1/companies", headers, HTTPClient.METHOD_POST, body)
    if err != OK:
        busy = false
    status_label.text = "Создаём..." if err == OK else "Ошибка соединения"

func load_companies() -> void:
    if api.access_token.is_empty() or busy:
        return
    pending = "list"
    busy = true
    var headers := PackedStringArray(["Authorization: Bearer " + api.access_token])
    var err := http.request(api.base_url + "/v1/companies", headers)
    if err != OK:
        busy = false
        status_label.text = "Не удалось получить компании"

func _on_response(_result: int, status: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    busy = false
    if pending == "create":
        status_label.text = "Компания создана" if status == 201 else "Ошибка: HTTP " + str(status)
        if status == 201:
            name_field.clear()
            load_companies.call_deferred()
        return
    if status != 200:
        status_label.text = "Ошибка загрузки компаний: HTTP " + str(status)
        return
    var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
    if typeof(parsed) != TYPE_DICTIONARY:
        return
    companies = parsed.get("companies", [])
    status_label.text = "Мои компании: " + str(companies.size()) if companies.size() > 0 else "Создайте первую компанию"
    companies_updated.emit(companies)
    load_wallets()
    if not companies.is_empty():
        var headers := PackedStringArray(["Authorization: Bearer " + api.access_token])
        starter_http.request(api.base_url + "/v1/companies/" + str(companies[0]["id"]) + "/starter-grant", headers, HTTPClient.METHOD_POST, "{}")

func _on_starter_response(_result: int, status: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    if status != 200:
        return
    var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
    if typeof(parsed) == TYPE_DICTIONARY and int(parsed.get("granted_kopecks", 0)) > 0:
        status_label.text = "Стартовый капитал: 10 000 игровых ₽ начислен!"
    load_wallets()

func load_wallets() -> void:
    if api.access_token.is_empty() or wallet_http.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED:
        return
    var headers := PackedStringArray(["Authorization: Bearer " + api.access_token])
    var err := wallet_http.request(api.base_url + "/v1/wallets", headers)
    if err != OK:
        balances_label.text = "Баланс: нет соединения"

func _on_wallet_response(_result: int, status: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    if status != 200:
        balances_label.text = "Баланс: ошибка HTTP " + str(status)
        return
    var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
    if typeof(parsed) != TYPE_DICTIONARY or typeof(parsed.get("wallets")) != TYPE_ARRAY:
        balances_label.text = "Баланс: неверный ответ сервера"
        return
    var wallets: Array = parsed["wallets"]
    var amounts: Dictionary = {}
    for wallet in wallets:
        if typeof(wallet) == TYPE_DICTIONARY and wallet.get("company_id") != null:
            amounts[str(wallet["company_id"])] = int(wallet.get("balance_kopecks", 0))
    var rows := PackedStringArray()
    for owned in companies:
        var id := str(owned.get("id", ""))
        if amounts.has(id):
            var kopecks: int = amounts[id]
            rows.append("%s: %d,%02d ₽" % [str(owned.get("name", "Компания")), int(kopecks / 100), absi(kopecks % 100)])
    balances_label.text = "\n".join(rows) if not rows.is_empty() else "Баланс компании: нет данных"
    wallets_updated.emit(wallets)