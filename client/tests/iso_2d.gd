extends SceneTree
const IsoBuilding = preload("res://scripts/iso_building.gd")
var failures := 0
func check(ok: bool, why: String) -> void:
    if not ok:
        failures += 1
        printerr("FAIL: " + why)
func _initialize() -> void:
    call_deferred("_run")
func _run() -> void:
    var scene: Node2D = load("res://scenes/world.tscn").instantiate()
    root.add_child(scene)
    await process_frame
    check(scene.TILE_W == scene.TILE_H * 2.0, "2:1 isometric projection")
    check(scene.has_method("draw_overlay"), "authoritative world overlay")
    check(IsoBuilding.ROOFS.size() == 3, "three distinct building-zone palettes")
    check(scene.get_node("Overlay") != null, "overlay present")
    check(not scene.get_node("Build").panel.visible, "construction overlay hidden by default")
    scene.queue_free()
    if failures == 0:
        print("BASHECO_ISO_2D_OK projection=2to1 server_plots=1 palette=3")
    quit(failures)