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
    var p: Dictionary = world.plots[0]
    var center: Vector2 = world.project_point(
        float(p["tile_x"]) + float(p["width_tiles"]) / 2.0,
        float(p["tile_y"]) + float(p["height_tiles"]) / 2.0)
    world._select_at(center)
    assert(world.selected_plot == 0)
    var down := InputEventScreenTouch.new()
    down.index = 0
    down.pressed = true
    down.position = Vector2(200, 300)
    world._unhandled_input(down)
    var drag := InputEventScreenDrag.new()
    drag.index = 0
    drag.position = Vector2(220, 320)
    world._unhandled_input(drag)
    assert(world.camera_offset.distance_to(Vector2(670, 110)) < 0.01)
    var up := InputEventScreenTouch.new()
    up.index = 0
    up.position = drag.position
    up.pressed = false
    world._unhandled_input(up)
    print("BASHECO_GODOT_SMOKE_OK plots=6 osm=",world.get_node("OSM").features.size())
    quit(0)
