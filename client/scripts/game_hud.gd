extends CanvasLayer
## Mobile-first top status and map controls. Never invents balances.
var world: Node2D
var company_label: Label
var district_label: Label
var frame: PanelContainer
var geo_credit: Label

func _ready() -> void:
    world = get_parent()
    frame = PanelContainer.new()
    frame.add_theme_stylebox_override("panel", _surface())
    add_child(frame)
    var row := HBoxContainer.new()
    row.add_theme_constant_override("separation", 12)
    frame.add_child(row)
    district_label = Label.new()
    district_label.text = "УФА  •  ЦЕНТРАЛЬНЫЙ КВАРТАЛ"
    district_label.add_theme_color_override("font_color", Color("#e8f2ef"))
    row.add_child(district_label)
    var divider := VSeparator.new()
    row.add_child(divider)
    company_label = Label.new()
    company_label.text = "Компания не выбрана"
    company_label.add_theme_color_override("font_color", Color("#e8f2ef"))
    row.add_child(company_label)
    var spacer := Control.new()
    spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    row.add_child(spacer)
    var minus := Button.new()
    minus.text = "−"
    minus.custom_minimum_size = Vector2(44, 42)
    minus.pressed.connect(func(): world.zoom_at(get_viewport().get_visible_rect().size * 0.5, 1.0 / 1.2))
    row.add_child(minus)
    var center := Button.new()
    center.text = "⌖ Район"
    center.custom_minimum_size = Vector2(92, 42)
    center.pressed.connect(world._focus_on_district)
    row.add_child(center)
    var plus := Button.new()
    plus.text = "+"
    plus.custom_minimum_size = Vector2(44, 42)
    plus.pressed.connect(func(): world.zoom_at(get_viewport().get_visible_rect().size * 0.5, 1.2))
    row.add_child(plus)
    geo_credit = Label.new()
    geo_credit.text = "© OpenStreetMap contributors · ODbL 1.0 · География: пилот, не вся Уфа"
    geo_credit.add_theme_color_override("font_color", Color("#dbe6e2"))
    geo_credit.add_theme_font_size_override("font_size", 13)
    geo_credit.mouse_filter = Control.MOUSE_FILTER_IGNORE
    add_child(geo_credit)
    get_parent().get_node("Company").companies_updated.connect(_companies_updated)
    get_viewport().size_changed.connect(_layout)
    _layout()
    hide()

func _surface() -> StyleBoxFlat:
    var style := StyleBoxFlat.new()
    style.bg_color = Color("#142634")
    style.border_color = Color("#2d5559")
    style.border_width_bottom = 2
    style.content_margin_left = 14
    style.content_margin_right = 14
    style.content_margin_top = 5
    style.content_margin_bottom = 5
    return style

func _layout() -> void:
    var size := get_viewport().get_visible_rect().size
    frame.position = Vector2(10, 8)
    frame.custom_minimum_size = Vector2(maxf(400.0, size.x - 20.0), 52)
    district_label.visible = size.x > 780
    if geo_credit != null:
        geo_credit.position = Vector2(16, maxf(55.0, size.y - 100.0))

func _companies_updated(companies: Array) -> void:
    if companies.is_empty():
        company_label.text = "Создайте компанию"
    else:
        company_label.text = str(companies[0].get("name", "Компания"))

func update_geography_credit(location_id: String) -> void:
    if geo_credit == null:
        return
    var place := "Михайловка" if location_id == "mikhailovka" else "Уфа"
    geo_credit.text = "© OpenStreetMap contributors · ODbL 1.0 · " + place + " · фрагмент, не вся карта"
