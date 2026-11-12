extends SceneTree
## End-to-end check against a real local BASHECO server (started by
## server/tests/e2e_world_client.py). Args after "--": URL TOKEN EXPECTED_JSON
## The client must show server plots at the server's world cells and derive the
## same WGS84 position for them as the server does.
const WorldGrid = preload("res://scripts/world_grid.gd")
var failures := 0

func check(condition: bool, message: String) -> void:
    if not condition:
        failures += 1
        printerr("FAIL: " + message)

func _initialize() -> void:
    call_deferred("_run")

func wait_for_plot(world: Node2D, plot_id: String) -> Dictionary:
    for _i in range(600):
        await process_frame
        for plot in world.plots:
            if str(plot.get("id", "")) == plot_id:
                return plot
    return {}

func _run() -> void:
    var args := OS.get_cmdline_user_args()
    if args.size() != 3:
        printerr("usage: -- URL TOKEN EXPECTED_JSON")
        quit(2)
        return
    var expected: Array = JSON.parse_string(args[2])
    var world: Node2D = load("res://scenes/world.tscn").instantiate()
    root.add_child(world)
    await process_frame
    var atlas = world.geo_background.manifest
    world.get_node("Login").panel.visible = false
    world.world_visible = true
    world.connect_to_server(args[0], args[1])
    check(world.get_node("API").access_token == args[1], "client accepted the local server URL")
    var worst_m := 0.0
    for item in expected:
        var cell := Vector2i(int(item["world_cell_x"]), int(item["world_cell_y"]))
        world.zoom_level = world.DEFAULT_ZOOM
        world.center_on_cell(cell)
        world.refresh_parcels()
        var plot: Dictionary = await wait_for_plot(world, str(item["plot_id"]))
        check(not plot.is_empty(), "plot %s arrived from the global viewport" % item["plot_id"])
        if plot.is_empty():
            continue
        check(Vector2i(int(plot["cell_x"]), int(plot["cell_y"])) == cell, "client uses the server's world cell")
        check(str(plot["sector_id"]) == str(item["sector_id"]), "sector kept as metadata")
        # Same ground position on both sides: server lon/lat of the old tile corner
        # versus the client's own inverse projection of the world cell corner.
        var metres := WorldGrid.cell_to_metres(float(cell.x), float(cell.y))
        var lonlat := WorldGrid.metres_to_lonlat(metres[0], metres[1])
        var d_east := (lonlat[0] - float(item["lon"])) * 111320.0 * cos(deg_to_rad(lonlat[1]))
        var d_north := (lonlat[1] - float(item["lat"])) * 110540.0
        var distance := Vector2(d_east, d_north).length()
        worst_m = maxf(worst_m, distance)
        check(distance < 4.3, "ground position differs by %f m" % distance)
        check(absf(distance - float(item["snap_offset_m"])) < 0.05, "client distance equals the server's recorded snap offset")
        # And forward: the centre of that cell, projected by the client, is the same cell.
        var centre := WorldGrid.cell_to_metres(float(cell.x) + 0.5, float(cell.y) + 0.5)
        var centre_lonlat := WorldGrid.metres_to_lonlat(centre[0], centre[1])
        check(WorldGrid.lonlat_to_cell(centre_lonlat[0], centre_lonlat[1]) == cell, "client forward projection lands in the server cell")
        var on_screen: Vector2 = world.project_cell(cell, Vector2(2.5, 2.5))
        world._select_at(on_screen)
        check(world.selected_plot >= 0 and str(world.plots[world.selected_plot]["id"]) == str(item["plot_id"]), "plot selectable where it is drawn")
        check(world.current_location_id == str(item["expected_location"]), "camera is inside %s (got '%s')" % [item["expected_location"], world.current_location_id])
    check(is_same(world.geo_background.manifest, atlas), "one world for both settlements")
    if failures == 0:
        print("BASHECO_E2E_OK plots=%d worst_ground_offset_m=%.3f" % [expected.size(), worst_m])
    quit(1 if failures > 0 else 0)
