extends CanvasLayer
## Minimal login panel, intentionally does not persist credentials or tokens.
var api: Node
var endpoint: LineEdit
var display_name: LineEdit
var email: LineEdit
var password: LineEdit
var status_label: Label
var panel: PanelContainer
var scroll: ScrollContainer
var center: CenterContainer
var backdrop: ColorRect
var heading: Label
var login_button: Button
var register_button: Button
var demo_button: Button
var busy := false

func _ready() -> void:
    api = get_parent().get_node("API")
    api.authenticated.connect(_on_authenticated)
    api.request_failed.connect(_on_error)
    backdrop = ColorRect.new()
    backdrop.color = Color("#101c28")
    backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    add_child(backdrop)
    scroll = ScrollContainer.new()
    scroll.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    add_child(scroll)
    center = CenterContainer.new()
    center.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    center.size_flags_vertical = Control.SIZE_EXPAND_FILL
    scroll.add_child(center)
    panel = PanelContainer.new()
    panel.custom_minimum_size = Vector2(440, 0)
    panel.add_theme_stylebox_override("panel", _card_style())
    center.add_child(panel)
    get_viewport().size_changed.connect(_layout)
    var layout := VBoxContainer.new()
    layout.add_theme_constant_override("separation", 12)
    panel.add_child(layout)
    var eyebrow := Label.new()
    eyebrow.text = "РЕСПУБЛИКА БАШКОРТОСТАН  •  ЗАКРЫТАЯ АЛЬФА"
    eyebrow.add_theme_color_override("font_color", Color("#8dcac2"))
    eyebrow.add_theme_font_size_override("font_size", 12)
    layout.add_child(eyebrow)
    heading = Label.new()
    heading.text = "BASHECO"
    heading.add_theme_font_size_override("font_size", 38)
    heading.add_theme_color_override("font_color", Color("#f0f7f5"))
    layout.add_child(heading)
    var subtitle := Label.new()
    subtitle.text = "Строй предприятия. Развивай города. Создай свою экономику."
    subtitle.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    subtitle.add_theme_color_override("font_color", Color("#b5c9cc"))
    layout.add_child(subtitle)
    var divider := HSeparator.new()
    layout.add_child(divider)
    endpoint = LineEdit.new()
    endpoint.placeholder_text = "Адрес игрового API (HTTPS)"
    endpoint.text = "https://rikagro.ru/basheco/api"
    endpoint.visible = false
    layout.add_child(endpoint)
    display_name = LineEdit.new()
    display_name.placeholder_text = "Имя игрока (для регистрации)"
    display_name.custom_minimum_size.y = 46
    layout.add_child(display_name)
    email = LineEdit.new()
    email.placeholder_text = "Электронная почта"
    email.custom_minimum_size.y = 46
    layout.add_child(email)
    password = LineEdit.new()
    password.placeholder_text = "Пароль"
    password.secret = true
    password.custom_minimum_size.y = 46
    password.text_submitted.connect(func(_value: String): _login())
    layout.add_child(password)
    login_button = Button.new()
    login_button.text = "Войти в игру"
    login_button.custom_minimum_size.y = 50
    login_button.add_theme_stylebox_override("normal", _primary_style())
    login_button.pressed.connect(_login)
    layout.add_child(login_button)
    register_button = Button.new()
    register_button.text = "Создать аккаунт"
    register_button.custom_minimum_size.y = 46
    register_button.pressed.connect(_register)
    layout.add_child(register_button)
    demo_button = Button.new()
    demo_button.text = "Посмотреть карту без входа"
    demo_button.custom_minimum_size.y = 46
    demo_button.pressed.connect(_preview_map)
    layout.add_child(demo_button)
    status_label = Label.new()
    status_label.text = "Для строительства и торговли нужен игровой аккаунт."
    status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    status_label.add_theme_color_override("font_color", Color("#b5c9cc"))
    layout.add_child(status_label)
    call_deferred("_layout")

func _card_style() -> StyleBoxFlat:
    var style := StyleBoxFlat.new()
    style.bg_color = Color("#142634")
    style.border_color = Color("#2b565a")
    style.set_border_width_all(1)
    style.set_corner_radius_all(16)
    style.set_content_margin_all(24)
    return style

func _primary_style() -> StyleBoxFlat:
    var style := StyleBoxFlat.new()
    style.bg_color = Color("#287b74")
    style.set_corner_radius_all(10)
    return style

func _layout() -> void:
    var size := get_viewport().get_visible_rect().size
    var margin := 16.0
    var desired_width: float = minf(440.0, maxf(280.0, size.x - 2.0 * margin))
    panel.custom_minimum_size.x = desired_width
    panel.size.x = desired_width
    # On short landscape screens the card can scroll instead of clipping controls.
    center.custom_minimum_size = Vector2(size.x, size.y)
    panel.custom_minimum_size.x = desired_width

func _set_busy(value: bool) -> void:
    busy = value
    login_button.disabled = value
    register_button.disabled = value


func _preview_map() -> void:
    scroll.visible = false
    backdrop.visible = false
    get_parent().world_visible = true
    get_parent().get_node("Navigation").show()
    get_parent().get_node("HUD").show()
    get_parent().queue_redraw()

var registration_http: HTTPRequest

func _register() -> void:
    if busy:
        return
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
    _set_busy(result == OK)

func _on_register_result(_result: int, status: int, _headers: PackedStringArray, _body: PackedByteArray) -> void:
    _set_busy(false)
    status_label.text = "Аккаунт создан. Теперь войдите." if status == 201 else "Ошибка регистрации: HTTP " + str(status)

func _login() -> void:
    if busy:
        return
    var url := endpoint.text.strip_edges()
    if not url.begins_with("https://") and not url.begins_with("http://127.0.0.1:"):
        status_label.text = "Разрешён только HTTPS"
        return
    api.configure(url, "")
    status_label.text = "Подключение..."
    if email.text.strip_edges().is_empty() or password.text.is_empty():
        status_label.text = "Введите почту и пароль"
        return
    _set_busy(true)
    api.login(email.text.strip_edges(), password.text)
    password.clear()

func _on_authenticated() -> void:
    _set_busy(false)
    status_label.text = "Вход выполнен"
    get_parent().connect_to_server(api.base_url, api.access_token)
    scroll.visible = false
    backdrop.visible = false
    get_parent().get_node("Navigation").show()
    get_parent().queue_redraw()

func _on_error(_code: int, message: String) -> void:
    _set_busy(false)
    status_label.text = message
    scroll.visible = true
    backdrop.visible = true