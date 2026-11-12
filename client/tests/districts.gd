extends SceneTree
const Town = preload("res://scripts/generated_town.gd")
var failures := 0
func check(ok: bool, label: String) -> void:
    if not ok:
        failures += 1
        printerr("FAIL " + label)
func _initialize() -> void:
    call_deferred("_run")
func _run() -> void:
    var anchor := Vector2i(100, 200)
    check(Town.DISTRICT_NAMES.size() == 5, "five districts")
    check(Town.district_at(128, 228, anchor) == 0, "center")
    check(Town.district_at(105, 205, anchor) == 3, "park")
    check(Town.district_at(145, 245, anchor) == 2, "industrial")
    check(Town.land_value_band(128, 228, anchor) > Town.land_value_band(101, 201, anchor), "center value band")
    check(Town.road_at(108, 207, anchor), "road")
    check(not Town.road_at(107, 207, anchor), "buildable land")
    var world: Node2D = load("res://scenes/world.tscn").instantiate()
    root.add_child(world)
    await process_frame
    check(world.has_method("_input"), "touch input")
    check(world.has_method("draw_overlay"), "minimap overlay")
    world.queue_free()
    if failures == 0:
        print("BASHECO_DISTRICTS_OK districts=5 roads=1 land_bands=3 minimap=1")
    quit(failures)