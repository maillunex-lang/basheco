extends RefCounted
## Original vector-drawn 2D isometric building art for server-confirmed parcels.
## No 3D meshes, no claims about actual building height or physical appearance.
const ROOFS := {
    "commercial": Color("#dca76b"),
    "industrial": Color("#91b4c1"),
    "agricultural": Color("#a6c59a")
}

static func draw_building(canvas: CanvasItem, world: Node2D, plot: Dictionary) -> void:
    if plot.get("building_id") == null:
        return
    var width := clampi(int(plot.get("width_cells", 1)), 1, 16)
    var height := clampi(int(plot.get("height_cells", 1)), 1, 16)
    var origin := Vector2i(int(plot["cell_x"]), int(plot["cell_y"]))
    var zone := str(plot.get("zone", "commercial"))
    var roof: Color = ROOFS.get(zone, Color("#c8b7a1"))
    var left: Vector2 = world.project_cell(origin)
    var top: Vector2 = world.project_cell(origin + Vector2i(width, 0))
    var right: Vector2 = world.project_cell(origin + Vector2i(width, height))
    var bottom: Vector2 = world.project_cell(origin + Vector2i(0, height))
    var rise: float = minf(58.0, 18.0 + float(mini(width, height)) * 6.0) * world.zoom_level
    var lift := Vector2(0.0, -rise)
    var base := PackedVector2Array([left, top, right, bottom])
    var roof_poly := PackedVector2Array([left + lift, top + lift, right + lift, bottom + lift])
    # Ground shadow stays inside the owned server parcel footprint.
    canvas.draw_colored_polygon(base, Color("#172d2a", 0.45))
    canvas.draw_colored_polygon(PackedVector2Array([bottom, right, right + lift, bottom + lift]), roof.darkened(0.43))
    canvas.draw_colored_polygon(PackedVector2Array([top, right, right + lift, top + lift]), roof.darkened(0.27))
    canvas.draw_colored_polygon(roof_poly, roof)
    canvas.draw_polyline(PackedVector2Array([left + lift, top + lift, right + lift, bottom + lift, left + lift]), roof.lightened(0.24), maxf(1.0, world.zoom_level * 1.5), true)
    # Door indicates the south-facing facade without implying a real entrance.
    var door: Vector2 = (bottom + right) * 0.5
    var dw := clampf(world.zoom_level * 5.0, 2.0, 11.0)
    canvas.draw_colored_polygon(PackedVector2Array([
        door - Vector2(dw, 0), door + Vector2(dw, 0),
        door + Vector2(dw, -rise * 0.45), door + Vector2(-dw, -rise * 0.45)
    ]), Color("#3d5251"))