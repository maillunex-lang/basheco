extends Node
## API transport. Never persist bearer tokens to disk.
signal sector_loaded(data: Dictionary)
signal request_failed(status: int, message: String)

var base_url := "http://127.0.0.1:4219"
var access_token := ""
var _http: HTTPRequest

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

func load_sector(sector_id: String = "ufa-prototype-01") -> void:
    if access_token.is_empty():
        request_failed.emit(401, "Необходим вход в игру")
        return
    var headers := PackedStringArray(["Authorization: Bearer " + access_token])
    var err := _http.request(base_url + "/v1/world/sectors/" + sector_id.uri_encode(), headers)
    if err != OK:
        request_failed.emit(0, "Ошибка соединения")

func _on_request_completed(_result: int, status: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    if status != 200:
        request_failed.emit(status, "Сервер не вернул сектор")
        return
    var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
    if typeof(parsed) != TYPE_DICTIONARY or not parsed.has("plots") or not parsed.has("sector"):
        request_failed.emit(0, "Неверный формат карты")
        return
    sector_loaded.emit(parsed)
