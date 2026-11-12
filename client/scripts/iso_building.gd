extends RefCounted
## Original vector-drawn 2D isometric building art for server-confirmed parcels.
## No 3D meshes, no claims about actual building height or physical appearance.
# CC0 Kenney Isometric Buildings sprites, reused at a bounded mobile size.
const SPRITES := {
    "commercial": preload("res://assets/kenney/building_45.png"),
    "industrial": preload("res://assets/kenney/building_115.png"),
    "agricultural": preload("res://assets/kenney/building_55.png")
}
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
    # A licensed 2D sprite provides the detailed facade. Vector geometry behind
    # it preserves the authoritative parcel footprint at every supported size.
    var texture: Texture2D = SPRITES.get(zone, SPRITES["commercial"])
    var footprint_px: float = maxf(top.distance_to(left), bottom.distance_to(left))
    var sprite_width: float = clampf(footprint_px * 0.82, 30.0 * world.zoom_level, 160.0 * world.zoom_level)
    var sprite_height: float = sprite_width * float(texture.get_height()) / float(texture.get_width())
    var anchor: Vector2 = (left + right) * 0.5
    canvas.draw_texture_rect(texture, Rect2(anchor.x - sprite_width * 0.5, anchor.y - sprite_height * 0.86, sprite_width, sprite_height), false)
    # Door indicates the south-facing facade without implying a real entrance.
    var door: Vector2 = (bottom + right) * 0.5
    var dw := clampf(world.zoom_level * 5.0, 2.0, 11.0)
    canvas.draw_colored_polygon(PackedVector2Array([
        door - Vector2(dw, 0), door + Vector2(dw, 0),
        door + Vector2(dw, -rise * 0.45), door + Vector2(-dw, -rise * 0.45)
    ]), Color("#3d5251"))