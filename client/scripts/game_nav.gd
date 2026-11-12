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

func _ready() -> void:
    var frame := PanelContainer.new()
    frame.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
    frame.offset_top = -76
    frame.offset_bottom = 0
    frame.mouse_filter = Control.MOUSE_FILTER_STOP
    add_child(frame)
    bar = HBoxContainer.new()
    bar.alignment = BoxContainer.ALIGNMENT_CENTER
    bar.add_theme_constant_override("separation", 8)
    frame.add_child(bar)
    for item in ITEMS:
        var button := Button.new()
        button.text = item[0]
        button.icon = load(item[1])
        button.expand_icon = true
        button.custom_minimum_size = Vector2(118, 64)
        button.pressed.connect(_show_section.bind(item[2]))
        bar.add_child(button)
    get_parent().get_node("Economy").panel.visible = false
    get_viewport().size_changed.connect(_layout)
    _layout()

func _layout() -> void:
    var size := get_viewport().get_visible_rect().size
    var scale_factor: float = clampf(size.x / 1280.0, 0.68, 1.1)
    bar.add_theme_constant_override("separation", int(8 * scale_factor))
    for button in bar.get_children():
        button.custom_minimum_size = Vector2(118 * scale_factor, 58)
    for name in ["Company", "Economy", "Market", "Build"]:
        var node: Node = get_parent().get_node(name)
        if node.panel != null:
            node.panel.position = Vector2(maxf(12.0, size.x - 385.0), 90.0)
            node.panel.custom_minimum_size.x = minf(360.0, size.x - 24.0)

func _show_section(section: String) -> void:
    for name in ["Company", "Economy", "Market", "Build"]:
        var node: Node = get_parent().get_node(name)
        if node.panel != null:
            node.panel.visible = name == section
    if section == "Market":
        get_parent().get_node("Market").refresh_listings()
