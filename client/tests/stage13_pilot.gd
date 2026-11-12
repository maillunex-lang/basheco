extends SceneTree
var failures := 0
func check(value: bool, message: String) -> void:
    if not value:
        failures += 1
        printerr("PILOT FAIL: " + message)
func _initialize() -> void:
    call_deferred("_run")
func _run() -> void:
    var world = load("res://scenes/world.tscn").instantiate()
    root.add_child(world)
    await process_frame
    var menu = world.get_node("Geography")
    check(menu.catalog["districts"].size() == 63, "official registry remains complete")
    check(menu.available_locations.size() == 1, "only one generated playable location")
    check(menu.available_locations.has("S80652440101"), "Mikhailovka is published")
    var results: Array[Dictionary] = []
    menu.open_map()
    menu._open_districts()
    results = menu._results()
    check(results.size() == 1, "empty municipalities hidden")
    var district: Dictionary = results[0]["data"]
    menu._select_district(district)
    results = menu._results()
    check(results.size() == 1 and results[0]["data"]["id"] == "S80652440101", "only built settlement visible")
    menu.search_field.text = "Стерлитамак"
    check(menu._results().is_empty(), "unbuilt settlements hidden from search")
    menu.search_field.text = ""
    menu._enter_location(results[0]["data"])
    check(not menu.visible, "enter available settlement")
    check(world.generated_objects.size() == 77, "62 roads and 15 buildings loaded")
    var houses := 0
    for obj in world.generated_objects:
        if obj["kind"] == "house":
            houses += 1
    check(houses == 15, "pilot has houses")
    var before = world.camera_center_cell()
    menu._enter_location({"id":"S80745000001","name":"Стерлитамак","cell":[72000,-1012000]})
    check(world.camera_center_cell() == before, "direct navigation cannot bypass availability")
    if failures == 0:
        print("BASHECO_STAGE13_PILOT_OK available=1 houses=15 roads=62")
    quit(0 if failures == 0 else 1)