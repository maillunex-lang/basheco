extends CanvasLayer
## Minimal login panel, intentionally does not persist credentials or tokens.
var api: Node
var endpoint: LineEdit
var email: LineEdit
var password: LineEdit
var status_label: Label
var panel: PanelContainer

func _ready() -> void:
    api = get_parent().get_node("API")
    api.authenticated.connect(_on_authenticated)
    api.request_failed.connect(_on_error)
    panel = PanelContainer.new()
    panel.position = Vector2(18, 82)
    panel.custom_minimum_size = Vector2(350, 0)
    add_child(panel)
    var layout := VBoxContainer.new()
    layout.add_theme_constant_override("separation", 9)
    panel.add_child(layout)
    var title := Label.new()
    title.text = "BASHECO · Вход в игру"
    title.add_theme_font_size_override("font_size", 20)
    layout.add_child(title)
    endpoint = LineEdit.new()
    endpoint.placeholder_text = "Адрес игрового API (HTTPS)"
    endpoint.text = "https://rikagro.ru/basheco/api"
    layout.add_child(endpoint)
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
    var demo_button := Button.new()
    demo_button.text = "Посмотреть карту без входа"
    demo_button.custom_minimum_size.y = 48
    demo_button.pressed.connect(func(): panel.visible = false)
    layout.add_child(demo_button)
    status_label = Label.new()
    status_label.text = "Для доступа необходима учётная запись"
    layout.add_child(status_label)

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
    api.load_sector()
    panel.visible = false

func _on_error(_code: int, message: String) -> void:
    status_label.text = message
    panel.visible = true
