extends SceneTree
## Rendering contract: cosmetic changes must not replace authoritative parcels.
var failures := 0

func _check(condition: bool, description: String) -> void:
    if not condition:
        failures += 1
        printerr("FAIL: " + description)

func _initialize() -> void:
    call_deferred("_run")

func _run() -> void:
    var scene: Node2D = load("res://scenes/world.tscn").instantiate()
    root.add_child(scene)
    await process_frame
    var hud = scene.get_node("HUD")
    var build = scene.get_node("Build")
    _check(not hud.performance_label.visible, "developer metrics hidden by default")
    _check(not build.panel.visible, "building mode starts closed")
    _check(scene.get_node("Overlay") != null, "authoritative world overlay remains")
    _check(scene.has_method("refresh_parcels"), "server parcel refresh retained")
    _check(scene.has_method("draw_overlay"), "world rendering retained")
    _check(scene.get_node("API") != null, "server API remains connected")
    scene.queue_free()
    if failures == 0:
        print("BASHECO_MAP_AB_OK debug_hidden=1 authoritative_overlay=1")
    quit(failures)