extends CanvasLayer
## Navigation from the versioned OKTMO registry; no per-city scenes or invented locations.
const CATALOG := "res://data/admin_navigation.json"
const PAGE_SIZE := 60
var panel: PanelContainer
var title_label: Label
var list_box: VBoxContainer
var back_button: Button
var search_field: LineEdit
var status_label: Label
var catalog: Dictionary = {}
var current_district: Dictionary = {}
var level := 0
var page := 0

func _ready() -> void:
    var file := FileAccess.open(CATALOG, FileAccess.READ)
    if file != null:
        var parsed: Variant = JSON.parse_string(file.get_as_text())
        if typeof(parsed) == TYPE_DICTIONARY and parsed.get("schema", "") == "basheco.navigation/1":
            catalog = parsed
    panel = PanelContainer.new()
    panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    panel.offset_left = 16
    panel.offset_top = 64
    panel.offset_right = -16
    panel.offset_bottom = -72
    panel.add_theme_stylebox_override("panel", _style())
    add_child(panel)
    var content := VBoxContainer.new()
    content.add_theme_constant_override("separation", 9)
    panel.add_child(content)
    var header := HBoxContainer.new()
    content.add_child(header)
    back_button = Button.new()
    back_button.text = "← Назад"
    back_button.pressed.connect(_back)
    header.add_child(back_button)
    title_label = Label.new()
    title_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    title_label.add_theme_font_size_override("font_size", 19)
    title_label.clip_text = true
    header.add_child(title_label)
    var close_button := Button.new()
    close_button.text = "✕"
    close_button.pressed.connect(hide)
    header.add_child(close_button)
    search_field = LineEdit.new()
    search_field.placeholder_text = "Поиск района или населённого пункта"
    search_field.clear_button_enabled = true
    search_field.text_changed.connect(_on_search)
    content.add_child(search_field)
    var scroll := ScrollContainer.new()
    scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    content.add_child(scroll)
    list_box = VBoxContainer.new()
    list_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    list_box.add_theme_constant_override("separation", 5)
    scroll.add_child(list_box)
    status_label = Label.new()
    status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    content.add_child(status_label)
    hide()

func _style() -> StyleBoxFlat:
    var style := StyleBoxFlat.new()
    style.bg_color = Color("#142634")
    style.set_corner_radius_all(12)
    style.content_margin_left = 14
    style.content_margin_right = 14
    style.content_margin_top = 12
    style.content_margin_bottom = 12
    return style

func open_map() -> void:
    level = 0
    page = 0
    search_field.text = ""
    _render()
    show()

func _on_search(_value: String) -> void:
    page = 0
    _render()

func _matches(haystack: String, query: String) -> bool:
    return haystack.to_lower().contains(query)

func _results() -> Array[Dictionary]:
    var result: Array[Dictionary] = []
    var query := search_field.text.strip_edges().to_lower()
    if catalog.is_empty():
        return result
    if level == 0 and query.is_empty():
        return result
    if level == 1 or (level == 0 and not query.is_empty()):
        for district in catalog.get("districts", []):
            if query.is_empty() or _matches(str(district.get("name", "")), query):
                result.append({"kind": "district", "data": district})
            if not query.is_empty():
                for settlement in district.get("locations", []):
                    var label := str(settlement.get("name", "")) + " " + str(settlement.get("unit", ""))
                    if _matches(label, query):
                        result.append({"kind": "settlement", "data": settlement, "district": district})
    else:
        for settlement in current_district.get("locations", []):
            var label := str(settlement.get("name", "")) + " " + str(settlement.get("unit", ""))
            if query.is_empty() or _matches(label, query):
                result.append({"kind": "settlement", "data": settlement, "district": current_district})
    return result

func _render() -> void:
    for child in list_box.get_children():
        list_box.remove_child(child)
        child.queue_free()
    back_button.text = "← Закрыть" if level == 0 else "← Назад"
    if catalog.is_empty():
        title_label.text = "Карта Башкортостана"
        status_label.text = "Справочник не найден. Сначала сформируйте admin_navigation.json."
        return
    if level == 0 and search_field.text.strip_edges().is_empty():
        title_label.text = "Республика Башкортостан"
        _entry("Районы и городские округа", "63 территории", func(): _open_districts(), true)
        status_label.text = "Выберите территорию или найдите населённый пункт по названию."
        return
    title_label.text = "Поиск по республике" if level == 0 else ("Районы и округа" if level == 1 else str(current_district.get("name", "")))
    var items := _results()
    var start := page * PAGE_SIZE
    for i in range(start, mini(start + PAGE_SIZE, items.size())):
        var result: Dictionary = items[i]
        if result["kind"] == "district":
            var district: Dictionary = result["data"]
            _entry(str(district["name"]), str(district.get("locations", []).size()) + " населённых пунктов", func(): _select_district(district), true)
        else:
            var location: Dictionary = result["data"]
            var district: Dictionary = result["district"]
            var cell: Variant = location.get("cell")
            var available := typeof(cell) == TYPE_ARRAY and cell.size() == 2
            var caption := str(location.get("type", "")) + " · " + str(district["name"])
            if not available:
                caption += " · координаты не подтверждены"
            _entry(str(location["name"]), caption, func(): _enter_location(location), available)
    if start + PAGE_SIZE < items.size():
        _entry("Показать ещё", str(items.size() - start - PAGE_SIZE) + " записей", func(): page += 1; _render(), true)
    status_label.text = "Найдено: %d. Показано: %d." % [items.size(), mini(start + PAGE_SIZE, items.size())]

func _entry(name: String, subtitle: String, action: Callable, enabled: bool) -> void:
    var button := Button.new()
    button.text = name + "\n" + subtitle
    button.alignment = HORIZONTAL_ALIGNMENT_LEFT
    button.custom_minimum_size.y = 55
    button.disabled = not enabled
    button.pressed.connect(action)
    list_box.add_child(button)

func _open_districts() -> void:
    level = 1
    page = 0
    _render()

func _select_district(item: Dictionary) -> void:
    current_district = item
    level = 2
    page = 0
    search_field.text = ""
    _render()

func _enter_location(item: Dictionary) -> void:
    var cell: Variant = item.get("cell")
    if typeof(cell) != TYPE_ARRAY or cell.size() != 2:
        return
    var parent := get_parent()
    if parent.has_method("open_world_cell"):
        parent.open_world_cell(Vector2i(int(cell[0]), int(cell[1])), str(item.get("name", ""))):
            hide()

func _back() -> void:
    if level == 0:
        hide()
    else:
        level -= 1
        page = 0
        search_field.text = ""
        _render()
