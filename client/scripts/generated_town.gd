extends RefCounted
## BASHECO deterministic 2D town preview, version 1.
## Decorative-only. Never grants ownership, residents or placement permission.
## Server plots always win. Do not confuse this with published server scenery.
const SIZE := 56
const ROAD_STEP := 8
const FOOTPRINTS := [Vector2i(1, 1), Vector2i(1, 2), Vector2i(2, 2), Vector2i(3, 2), Vector2i(3, 3)]
const HOUSE_ART := [
    preload("res://assets/kenney/building_45.png"),
    preload("res://assets/kenney/building_55.png"),
    preload("res://assets/kenney/building_85.png"),
    preload("res://assets/kenney/building_115.png")
]
const TREE_ART := preload("res://assets/kenney/detail_10.png")

static func road_at(x: int, y: int, anchor: Vector2i) -> bool:
    return posmod(x - anchor.x, ROAD_STEP) == 0 or posmod(y - anchor.y, ROAD_STEP) == 0

static func overlaps_plot(x: int, y: int, w: int, h: int, plots: Array[Dictionary]) -> bool:
    for plot in plots:
        var px := int(plot["cell_x"])
        var py := int(plot["cell_y"])
        if x < px + int(plot["width_cells"]) and x + w > px and y < py + int(plot["height_cells"]) and y + h > py:
            return true
    return false

static func draw_town(canvas: CanvasItem, world: Node2D, view: Array[int], plots: Array[Dictionary]) -> void:
    if world.lod() > 1:
        return
    var focus: Vector2i = world.generated_focus_cell
    var anchor := focus - Vector2i(SIZE / 2, SIZE / 2)
    var min_x := maxi(view[0], anchor.x)
    var min_y := maxi(view[1], anchor.y)
    var max_x := mini(view[2], anchor.x + SIZE)
    var max_y := mini(view[3], anchor.y + SIZE)
    if min_x >= max_x or min_y >= max_y:
        return
    # Roads are actual one-cell strips. No old OSM footprints or giant polygons.
    for y in range(min_y, max_y):
        for x in range(min_x, max_x):
            if not road_at(x, y, anchor) or overlaps_plot(x, y, 1, 1, plots):
                continue
            var c := Vector2i(x, y)
            var tile := PackedVector2Array([world.project_cell(c), world.project_cell(c + Vector2i(1, 0)),
                world.project_cell(c + Vector2i(1, 1)), world.project_cell(c + Vector2i(0, 1))])
            canvas.draw_colored_polygon(tile, Color("#65716c"))
            if posmod(x - anchor.x, ROAD_STEP) == 0 and posmod(y - anchor.y, ROAD_STEP) != 0:
                canvas.draw_line(world.project_cell(c, Vector2(0.5, 0.2)), world.project_cell(c, Vector2(0.5, 0.8)), Color("#e4d6a8", 0.55), maxf(1.0, world.zoom_level), true)
    # Fixed blocks and stable per-cell footprints: no random flicker on pan.
    var objects: Array[Dictionary] = []
    for by in range(0, SIZE - ROAD_STEP, ROAD_STEP):
        for bx in range(0, SIZE - ROAD_STEP, ROAD_STEP):
            var block_seed := posmod((bx + 3) * 37 + (by + 7) * 71 + focus.x * 3 + focus.y, 2147483647)
            # Distinct neighborhoods: park, low-density housing, dense center.
            var neighborhood := posmod(block_seed / 11, 9)
            for slot in range(4):
                var local_x := 1 + (slot % 2) * 3
                var local_y := 1 + (slot / 2) * 3
                var seed := posmod(block_seed + slot * 59, 2147483647)
                var x := anchor.x + bx + local_x
                var y := anchor.y + by + local_y
                var footprint: Vector2i = FOOTPRINTS[posmod(seed, FOOTPRINTS.size())]
                if neighborhood == 0:
                    footprint = Vector2i(1, 1)
                if x + footprint.x >= anchor.x + bx + ROAD_STEP or y + footprint.y >= anchor.y + by + ROAD_STEP:
                    continue
                if x + footprint.x > max_x or y + footprint.y > max_y or x < min_x - 4 or y < min_y - 4:
                    continue
                if overlaps_plot(x, y, footprint.x, footprint.y, plots):
                    continue
                var foot := Vector2i(x, y)
                var where: Vector2 = world.project_cell(foot, Vector2(float(footprint.x) * 0.5, float(footprint.y) * 0.5))
                var sprite: Texture2D = TREE_ART if neighborhood == 0 or posmod(seed, 7) == 0 else HOUSE_ART[posmod(seed / 5, HOUSE_ART.size())]
                var size_px := clampf(float(maxi(footprint.x, footprint.y)) * 30.0 * world.zoom_level, 27.0, 130.0)
                if sprite == TREE_ART:
                    size_px = 28.0 * world.zoom_level
                var height_px := size_px * float(sprite.get_height()) / float(sprite.get_width())
                objects.append({"depth": where.y, "texture": sprite,
                    "rect": Rect2(where.x - size_px * 0.5, where.y - height_px * 0.85, size_px, height_px)})
    objects.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
        return float(a["depth"]) < float(b["depth"]))
    for item in objects:
        canvas.draw_texture_rect(item["texture"], item["rect"], false)