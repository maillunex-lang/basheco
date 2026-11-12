extends CanvasLayer
## Company creation after login; no local persistence.
var api: Node
var http: HTTPRequest
var panel: PanelContainer
var name_field: LineEdit
var status_label: Label

func _ready() -> void:
    api = get_parent().get_node("API")
    http = HTTPRequest.new()
    add_child(http)
    http.request_completed.connect(_on_response)
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
    panel.visible = false
    api.authenticated.connect(func(): panel.visible = true)

func _create() -> void:
    if api.access_token.is_empty() or name_field.text.strip_edges().length() < 2:
        status_label.text = "Введите название и войдите"
        return
    var headers := PackedStringArray(["Authorization: Bearer " + api.access_token, "Content-Type: application/json"])
    var body := JSON.stringify({"name": name_field.text.strip_edges()})
    var err := http.request(api.base_url + "/v1/companies", headers, HTTPClient.METHOD_POST, body)
    status_label.text = "Создаём..." if err == OK else "Ошибка соединения"

func _on_response(_result: int, status: int, _headers: PackedStringArray, _body: PackedByteArray) -> void:
    status_label.text = "Компания создана" if status == 201 else "Ошибка: HTTP " + str(status)
    if status == 201:
        get_parent().get_node("Market").load_companies()
