extends SceneTree
## Headless scene smoke: map fixtures, OSM data, selection, touch gestures.
func _initialize() -> void:
    call_deferred("_run")

func _run() -> void:
    var scene: PackedScene = load("res://scenes/world.tscn")
    var world: Node2D = scene.instantiate()
    root.add_child(world)
    await process_frame
    assert(world.plots.size() == 6)
    assert(world.world_width == 200 and world.world_height == 200)
    var visible: Array[int] = world._visible_tile_bounds()
    assert(visible[2] - visible[0] < 200)
    assert(visible[3] - visible[1] < 200)
    var osm = world.get_node("OSM")
    assert(osm.features.size() >= 1)
    assert(osm.chunk_paths.size() == 16)
    assert(osm.loaded_chunks.size() >= 1 and osm.loaded_chunks.size() <= 16)
    osm._load_chunk(Vector2i(1, 1))
    assert(osm.loaded_chunks.has(Vector2i(1, 1)))
    assert(osm.attribution.text.contains("OpenStreetMap"))
    assert(world.get_node("API") != null)
    assert(world.get_node("Login") != null)
    var build_panel = world.get_node("Build")
    assert(build_panel.company_ids.is_empty())
    build_panel._set_companies([{"id":"test-company-1", "name":"Тестовая компания"}])
    assert(build_panel.company_ids.size() == 1)
    assert(build_panel.company.get_item_text(0) == "Тестовая компания")
    assert(build_panel._selected_company_id() == "test-company-1")
    var market = world.get_node("Market")
    market._set_companies([{"id":"test-company-1", "name":"Тестовая компания"}, {"id":"test-company-2", "name":"Другая компания"}])
    assert(market._selected_company_id() == "test-company-1")
    market.company_field.select(1)
    market._set_companies([{"id":"test-company-2", "name":"Другая компания"}, {"id":"test-company-1", "name":"Тестовая компания"}])
    assert(market._selected_company_id() == "test-company-2")
    assert(world.get_node("Login").display_name != null)
    var hud = world.get_node("HUD")
    assert(hud.company_label.text == "Компания не выбрана")
    hud._companies_updated([{"name":"Тестовая компания"}])
    assert(hud.company_label.text == "Тестовая компания")
    var anchor := Vector2(360, 220)
    var local_before: Vector2 = (anchor - world.camera_offset) / world.zoom_level
    world.zoom_at(anchor, 1.25)
    var local_after: Vector2 = (anchor - world.camera_offset) / world.zoom_level
    assert(local_before.distance_to(local_after) < 0.01)
    world._focus_on_district()
    assert(world.zoom_level >= world.MIN_ZOOM and world.zoom_level <= world.MAX_ZOOM)
    var nav = world.get_node("Navigation")
    nav._show_section("Build")
    assert(build_panel.panel.visible)
    assert(not market.panel.visible)
    nav._show_section("")
    assert(not build_panel.panel.visible)
    var geo = world.get_node("Geography")
    assert(geo.visible and geo.level == 0)
    geo._select_district(geo.catalog["districts"][0])
    assert(geo.level == 2)
    geo._enter_location(geo.catalog["districts"][0]["locations"][0])
    assert(not geo.visible)
    var p: Dictionary = world.plots[0]
    var center: Vector2 = world.project_point(
        float(p["tile_x"]) + float(p["width_tiles"]) / 2.0,
        float(p["tile_y"]) + float(p["height_tiles"]) / 2.0)
    world._select_at(center)
    assert(world.selected_plot == 0)
    world.world_visible = true
    world.get_node("Login").panel.visible = false
    var before_drag: Vector2 = world.camera_offset
    var down := InputEventScreenTouch.new()
    down.index = 0
    down.pressed = true
    down.position = Vector2(200, 300)
    world._unhandled_input(down)
    var drag := InputEventScreenDrag.new()
    drag.index = 0
    drag.position = Vector2(220, 320)
    world._unhandled_input(drag)
    assert(world.camera_offset.distance_to(before_drag + Vector2(20, 20)) < 0.01)
    var up := InputEventScreenTouch.new()
    up.index = 0
    up.position = drag.position
    up.pressed = false
    world._unhandled_input(up)
    print("BASHECO_GODOT_SMOKE_OK plots=6 osm=",world.get_node("OSM").features.size())
    quit(0)
