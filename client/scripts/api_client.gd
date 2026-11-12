extends Node
const WorldGrid = preload("res://scripts/world_grid.gd")
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

## Parcels of every settlement inside a rectangle of GLOBAL world cells.
func load_viewport(bounds: Array[int]) -> void:
    if access_token.is_empty() or _http.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED:
        return
    if bounds.size() != 4:
        return
    _request_kind = "viewport"
    var headers := PackedStringArray(["Authorization: Bearer " + access_token])
    var query := "?min_cell_x=%d&min_cell_y=%d&max_cell_x=%d&max_cell_y=%d" % [bounds[0], bounds[1], bounds[2], bounds[3]]
    var err := _http.request(base_url + "/v1/world/viewport" + query, headers)
    if err != OK:
        request_failed.emit(0, "Ошибка загрузки участков")


func _on_request_completed(_result: int, status: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    if status != 200:
        request_failed.emit(status, "Ошибка авторизации" if _request_kind == "login" else "Сервер не вернул карту")
        return
    var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
    if _request_kind == "login":
        if typeof(parsed) == TYPE_DICTIONARY and parsed.has("access_token"):
            access_token = str(parsed["access_token"])
            authenticated.emit()
        else:
            request_failed.emit(0, "Неверный ответ авторизации")
        return
    if typeof(parsed) != TYPE_DICTIONARY or typeof(parsed.get("plots")) != TYPE_ARRAY:
        request_failed.emit(0, "Неверный формат карты")
        return
    if _request_kind == "viewport":
        # The server is authoritative for the grid: refuse to place plots from another one.
        if typeof(parsed.get("grid")) != TYPE_DICTIONARY or not WorldGrid.matches(parsed["grid"]):
            request_failed.emit(0, "Версия карты сервера не совпадает с клиентом")
            return
    elif not parsed.has("sector"):
        request_failed.emit(0, "Неверный формат карты")
        return
    sector_loaded.emit(parsed)
