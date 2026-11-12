extends SceneTree
## Test the Android alpha parcel controls without touching a real game server.
const WorldGrid = preload("res://scripts/world_grid.gd")
var failures := 0

func check(ok: bool, message: String) -> void:
    if not ok:
        failures += 1
        printerr("FAIL: " + message)

func _initialize() -> void:
    call_deferred("_run")

func _run() -> void:
    var world: Node2D = load("res://scenes/world.tscn").instantiate()
    root.add_child(world)
    await process_frame
    var build = world.get_node("Build")
    check(build.sector_picker.item_count == 2, "only verified alpha settlements")
    check(build.zone_picker.item_count == 3, "three server-authorized plot zones")
    check(build.plot_button.disabled, "cannot provision parcels without auth")
    var cell: Vector2i = world.camera_center_cell()
    var metres: PackedFloat64Array = WorldGrid.cell_to_metres(float(cell.x), float(cell.y))
    var lonlat: PackedFloat64Array = WorldGrid.metres_to_lonlat(metres[0], metres[1])
    var origin := {
        "origin_lon": lonlat[0], "origin_lat": lonlat[1],
        "origin_tile_x": 400, "origin_tile_y": 400,
        "metres_per_tile": 6.0, "projection": "local_equirectangular_metres"
    }
    check(build._legacy_tile_for_cell(origin, cell) == Vector2i(400, 400),
        "alpha tile picker matches exact world cell at legacy anchor")
    origin["metres_per_tile"] = 0.0
    check(build._legacy_tile_for_cell(origin, cell) == Vector2i(-1, -1),
        "invalid legacy scale is refused")
    world.queue_free()
    if failures == 0:
        print("BASHECO_ANDROID_PLOT_UI_OK sectors=2 zones=3 anchor_inverse=1")
    quit(failures)