extends CanvasLayer
## Lightweight geographic navigation; no world geometry is loaded here.
const CATALOG := "res://data/regions_bashkortostan.json"
var panel: PanelContainer
var title_label: Label
var list_box: VBoxContainer
var back_button: Button
var catalog: Dictionary = {}
var current_district: Dictionary = {}
var level := 0

func _ready() -> void:
    var file := FileAccess.open(CATALOG, FileAccess.READ)
    if file != null:
        var parsed: Variant = JSON.parse_string(file.get_as_text())
        if typeof(parsed) == TYPE_DICTIONARY:
            catalog = parsed
    panel = PanelContainer.new()
    panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    panel.offset_left = 24
    panel.offset_top = 70
    panel.offset_right = -24
    panel.offset_bottom = -90
    panel.add_theme_stylebox_override("panel", _style())
    add_child(panel)
    var content := VBoxContainer.new()
    content.add_theme_constant_override("separation", 12)
    panel.add_child(content)
    var header := HBoxContainer.new()
    content.add_child(header)
    back_button = Button.new()
    back_button.text = "← Назад"
    back_button.pressed.connect(_back)
    header.add_child(back_button)
    title_label = Label.new()
    title_label.add_theme_font_size_override("font_size", 23)
    header.add_child(title_label)
    var scroll := ScrollContainer.new()
    scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    content.add_child(scroll)
    list_box = VBoxContainer.new()
    list_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    list_box.add_theme_constant_override("separation", 9)
    scroll.add_child(list_box)
    var note := Label.new()
    note.text = "География: демонстрационный каталог. Полный список и границы будут добавлены после проверки источников."
    note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    content.add_child(note)
    hide()

func _style() -> StyleBoxFlat:
    var style := StyleBoxFlat.new()
    style.bg_color = Color("#142634")
    style.set_corner_radius_all(12)
    style.content_margin_left = 20
    style.content_margin_right = 20
    style.content_margin_top = 16
    style.content_margin_bottom = 16
    return style

func open_map() -> void:
    level = 0
    _render()
    show()

func _render() -> void:
    for child in list_box.get_children():
        child.queue_free()
    back_button.visible = true
    if level == 0:
        title_label.text = "Республика Башкортостан"
        back_button.text = "← В город"
        _entry("Районы и городские округа", "Открыть список территорий", func(): level = 1; _render(), true)
    elif level == 1:
        title_label.text = "Районы и городские округа"
        back_button.text = "← Республика"
        for district in catalog.get("districts", []):
            var item: Dictionary = district
            _entry(str(item.get("name", "")), "Выбрать территорию", func(): _select_district(item), true)
    else:
        title_label.text = str(current_district.get("name", "Локации"))
        back_button.text = "← Районы"
        for location in current_district.get("locations", []):
            var item: Dictionary = location
            var playable := bool(item.get("playable", false))
            var caption := "Играть в локации" if playable else "Пока недоступно в Alpha"
            _entry(str(item.get("name", "")), caption, func(): _enter_location(item), playable)

func _entry(name: String, subtitle: String, action: Callable, enabled: bool) -> void:
    var button := Button.new()
    button.text = name + "    ·    " + subtitle
    button.alignment = HORIZONTAL_ALIGNMENT_LEFT
    button.custom_minimum_size.y = 58
    button.disabled = not enabled
    button.pressed.connect(action)
    list_box.add_child(button)

func _select_district(item: Dictionary) -> void:
    current_district = item
    level = 2
    _render()

func _enter_location(item: Dictionary) -> void:
    if not bool(item.get("playable", false)):
        return
    if str(item.get("sector_id", "")) != "ufa-prototype-01":
        return
    hide()
    get_parent()._focus_on_district()

func _back() -> void:
    if level == 0:
        hide()
    else:
        level -= 1
        _render()
