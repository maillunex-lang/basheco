extends Node
## API transport. Never persist bearer tokens to disk.
signal sector_loaded(data: Dictionary)
signal authenticated()
signal request_failed(status: int, message: String)

var base_url := "http://127.0.0.1:4219"
var access_token := ""
var _http: HTTPRequest
var _request_kind := ""

func _ready() -> void:
    _http = HTTPRequest.new()
    add_child(_http)
    _http.request_completed.connect(_on_request_completed)

func configure(url: String, token: String) -> void:
    if not url.begins_with("https://") and not url.begins_with("http://127.0.0.1:"):
        request_failed.emit(0, "Требуется HTTPS или локальный сервер")
        return
    base_url = url.trim_suffix("/")
    access_token = token

func login(email: String, password: String) -> void:
    if email.is_empty() or password.is_empty():
        request_failed.emit(422, "Введите почту и пароль")
        return
    _request_kind = "login"
    var headers := PackedStringArray(["Content-Type: application/json"])
    var payload := JSON.stringify({"email": email, "password": password})
    var err := _http.request(base_url + "/v1/auth/login", headers, HTTPClient.METHOD_POST, payload)
    if err != OK:
        request_failed.emit(0, "Ошибка соединения")

func load_sector(sector_id: String = "ufa") -> void:
    if access_token.is_empty():
        request_failed.emit(401, "Необходим вход в игру")
        return
    _request_kind = "sector"
    var headers := PackedStringArray(["Authorization: Bearer " + access_token])
    var err := _http.request(base_url + "/v1/world/sectors/" + sector_id.uri_encode(), headers)
    if err != OK:
        request_failed.emit(0, "Ошибка соединения")

func load_viewport(sector_id: String, bounds: Array[int]) -> void:
    if access_token.is_empty() or _http.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED:
        return
    if bounds.size() != 4:
        return
    _request_kind = "viewport"
    var headers := PackedStringArray(["Authorization: Bearer " + access_token])
    var query := "?min_x=%d&min_y=%d&max_x=%d&max_y=%d" % [bounds[0], bounds[1], bounds[2], bounds[3]]
    var err := _http.request(base_url + "/v1/world/sectors/" + sector_id.uri_encode() + "/viewport" + query, headers)
    if err != OK:
        request_failed.emit(0, "Ошибка загрузки участков")


func _on_request_completed(_result: int, status: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    if status != 200:
        request_failed.emit(status, "Ошибка авторизации" if _request_kind == "login" else "Сервер не вернул сектор")
        return
    var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
    if _request_kind == "login":
        if typeof(parsed) == TYPE_DICTIONARY and parsed.has("access_token"):
            access_token = str(parsed["access_token"])
            authenticated.emit()
        else:
            request_failed.emit(0, "Неверный ответ авторизации")
        return
    if typeof(parsed) != TYPE_DICTIONARY or not parsed.has("plots") or not parsed.has("sector"):
        request_failed.emit(0, "Неверный формат карты")
        return
    sector_loaded.emit(parsed)
