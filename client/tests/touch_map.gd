extends SceneTree
var failures := 0
func check(ok: bool, why: String) -> void:
    if not ok:
        failures += 1
        printerr("FAIL: " + why)
func _initialize() -> void:
    call_deferred("_run")
func _run() -> void:
    var world: Node2D = load("res://scenes/world.tscn").instantiate()
    root.add_child(world)
    await process_frame
    world.world_visible = true
    world.get_node("Login").panel.hide()
    var center := Vector2(450, 290)
    check(world._map_gesture_allowed(center), "map gestures allowed")
    check(not world._map_gesture_allowed(Vector2(400, 25)), "HUD protected")
    var down := InputEventScreenTouch.new()
    down.index = 0
    down.position = center
    down.pressed = true
    world._input(down)
    var before: Vector2 = world.camera_offset
    var drag := InputEventScreenDrag.new()
    drag.index = 0
    drag.position = center + Vector2(85, 40)
    world._input(drag)
    check(world.camera_offset.distance_to(before) > 30.0, "single finger pan")
    var second := InputEventScreenTouch.new()
    second.index = 1
    second.position = center + Vector2(150, 0)
    second.pressed = true
    world._input(second)
    var old_zoom: float = world.zoom_level
    var pinch := InputEventScreenDrag.new()
    pinch.index = 1
    pinch.position = center + Vector2(210, 0)
    world._input(pinch)
    check(world.zoom_level > old_zoom, "pinch zoom in")
    check(world.touch_moved.get(0, false), "drag is not a tap")
    world.queue_free()
    if failures == 0:
        print("BASHECO_TOUCH_OK pan=1 pinch=1 hud_guard=1")
    quit(failures)