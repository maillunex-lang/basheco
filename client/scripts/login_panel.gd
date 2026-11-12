extends CanvasLayer
## Minimal login panel, intentionally does not persist credentials or tokens.
var api: Node
var endpoint: LineEdit
var display_name: LineEdit
var email: LineEdit
var password: LineEdit
var status_label: Label
var panel: PanelContainer
var backdrop: ColorRect

func _ready() -> void:
    api = get_parent().get_node("API")
    api.authenticated.connect(_on_authenticated)
    api.request_failed.connect(_on_error)
    backdrop = ColorRect.new()
    backdrop.color = Color("#101c28")
    backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    add_child(backdrop)
    panel = PanelContainer.new()
    panel.custom_minimum_size = Vector2(390, 0)
    add_child(panel)
    get_viewport().size_changed.connect(_layout)
    call_deferred("_layout")
    var layout := VBoxContainer.new()
    layout.add_theme_constant_override("separation", 9)
    panel.add_child(layout)
    var title := Label.new()
    title.text = "BASHECO\nЭКОНОМИЧЕСКАЯ MMO"
    title.add_theme_font_size_override("font_size", 20)
    layout.add_child(title)
    endpoint = LineEdit.new()
    endpoint.placeholder_text = "Адрес игрового API (HTTPS)"
    endpoint.text = "https://rikagro.ru/basheco/api"
    endpoint.visible = false
    layout.add_child(endpoint)
    display_name = LineEdit.new()
    display_name.placeholder_text = "Имя игрока"
    layout.add_child(display_name)
    email = LineEdit.new()
    email.placeholder_text = "Электронная почта"
    layout.add_child(email)
    password = LineEdit.new()
    password.placeholder_text = "Пароль"
    password.secret = true
    layout.add_child(password)
    var button := Button.new()
    button.text = "Войти и загрузить квартал"
    button.custom_minimum_size.y = 48
    button.pressed.connect(_login)
    layout.add_child(button)
    var register_button := Button.new()
    register_button.text = "Регистрация"
    register_button.pressed.connect(_register)
    layout.add_child(register_button)
    var demo_button := Button.new()
    demo_button.text = "Посмотреть карту без входа"
    demo_button.custom_minimum_size.y = 48
    demo_button.pressed.connect(_preview_map)
    layout.add_child(demo_button)
    status_label = Label.new()
    status_label.text = "Уфа · Закрытая Alpha 0.1"
    layout.add_child(status_label)

func _layout() -> void:
    var size := get_viewport().get_visible_rect().size
    panel.position = Vector2((size.x - panel.size.x) * 0.5, maxf(24.0, (size.y - panel.size.y) * 0.5))

func _preview_map() -> void:
    panel.visible = false
    backdrop.visible = false
    get_parent().world_visible = true
    get_parent().get_node("Navigation").show()
    get_parent().get_node("HUD").show()
    get_parent().queue_redraw()

var registration_http: HTTPRequest

func _register() -> void:
    var url := endpoint.text.strip_edges().trim_suffix("/")
    if not url.begins_with("https://") and not url.begins_with("http://127.0.0.1:"):
        status_label.text = "Для регистрации требуется HTTPS"
        return
    if display_name.text.strip_edges().length() < 2:
        status_label.text = "Укажите имя игрока"
        return
    if password.text.length() < 12:
        status_label.text = "Пароль: минимум 12 символов"
        return
    if registration_http == null:
        registration_http = HTTPRequest.new()
        add_child(registration_http)
        registration_http.request_completed.connect(_on_register_result)
    var body := JSON.stringify({
        "email": email.text.strip_edges(),
        "display_name": display_name.text.strip_edges(),
        "password": password.text
    })
    password.clear()
    var headers := PackedStringArray(["Content-Type: application/json"])
    var result := registration_http.request(url + "/v1/auth/register", headers, HTTPClient.METHOD_POST, body)
    status_label.text = "Регистрация..." if result == OK else "Не удалось отправить запрос"

func _on_register_result(_result: int, status: int, _headers: PackedStringArray, _body: PackedByteArray) -> void:
    status_label.text = "Аккаунт создан. Теперь войдите." if status == 201 else "Ошибка регистрации: HTTP " + str(status)

func _login() -> void:
    var url := endpoint.text.strip_edges()
    if not url.begins_with("https://") and not url.begins_with("http://127.0.0.1:"):
        status_label.text = "Разрешён только HTTPS"
        return
    api.configure(url, "")
    status_label.text = "Подключение..."
    api.login(email.text.strip_edges(), password.text)
    password.clear()

func _on_authenticated() -> void:
    status_label.text = "Вход выполнен"
    get_parent().connect_to_server(api.base_url, api.access_token)
    panel.visible = false
    backdrop.visible = false
    get_parent().get_node("Navigation").show()
    get_parent().queue_redraw()

func _on_error(_code: int, message: String) -> void:
    status_label.text = message
    panel.visible = true
    backdrop.visible = true
