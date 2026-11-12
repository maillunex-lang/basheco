extends CanvasLayer
## Responsive navigation, original icon assets, no fabricated balances.
const ITEMS := [
    ["Карта", "res://assets/icons/warehouse.svg", ""],
    ["Компания", "res://assets/icons/company.svg", "Company"],
    ["Стройка", "res://assets/icons/warehouse.svg", "Build"],
    ["Производство", "res://assets/icons/workshop.svg", "Economy"],
    ["Рынок", "res://assets/icons/market.svg", "Market"]
]
var bar: HBoxContainer
var buttons: Dictionary = {}
var active_section := ""
var frame: PanelContainer

func _ready() -> void:
    hide()
    frame = PanelContainer.new()
    frame.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
    frame.offset_top = -76
    frame.offset_bottom = 0
    frame.mouse_filter = Control.MOUSE_FILTER_STOP
    frame.add_theme_stylebox_override("panel", _panel_style())
    add_child(frame)
    bar = HBoxContainer.new()
    bar.alignment = BoxContainer.ALIGNMENT_CENTER
    bar.add_theme_constant_override("separation", 8)
    frame.add_child(bar)
    for item in ITEMS:
        var button := Button.new()
        button.text = item[0]
        button.add_theme_stylebox_override("normal", _button_style(false))
        button.add_theme_stylebox_override("hover", _button_style(true))
        button.add_theme_stylebox_override("pressed", _button_style(true))
        button.add_theme_color_override("font_color", Color("#e5edf1"))
        button.icon = load(item[1])
        button.expand_icon = true
        button.tooltip_text = item[0]
        button.focus_mode = Control.FOCUS_ALL
        button.custom_minimum_size = Vector2(118, 64)
        button.pressed.connect(_show_section.bind(item[2]))
        bar.add_child(button)
        buttons[item[2]] = button
    for name in ["Company", "Economy", "Market", "Build"]:
        var section_panel: PanelContainer = get_parent().get_node(name).panel
        section_panel.add_theme_stylebox_override("panel", _panel_style())
        section_panel.visible = false
    get_viewport().size_changed.connect(_layout)
    _layout()
    _update_active()

func _panel_style() -> StyleBoxFlat:
    var style := StyleBoxFlat.new()
    style.bg_color = Color("#142634")
    style.border_color = Color("#2c4654")
    style.border_width_top = 2
    style.content_margin_left = 12
    style.content_margin_right = 12
    style.set_corner_radius_all(12)
    style.content_margin_top = 10
    style.content_margin_bottom = 7
    return style

func _button_style(active: bool) -> StyleBoxFlat:
    var style := StyleBoxFlat.new()
    style.bg_color = Color("#28616a") if active else Color("#203844")
    style.set_corner_radius_all(10)
    style.content_margin_left = 8
    style.content_margin_right = 8
    return style

func _layout() -> void:
    var viewport_size := get_viewport().get_visible_rect().size
    var compact := viewport_size.x < 900.0
    var available_width: float = maxf(320.0, viewport_size.x - 24.0)
    var button_width: float = clampf((available_width - 48.0) / float(ITEMS.size()), 58.0, 150.0)
    frame.offset_left = 0
    frame.offset_right = 0
    frame.offset_top = -70 if compact else -78
    frame.offset_bottom = 0
    bar.add_theme_constant_override("separation", 4 if compact else 8)
    for item in ITEMS:
        var button: Button = buttons[item[2]]
        button.custom_minimum_size = Vector2(button_width, 52 if compact else 58)
        button.add_theme_font_size_override("font_size", 12 if compact else 15)
        button.text = item[0] if not compact else {"Карта": "Карта", "Компания": "Фирма", "Стройка": "Стройка", "Производство": "Цех", "Рынок": "Рынок"}.get(item[0], item[0])
    for name in ["Company", "Economy", "Market", "Build"]:
        var node: Node = get_parent().get_node(name)
        if node.panel != null:
            node.panel.position = Vector2(maxf(12.0, viewport_size.x - 385.0), 90.0)
            node.panel.custom_minimum_size.x = minf(360.0, viewport_size.x - 24.0)
            if name == "Build" and node.scroll != null:
                node.scroll.custom_minimum_size.y = minf(440.0, maxf(220.0, viewport_size.y - 185.0))

func _update_active() -> void:
    for section in buttons:
        var button: Button = buttons[section]
        var selected: bool = section == active_section
        button.add_theme_stylebox_override("normal", _button_style(selected))
        button.add_theme_color_override("font_color", Color("#ffffff") if selected else Color("#e5edf1"))
        button.set_pressed_no_signal(selected)

func _show_section(section: String) -> void:
    active_section = section
    _update_active()
    for name in ["Company", "Economy", "Market", "Build"]:
        var node: Node = get_parent().get_node(name)
        if node.panel != null:
            node.panel.visible = name == section
    get_parent().get_node("Geography").hide()
    if section == "Company":
        get_parent().get_node("Company").load_wallets()
    if section == "Market":
        get_parent().get_node("Market").refresh_listings()