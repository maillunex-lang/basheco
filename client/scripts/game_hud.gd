extends CanvasLayer
## Mobile-first top status and map controls. Never invents balances.
var world: Node2D
var company_label: Label
var district_label: Label
var frame: PanelContainer
var row: HBoxContainer
var minus_button: Button
var center_button: Button
var plus_button: Button
var location_button: Button
var balance_label: Label
var geo_credit: Label
var performance_label: Label
var performance_elapsed := 0.0
const CREDIT := "© OpenStreetMap contributors · ODbL · Рельеф: SRTM / OpenTopoData · "

func _ready() -> void:
    world = get_parent()
    frame = PanelContainer.new()
    frame.add_theme_stylebox_override("panel", _surface())
    add_child(frame)
    row = HBoxContainer.new()
    row.add_theme_constant_override("separation", 12)
    frame.add_child(row)
    district_label = Label.new()
    district_label.text = "РЕСПУБЛИКА БАШКОРТОСТАН"
    district_label.add_theme_color_override("font_color", Color("#e8f2ef"))
    row.add_child(district_label)
    var divider := VSeparator.new()
    row.add_child(divider)
    company_label = Label.new()
    company_label.text = "Компания не выбрана"
    company_label.add_theme_color_override("font_color", Color("#e8f2ef"))
    row.add_child(company_label)
    balance_label = Label.new()
    balance_label.text = "Баланс: откройте компанию"
    balance_label.add_theme_color_override("font_color", Color("#a6d4ca"))
    balance_label.tooltip_text = "Баланс появится после подключения серверного кошелька"
    row.add_child(balance_label)
    var spacer := Control.new()
    spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    row.add_child(spacer)
    location_button = Button.new()
    location_button.text = "⌕ Населённый пункт"
    location_button.tooltip_text = "Выбрать район или населённый пункт"
    location_button.custom_minimum_size.y = 42
    location_button.pressed.connect(func(): world.get_node("Geography").open_map())
    row.add_child(location_button)
    minus_button = Button.new()
    var minus := minus_button
    minus.text = "−"
    minus.custom_minimum_size = Vector2(44, 42)
    minus.pressed.connect(func(): world.zoom_at(get_viewport().get_visible_rect().size * 0.5, 1.0 / 1.2))
    row.add_child(minus)
    center_button = Button.new()
    var center := center_button
    center.text = "⌖ Район"
    center.custom_minimum_size = Vector2(92, 42)
    center.pressed.connect(world._focus_on_district)
    row.add_child(center)
    plus_button = Button.new()
    var plus := plus_button
    plus.text = "+"
    plus.custom_minimum_size = Vector2(44, 42)
    plus.pressed.connect(func(): world.zoom_at(get_viewport().get_visible_rect().size * 0.5, 1.2))
    row.add_child(plus)
    geo_credit = Label.new()
    geo_credit.text = CREDIT + "покрытие частичное"
    geo_credit.add_theme_color_override("font_color", Color("#dbe6e2"))
    geo_credit.add_theme_font_size_override("font_size", 13)
    geo_credit.mouse_filter = Control.MOUSE_FILTER_IGNORE
    add_child(geo_credit)
    performance_label = Label.new()
    performance_label.add_theme_font_size_override("font_size", 12)
    performance_label.add_theme_color_override("font_color", Color("#a9d6d0"))
    performance_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
    performance_label.visible = OS.has_feature("debug")
    add_child(performance_label)
    get_parent().get_node("Company").companies_updated.connect(_companies_updated)
    get_viewport().size_changed.connect(_layout)
    _layout()
    hide()

func _process(delta: float) -> void:
    if not performance_label.visible or not world.world_visible:
        return
    performance_elapsed += delta
    if performance_elapsed < 1.0:
        return
    performance_elapsed = 0.0
    var fps := Performance.get_monitor(Performance.TIME_FPS)
    var memory_mb := Performance.get_monitor(Performance.MEMORY_STATIC) / 1048576.0
    var active: int = world.geo_background.active_chunk_ids.size()
    var cell: Vector2i = world.camera_center_cell()
    var lonlat: PackedFloat64Array = world.camera_center_lonlat()
    performance_label.text = "FPS: %d  |  Godot RAM: %.1f MB  |  чанков: %d  |  масштаб: %.3f×  |  клетка %d, %d  |  %.5f° в.д. %.5f° с.ш." % [int(fps), memory_mb, active, world.zoom_level, cell.x, cell.y, lonlat[0], lonlat[1]]

func _surface() -> StyleBoxFlat:
    var style := StyleBoxFlat.new()
    style.bg_color = Color("#142634")
    style.border_color = Color("#2d5559")
    style.border_width_bottom = 2
    style.set_corner_radius_all(12)
    style.content_margin_left = 14
    style.content_margin_right = 14
    style.content_margin_top = 5
    style.content_margin_bottom = 5
    return style

func _layout() -> void:
    var size := get_viewport().get_visible_rect().size
    frame.position = Vector2(10, 8)
    frame.custom_minimum_size = Vector2(maxf(280.0, size.x - 20.0), 52)
    district_label.visible = size.x >= 1080
    balance_label.visible = size.x >= 1100
    company_label.visible = size.x >= 700
    location_button.text = "⌕ Город" if size.x < 900 else "⌕ Населённый пункт"
    location_button.custom_minimum_size.x = 72 if size.x < 900 else 160
    center_button.text = "⌖" if size.x < 900 else "⌖ Район"
    center_button.custom_minimum_size.x = 44 if size.x < 900 else 92
    row.add_theme_constant_override("separation", 5 if size.x < 900 else 12)
    if geo_credit != null:
        geo_credit.position = Vector2(16, maxf(55.0, size.y - 100.0))
    if performance_label != null:
        performance_label.position = Vector2(16, maxf(76.0, size.y - 78.0))

func _companies_updated(companies: Array) -> void:
    if companies.is_empty():
        company_label.text = "Создайте компанию"
        balance_label.text = "Баланс: откройте компанию"
    else:
        company_label.text = str(companies[0].get("name", "Компания"))
        # The company-list response is not a verified balance endpoint.
        # Never display a guessed sum or the starter grant as current funds.
        balance_label.text = "Баланс: нет данных"

func update_geography_credit(location_id: String) -> void:
    if geo_credit == null:
        return
    var settlements: Dictionary = world.geo_background.settlements
    var place := str(settlements[location_id]["name"]) if settlements.has(location_id) else "Республика Башкортостан"
    geo_credit.text = CREDIT + place + " · покрытие частичное"