extends SceneTree
const Town = preload("res://scripts/generated_town.gd")
var errors := 0
func check(ok: bool, why: String) -> void:
    if not ok:
        errors += 1
        printerr("FAIL: " + why)
func _initialize() -> void:
    call_deferred("_run")
func _run() -> void:
    var scene: Node2D = load("res://scenes/world.tscn").instantiate()
    root.add_child(scene)
    await process_frame
    check(not scene.geo_background.layer.visible, "legacy OSM layer hidden")
    check(Town.FOOTPRINTS.has(Vector2i(1, 1)), "one-cell house")
    check(Town.FOOTPRINTS.has(Vector2i(3, 3)), "multi-cell house")
    check(Town.road_at(0, 3, Vector2i.ZERO), "one-cell road strip")
    check(not Town.road_at(3, 3, Vector2i.ZERO), "non-road block")
    var plots: Array[Dictionary] = [{"cell_x": 10, "cell_y": 10, "width_cells": 2, "height_cells": 2}]
    check(Town.overlaps_plot(11, 11, 1, 1, plots), "existing parcel blocks scenery")
    check(not Town.overlaps_plot(14, 14, 1, 1, plots), "free cell")
    check(scene.has_method("refresh_parcels"), "server parcels remain")
    scene.queue_free()
    if errors == 0:
        print("BASHECO_GENERATED_TOWN_OK old_osm_hidden=1 road_cell=1 footprints=5 server_plots_preserved=1")
    quit(errors)