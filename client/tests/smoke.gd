extends SceneTree
## Headless scene test of the single world: grid, streaming, camera, plots, UI.
const WorldGrid = preload("res://scripts/world_grid.gd")
var failures := 0

func check(condition: bool, message: String) -> void:
    if not condition:
        failures += 1
        printerr("FAIL: " + message)

func _initialize() -> void:
    call_deferred("_run")

func drain(world: Node2D) -> void:
    for _i in range(64):
        if not world.geo_background.process_pending_chunks(world):
            break

func _run() -> void:
    var scene: PackedScene = load("res://scenes/world.tscn")
    var world: Node2D = scene.instantiate()
    root.add_child(world)
    await process_frame
    var geo = world.geo_background
    var ufa: Vector2i = geo.settlements["ufa"]["focus_cell"]
    var mikhailovka: Vector2i = geo.settlements["mikhailovka"]["focus_cell"]

    # --- one atlas, one grid, real positions -----------------------------------
    check(geo.ready, "atlas loaded")
    check(not world.has_node("OSM"), "legacy per-city overlay removed")
    check(geo.manifest["crs"] == "EPSG:32640" and geo.manifest["grid_version"] == WorldGrid.GRID_VERSION, "atlas grid")
    check(geo.manifest["license"] == "ODbL 1.0", "licence kept")
    check(geo.settlements.size() == 2, "both settlements in the same atlas")
    check(ufa == Vector2i(72302, -1011032), "ufa world cell")
    check(mikhailovka == Vector2i(71469, -1012286), "mikhailovka world cell")
    var apart := Vector2(ufa - mikhailovka).length() * 6.0
    check(absf(apart - 9032.3) < 8.0, "real distance between settlements: %f" % apart)
    check(geo.settlements["ufa"]["boundary_source_url"].contains("1549169"), "ufa boundary provenance")
    check(geo.settlements["ufa"]["rings"].size() >= 1 and geo.settlements["mikhailovka"]["rings"].size() >= 1, "boundaries")
    check(geo.terrain_range["ufa"].x >= 170.0 and geo.terrain_range["ufa"].y <= 185.0, "ufa elevation range")
    check(geo.terrain_range["mikhailovka"].y - geo.terrain_range["mikhailovka"].x > 40.0, "mikhailovka relief")
    check(geo.BUILDING_SPRITES.size() == 3 and geo.TREE_SPRITE.get_width() > 0, "sprites")
    check(geo.chunk_index.size() == geo.manifest["chunks"].size() and geo.chunk_index.size() > 40, "chunk index")
    check(world.plots.is_empty(), "no invented plots")

    # --- camera starts on Ufa, chunks stream in --------------------------------
    check(world.camera_center_cell() == ufa, "camera on ufa: %s" % world.camera_center_cell())
    check(world.current_location_id == "ufa", "location label from real boundary")
    check(world.lod() == 0, "detail lod at start")
    drain(world)
    check(geo.loaded.size() > 0 and geo.loaded.size() <= geo.MAX_ACTIVE_CHUNKS, "ufa chunks loaded: %d" % geo.loaded.size())
    check(geo.loaded.has(Vector2i(1129, -15798)), "ufa focus chunk loaded")
    var ufa_features: int = geo.loaded_feature_count()
    check(ufa_features > 10, "ufa features")
    var lonlat: PackedFloat64Array = world.camera_center_lonlat()
    check(absf(lonlat[0] - 55.972) < 0.0002 and absf(lonlat[1] - 54.7386) < 0.0002, "camera lon/lat %f %f" % [lonlat[0], lonlat[1]])
    var visible: Array[int] = world.visible_cell_bounds()
    check(visible[2] - visible[0] < 200 and visible[3] - visible[1] < 200, "only on-screen cells considered")
    check(visible[0] < ufa.x and ufa.x < visible[2] and visible[1] < ufa.y and ufa.y < visible[3], "bounds are global cells")

    # --- projection round trip stays exact at million-sized coordinates ---------
    for offset in [Vector2i(0, 0), Vector2i(37, -12), Vector2i(-90, 41)]:
        var cell: Vector2i = ufa + offset
        var on_screen: Vector2 = world.project_cell(cell, Vector2(0.5, 0.5))
        check(world.screen_to_cell(on_screen) == cell, "screen<->cell round trip %s" % cell)
    var step: Vector2 = world.project_cell(ufa + Vector2i(1, 0)) - world.project_cell(ufa)
    check(step.distance_to(Vector2(32, 16) * world.zoom_level) < 0.001, "cell spacing has no float drift")

    # --- neighbouring chunks meet without a visible gap --------------------------
    var seam_checked := 0
    var seam_worst := 0.0
    var ends: Dictionary = {}
    for key in geo.loaded:
        var node: Node2D = geo.loaded[key]
        for feature in node.features:
            if feature["geom"] != "line":
                continue
            var parts: PackedStringArray = str(feature["uid"]).split("#")
            var pts: PackedVector2Array = feature["pts"]
            ends[feature["uid"]] = [node.transform * pts[0], node.transform * pts[pts.size() - 1], parts[0], int(parts[1])]
    for uid in ends:
        var next_uid: String = "%s#%d" % [ends[uid][2], ends[uid][3] + 1]
        if ends.has(next_uid):
            seam_worst = maxf(seam_worst, (ends[uid][1] as Vector2).distance_to(ends[next_uid][0]))
            seam_checked += 1
    check(seam_checked > 0, "roads cross chunk borders in the test area")
    check(seam_worst < 0.05, "seam between chunks: %f px" % seam_worst)
    check(geo.stats["duplicates"] == 0 and geo.stats["rejected"] == 0, "no duplicated or broken objects")

    # --- selecting a settlement moves the camera inside the same world ----------
    var atlas_before = geo.manifest
    var layer_before: Node2D = geo.layer
    var geo_menu = world.get_node("Geography")
    check(geo_menu.level == 0, "geography menu")
    geo_menu.open_map()
    check(geo_menu.catalog["districts"].size() == 63, "full municipality catalog")
    var ufimsky: Dictionary = {}
    var official_mikh: Dictionary = {}
    for district in geo_menu.catalog["districts"]:
        if district["id"] == "M80652000":
            ufimsky = district
            for location in district["locations"]:
                if location["id"] == "S80652440101":
                    official_mikh = location
    check(not official_mikh.is_empty(), "Mikhailovka stable OKTMO id")
    if not official_mikh.is_empty():
        geo_menu._select_district(ufimsky)
        geo_menu._enter_location(official_mikh)
        check(not geo_menu.visible, "menu closes after choosing")
        var actual: Array = official_mikh["cell"]
        check(world.camera_center_cell() == Vector2i(int(actual[0]), int(actual[1])), "camera flew to official Mikhailovka position")
    # Old atlas smoke cases below use the center of the sourced OSM fragment,
    # which is not the official Wikidata settlement anchor.
    world.open_location("mikhailovka")
    check(world.camera_center_cell() == mikhailovka, "atlas focus remains available")
    check(world.current_location_id == "mikhailovka", "location follows the camera")
    check(is_same(geo.manifest, atlas_before) and geo.layer == layer_before, "no second map was loaded")
    check(world.render_origin == WorldGrid.chunk_origin_cell(WorldGrid.cell_to_chunk(mikhailovka.x, mikhailovka.y)), "render origin follows camera")
    check(not geo.loaded.has(Vector2i(1129, -15798)), "far ufa chunk released")
    drain(world)
    check(geo.loaded.has(Vector2i(1116, -15817)), "mikhailovka focus chunk loaded")
    check(geo.loaded.size() <= geo.MAX_ACTIVE_CHUNKS, "chunk cap")
    check(geo.loaded_feature_count() > ufa_features, "denser village data streamed")
    check(geo.loaded_feature_count() < int(geo.manifest["exported_piece_count"]), "never the whole atlas in memory")
    check(world.get_node("HUD").geo_credit.text.contains("Михайловка"), "credit names the settlement")
    check(world.open_location("ufa") and world.camera_center_cell() == ufa, "back to ufa")
    drain(world)
    check(geo.loaded.has(Vector2i(1129, -15798)), "revisit reloads chunks")
    check(not world.open_location("unknown"), "unknown settlement rejected")
    check(geo.stats["duplicates"] == 0, "revisit creates no duplicates")

    # --- continuous travel between the settlements (no teleport, no jump) -------
    world.open_location("ufa")
    var travelled := 0
    var worst_jump := 0.0
    var max_loaded := 0
    var max_local := 0.0
    while world.camera_center_cell().distance_to(mikhailovka) > 40 and travelled < 4000:
        var before: Vector2i = world.camera_center_cell()
        var probe: Vector2i = before + Vector2i(3, -2)
        var probe_screen: Vector2 = world.project_cell(probe)
        var direction := Vector2(mikhailovka - before).normalized() * 24.0
        var drag_px: Vector2 = -world.iso(direction.x, direction.y) * world.zoom_level
        world.camera_offset += drag_px
        world._camera_changed()
        worst_jump = maxf(worst_jump, (world.project_cell(probe) - (probe_screen + drag_px)).length())
        geo.process_pending_chunks(world)
        max_loaded = maxi(max_loaded, geo.loaded.size())
        max_local = maxf(max_local, Vector2(world.camera_center_cell() - world.render_origin).length())
        travelled += 1
    check(world.camera_center_cell().distance_to(mikhailovka) <= 40, "camera reached mikhailovka by panning")
    check(travelled > 50, "it is a real 9 km trip: %d steps" % travelled)
    check(worst_jump < 0.05, "objects never jump when the origin is rebased: %f px" % worst_jump)
    check(max_loaded <= geo.MAX_ACTIVE_CHUNKS, "chunk cap during travel")
    check(max_local < 600.0, "drawn coordinates stay small: %f" % max_local)
    check(geo.stats["evictions"] > 0, "far chunks are released")

    # --- zoom, level of detail, navigation limits ---------------------------------
    world.open_location("ufa")
    var anchor := Vector2(360, 220)
    var cell_before: Vector2 = world.screen_to_local(anchor) + Vector2(world.render_origin)
    world.zoom_at(anchor, 1.25)
    var cell_after: Vector2 = world.screen_to_local(anchor) + Vector2(world.render_origin)
    check(cell_before.distance_to(cell_after) < 0.01, "zoom keeps the point under the finger")
    world.zoom_at(Vector2(320, 240), 1000.0)
    check(is_equal_approx(world.zoom_level, world.MAX_ZOOM), "max zoom")
    world.zoom_at(Vector2(640, 360), 0.05 / world.zoom_level)
    check(world.lod() == 3, "overview lod")
    check(geo.loaded.is_empty() and geo.pending_chunks.is_empty(), "overview holds no detail chunks")
    var both_visible := Rect2(Vector2.ZERO, world.get_viewport_rect().size)
    world.zoom_at(Vector2(640, 360), 0.012 / world.zoom_level)
    world.center_on_cell((ufa + mikhailovka) / 2)
    check(both_visible.has_point(world.project_cell(ufa)) and both_visible.has_point(world.project_cell(mikhailovka)), "both settlements on one screen")
    world.zoom_at(Vector2(320, 240), 0.000001)
    check(is_equal_approx(world.zoom_level, world.MIN_ZOOM), "min zoom")
    world.camera_offset += Vector2(900000, 900000)
    world._camera_changed()
    var nav: Array[int] = geo.nav_bounds
    var held: Vector2i = world.camera_center_cell()
    check(held.x >= nav[0] - 1 and held.x <= nav[2] + 1 and held.y >= nav[1] - 1 and held.y <= nav[3] + 1, "camera stays inside the navigable region")
    world.open_location("ufa")
    world.zoom_at(Vector2(640, 360), 0.2 / world.zoom_level)
    check(world.lod() == 2, "far lod")
    drain(world)
    check(geo.loaded.size() > 0, "far lod still streams chunks")
    world._focus_on_district()
    check(is_equal_approx(world.zoom_level, world.DEFAULT_ZOOM) and world.camera_center_cell() == ufa, "centre button")

    # --- server plots live in world cells ------------------------------------------
    world._on_sector_loaded({"plots": [
        {"id": "p1", "sector_id": "ufa", "tile_x": 20, "tile_y": 20, "width_tiles": 5, "height_tiles": 5, "zone": "commercial",
            "world_cell_x": float(ufa.x + 4), "world_cell_y": float(ufa.y - 3), "owner_company_id": null, "building_id": null},
        {"id": "p2", "sector_id": "mikhailovka", "tile_x": 150, "tile_y": 180, "width_tiles": 5, "height_tiles": 5, "zone": "industrial",
            "world_cell_x": float(mikhailovka.x), "world_cell_y": float(mikhailovka.y)},
        {"id": "p3", "sector_id": "ufa", "tile_x": 1, "tile_y": 1, "width_tiles": 5, "height_tiles": 5, "zone": "industrial",
            "world_cell_x": null, "world_cell_y": null}
    ], "unplaced_plot_count": 1, "grid": {}})
    check(world.plots.size() == 2, "unplaced plot is not drawn at a guessed position")
    check(world.unplaced_plot_count == 1, "unplaced plots are reported")
    check(world.plots[0]["cell_x"] == ufa.x + 4 and world.plots[0]["cell_y"] == ufa.y - 3, "plot uses world cells, not legacy tiles")
    var plot_center: Vector2 = world.project_cell(Vector2i(ufa.x + 4, ufa.y - 3), Vector2(2.5, 2.5))
    world._select_at(plot_center)
    check(world.selected_plot == 0, "plot selected by world cell")
    world._select_at(world.project_cell(ufa + Vector2i(40, 40)))
    check(world.selected_plot == -1, "empty ground selects nothing")
    var api = world.get_node("API")
    check(WorldGrid.matches(geo.manifest), "client grid equals atlas grid")

    # --- existing interface still works ----------------------------------------------
    check(world.get_node("Login") != null and world.get_node("Login").display_name != null, "login panel")
    var login = world.get_node("Login")
    check(login.heading.text == "BASHECO" and login.demo_button.text.contains("без входа"), "alpha main menu actions")
    check(login.scroll != null and login.scroll.visible, "login card scrolls on compact screens")
    login._login()
    check(not login.busy and login.status_label.text == "Введите почту и пароль", "empty login does not lock buttons")
    check(api != null, "api node")
    var build_panel = world.get_node("Build")
    check(build_panel.company_ids.is_empty(), "build panel starts empty")
    build_panel._set_companies([{"id": "test-company-1", "name": "Тестовая компания"}])
    check(build_panel.company_ids.size() == 1 and build_panel._selected_company_id() == "test-company-1", "build panel company")
    check(build_panel.CATALOG.size() == 3 and build_panel.CATALOG[0]["code"] == "shop", "build catalog matches SQL building types")
    check(build_panel._selection_error() == "Войдите в игру, чтобы строить", "build blocks unauthenticated users")
    check(build_panel.selected_info.text.contains("Цена и размеры здания пока не определены"), "build does not fabricate costs or footprint")
    check(build_panel.selected_info.text.contains("Контур на карте показывает участок"), "preview is labelled as parcel outline")
    check(build_panel.build_button.disabled, "build action disabled without server-authenticated plot")
    var market = world.get_node("Market")
    market._set_companies([{"id": "test-company-1", "name": "Тестовая компания"}, {"id": "test-company-2", "name": "Другая компания"}])
    check(market._selected_company_id() == "test-company-1", "market company")
    market.company_field.select(1)
    market._set_companies([{"id": "test-company-2", "name": "Другая компания"}, {"id": "test-company-1", "name": "Тестовая компания"}])
    check(market._selected_company_id() == "test-company-2", "market keeps selection")
    var hud = world.get_node("HUD")
    check(hud.company_label.text == "Компания не выбрана", "hud company placeholder")
    hud._companies_updated([{"name": "Тестовая компания"}])
    check(hud.company_label.text == "Тестовая компания", "hud company")
    check(hud.balance_label.text == "Баланс: нет данных", "hud does not fabricate funds")
    check(hud.location_button != null and hud.location_button.tooltip_text.contains("населённый пункт"), "hud location picker available")
    check(hud.district_label.text.begins_with("УФА"), "hud shows the settlement under the camera: " + hud.district_label.text)
    var nav_panel = world.get_node("Navigation")
    nav_panel._show_section("Build")
    check(build_panel.panel.visible and not market.panel.visible, "navigation opens build")
    check(nav_panel.active_section == "Build" and nav_panel.buttons["Build"].tooltip_text == "Стройка", "build navigation selected and labelled")
    nav_panel._show_section("")
    check(not build_panel.panel.visible, "navigation closes panels")
    check(nav_panel.active_section == "" and nav_panel.buttons[""].tooltip_text == "Карта", "map navigation selected")
    var chunks = load("res://scripts/city_chunks.gd")
    check(chunks.chunk_for_tile(63, 63) == Vector2i(0, 0) and chunks.chunk_for_tile(64, 64) == Vector2i(1, 1) and chunks.chunk_for_tile(-1, -1) == Vector2i(-1, -1), "plot chunk helper")
    var one_chunk: Array[int] = [0, 0, 64, 64]
    var four_chunks: Array[int] = [63, 63, 65, 65]
    check(chunks.chunks_for_bounds(one_chunk, 0).size() == 1 and chunks.chunks_for_bounds(four_chunks, 0).size() == 4, "chunks for bounds")

    # --- touch: drag and pinch ---------------------------------------------------------
    world.world_visible = true
    world.get_node("Login").panel.visible = false
    var before_drag: Vector2 = world.project_cell(ufa)
    var down := InputEventScreenTouch.new()
    down.index = 0
    down.pressed = true
    down.position = Vector2(200, 300)
    world._unhandled_input(down)
    var drag := InputEventScreenDrag.new()
    drag.index = 0
    drag.position = Vector2(220, 320)
    world._unhandled_input(drag)
    check(world.project_cell(ufa).distance_to(before_drag + Vector2(20, 20)) < 0.01, "one finger drags the map")
    var second := InputEventScreenTouch.new()
    second.index = 1
    second.pressed = true
    second.position = Vector2(420, 320)
    world._unhandled_input(second)
    var zoom_before: float = world.zoom_level
    var spread := InputEventScreenDrag.new()
    spread.index = 1
    spread.position = Vector2(520, 320)
    world._unhandled_input(spread)
    check(world.zoom_level > zoom_before, "two fingers zoom")
    for index in [1, 0]:
        var up := InputEventScreenTouch.new()
        up.index = index
        up.position = Vector2(220, 320)
        up.pressed = false
        world._unhandled_input(up)
    check(world.touches.is_empty(), "touches released")
    await process_frame
    await process_frame
    if failures == 0:
        print("BASHECO_GODOT_SMOKE_OK settlements=%d chunks_in_atlas=%d loads=%d evictions=%d travel_steps=%d seam_px=%.4f jump_px=%.4f" % [
            geo.settlements.size(), geo.chunk_index.size(), geo.stats["loads"], geo.stats["evictions"], travelled, seam_worst, worst_jump])
    quit(1 if failures > 0 else 0)