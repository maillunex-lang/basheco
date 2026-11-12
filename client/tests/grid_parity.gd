extends SceneTree
## Client grid math must equal the server's pyproj results (data/world/control_points.json).
const WorldGrid = preload("res://scripts/world_grid.gd")
var failures := 0

func check(condition: bool, message: String) -> void:
    if not condition:
        failures += 1
        printerr("FAIL: " + message)

func _initialize() -> void:
    var file := FileAccess.open("res://data/world/control_points.json", FileAccess.READ)
    var data: Dictionary = JSON.parse_string(file.get_as_text())
    check(WorldGrid.matches({"grid_version": data["grid_version"], "crs": data["crs"], "cell_metres": 6,
        "chunk_cells": 64, "origin_easting": 0, "origin_northing": 0}), "grid version/crs")
    var worst_m := 0.0
    var worst_deg := 0.0
    for point in data["points"]:
        var metres := WorldGrid.lonlat_to_metres(float(point["lon"]), float(point["lat"]))
        var error := maxf(absf(metres[0] - float(point["easting"])), absf(metres[1] - float(point["northing"])))
        worst_m = maxf(worst_m, error)
        check(error < 0.001, "%s forward error %f m" % [point["name"], error])
        var cell := WorldGrid.metres_to_cell(metres[0], metres[1])
        check(cell == Vector2i(int(point["cell"][0]), int(point["cell"][1])), "%s cell %s" % [point["name"], cell])
        check(WorldGrid.cell_to_chunk(cell.x, cell.y) == Vector2i(int(point["chunk"][0]), int(point["chunk"][1])), "%s chunk" % point["name"])
        check(WorldGrid.lonlat_to_cell(float(point["lon"]), float(point["lat"])) == cell, "lonlat_to_cell")
        var back := WorldGrid.metres_to_lonlat(float(point["easting"]), float(point["northing"]))
        var degrees := maxf(absf(back[0] - float(point["lon"])), absf(back[1] - float(point["lat"])))
        worst_deg = maxf(worst_deg, degrees)
        check(degrees < 2e-8, "%s inverse error %.10f deg" % [point["name"], degrees])
    check(data["points"].size() >= 9, "control point count")
    # Cell and chunk arithmetic, including negative indices and borders.
    check(WorldGrid.metres_to_cell(600000.0, 6060000.0) == Vector2i(100000, -1010000), "reference cell")
    check(WorldGrid.metres_to_cell(-0.1, 0.1) == Vector2i(-1, -1), "negative cell")
    check(WorldGrid.metres_to_cell(5.999, -5.999) == Vector2i(0, 0), "inside first cell")
    check(WorldGrid.metres_to_cell(6.0, -6.0) == Vector2i(1, 1), "cell border")
    check(WorldGrid.cell_to_chunk(-1, -1) == Vector2i(-1, -1), "negative chunk")
    check(WorldGrid.cell_to_chunk(-64, -65) == Vector2i(-1, -2), "negative chunk border")
    check(WorldGrid.cell_to_chunk(63, 64) == Vector2i(0, 1), "chunk border")
    check(WorldGrid.cell_to_chunk(72302, -1011032) == Vector2i(1129, -15798), "ufa chunk")
    check(WorldGrid.chunk_origin_cell(Vector2i(-1, 2)) == Vector2i(-64, 128), "chunk origin")
    var corner := WorldGrid.cell_to_metres(100000.0, -1010000.0)
    check(corner[0] == 600000.0 and corner[1] == 6060000.0, "cell to metres")
    check(not WorldGrid.matches({"grid_version": "basheco-grid/2", "crs": "EPSG:32640", "cell_metres": 6, "chunk_cells": 64, "origin_easting": 0, "origin_northing": 0}), "foreign grid rejected")
    if failures == 0:
        print("BASHECO_GRID_PARITY_OK points=%d worst_forward_m=%.6f worst_inverse_deg=%.10f" % [data["points"].size(), worst_m, worst_deg])
    quit(1 if failures > 0 else 0)
