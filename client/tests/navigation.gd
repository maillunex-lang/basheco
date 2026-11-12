extends SceneTree
## Headless regression for the complete administrative navigation catalog and camera.
var failures := 0

func check(condition: bool, message: String) -> void:
    if not condition:
        failures += 1
        printerr("NAV FAIL: " + message)

func _initialize() -> void:
    call_deferred("_run")

func _run() -> void:
    var world: Node2D = load("res://scenes/world.tscn").instantiate()
    root.add_child(world)
    await process_frame
    var menu = world.get_node("Geography")
    var districts: Array = menu.catalog.get("districts", [])
    check(districts.size() == 63, "63 official municipalities")
    var count := 0
    var confirmed := 0
    var unsafe := 0
    var mikh: Dictionary = {}
    var ufimsky: Dictionary = {}
    var far_away: Dictionary = {}
    var duplicate_mikh := 0
    var ids: Dictionary = {}
    for district in districts:
        for location in district.get("locations", []):
            count += 1
            var id := str(location["id"])
            check(not ids.has(id), "unique " + id)
            ids[id] = true
            if location["name"] == "Михайловка":
                duplicate_mikh += 1
            var cell: Variant = location.get("cell")
            if cell == null:
                unsafe += 1
            else:
                confirmed += 1
            if id == "S80652440101":
                mikh = location
                ufimsky = district
            if id == "S80745000001":
                far_away = location
    check(count == 4561, "4561 complete official settlements")
    check(confirmed == 4538 and unsafe == 23, "only 4538 confirmed coordinates can be followed")
    check(duplicate_mikh > 2, "same-name villages are distinct")
    check(not mikh.is_empty() and not far_away.is_empty(), "known settlements located")
    if mikh.is_empty() or far_away.is_empty():
        quit(1)
        return

    menu.open_map()
    menu.search_field.text = "Михайловка"
    var search_results: Array[Dictionary] = menu._results()
    var named := 0
    for result in search_results:
        if result["kind"] == "settlement" and result["data"]["name"] == "Михайловка":
            named += 1
    check(named == duplicate_mikh, "full-republic search finds all namesakes")
    menu._select_district(ufimsky)
    menu._enter_location(mikh)
    var cell: Array = mikh["cell"]
    check(world.camera_center_cell() == Vector2i(int(cell[0]), int(cell[1])), "camera uses official Mikhailovka cell")
    check(world.location_title() == "МИХАЙЛОВКА", "title shows the chosen settlement")
    check(not menu.visible, "menu closes on successful jump")

    menu.open_map()
    menu._enter_location(far_away)
    var far_cell: Array = far_away["cell"]
    var expected := Vector2i(int(far_cell[0]), int(far_cell[1]))
    check(world.camera_center_cell() == expected, "camera reaches distant Sterlitamak, not atlas clamp")
    check(world.location_title() == "СТЕРЛИТАМАК", "distant settlement is named")
    check(world.geo_background.nav_bounds[1] <= expected.y and world.geo_background.nav_bounds[3] >= expected.y, "bounds include Sterlitamak")
    world._focus_on_district()
    check(world.camera_center_cell() == expected, "focus control returns to chosen settlement")

    menu._enter_location({"id": "not-real", "name": "Нет координат", "cell": null})
    check(world.camera_center_cell() == expected, "unconfirmed coordinates cannot move camera")
    menu.open_map()
    menu.search_field.text = "несуществующаянп987"
    check(menu._results().size() == 0, "search returns no invented settlements")

    if failures == 0:
        print("BASHECO_NAVIGATION_OK municipalities=%d settlements=%d confirmed=%d unsafe=%d namesakes=%d" % [districts.size(), count, confirmed, unsafe, duplicate_mikh])
    quit(0 if failures == 0 else 1)