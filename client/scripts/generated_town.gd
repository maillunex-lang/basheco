extends RefCounted
## BASHECO deterministic 2D town preview, version 1.
## Decorative-only. Never grants ownership, residents or placement permission.
## Server plots always win. Do not confuse this with published server scenery.
const SIZE := 56
const ROAD_STEP := 8
const DISTRICT_NAMES := ["Центр", "Жилой район", "Промзона", "Парки", "Торговый район"]
const FOOTPRINTS := [Vector2i(1, 1), Vector2i(1, 2), Vector2i(2, 2), Vector2i(3, 2), Vector2i(3, 3)]
const HOUSE_ART := [
    preload("res://assets/kenney/building_45.png"),
    preload("res://assets/kenney/building_55.png"),
    preload("res://assets/kenney/building_85.png"),
    preload("res://assets/kenney/building_115.png")
]
const TREE_ART := preload("res://assets/kenney/detail_10.png")

static func road_at(x: int, y: int, anchor: Vector2i) -> bool:
    # A primary avenue every 16 cells and one-cell local streets every 8.
    return posmod(x - anchor.x, ROAD_STEP) == 0 or posmod(y - anchor.y, ROAD_STEP) == 0

static func district_at(x: int, y: int, anchor: Vector2i) -> int:
    var local := Vector2i(x - anchor.x, y - anchor.y)
    var center_distance := absi(local.x - SIZE / 2) + absi(local.y - SIZE / 2)
    if center_distance < 16:
        return 0
    if local.x > SIZE / 2 + 9 and local.y > SIZE / 2 + 3:
        return 2
    if local.x < SIZE / 2 - 9 and local.y < SIZE / 2 - 9:
        return 3
    if local.y < SIZE / 2 - 9:
        return 4
    return 1

static func land_value_band(x: int, y: int, anchor: Vector2i) -> int:
    # Relative illustration only, NOT a server economic price.
    var dist := absi(x - anchor.x - SIZE / 2) + absi(y - anchor.y - SIZE / 2)
    return 3 if dist < 14 else (2 if dist < 28 else 1)


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
            if overlaps_plot(x, y, 1, 1, plots):
                continue
            if not road_at(x, y, anchor):
                continue
            var c := Vector2i(x, y)
            var tile := PackedVector2Array([world.project_cell(c), world.project_cell(c + Vector2i(1, 0)),
                world.project_cell(c + Vector2i(1, 1)), world.project_cell(c + Vector2i(0, 1))])
            var arterial := posmod(x - anchor.x, ROAD_STEP * 2) == 0 or posmod(y - anchor.y, ROAD_STEP * 2) == 0
            canvas.draw_colored_polygon(tile, Color("#4f5b61") if arterial else Color("#717b76"))
            if posmod(x - anchor.x, ROAD_STEP) == 0 and posmod(y - anchor.y, ROAD_STEP) != 0:
                canvas.draw_line(world.project_cell(c, Vector2(0.5, 0.2)), world.project_cell(c, Vector2(0.5, 0.8)), Color("#e4d6a8", 0.55), maxf(1.0, world.zoom_level), true)
    # Fixed blocks and stable per-cell footprints: no random flicker on pan.
    var objects: Array[Dictionary] = []
    for by in range(0, SIZE - ROAD_STEP, ROAD_STEP):
        for bx in range(0, SIZE - ROAD_STEP, ROAD_STEP):
            var block_seed := posmod((bx + 3) * 37 + (by + 7) * 71 + focus.x * 3 + focus.y, 2147483647)
            # District zoning follows a stable spatial plan, not random per block.
            var neighborhood := district_at(anchor.x + bx + 3, anchor.y + by + 3, anchor)
            for slot in range(4):
                var local_x := 1 + (slot % 2) * 3
                var local_y := 1 + (slot / 2) * 3
                var seed := posmod(block_seed + slot * 59, 2147483647)
                var x := anchor.x + bx + local_x
                var y := anchor.y + by + local_y
                var footprint: Vector2i = FOOTPRINTS[posmod(seed, FOOTPRINTS.size())]
                if neighborhood == 0:
                    footprint = Vector2i(3, 3) if slot == 0 else Vector2i(2, 2)
                elif neighborhood == 2:
                    footprint = Vector2i(3, 2) if slot % 2 == 0 else Vector2i(2, 2)
                elif neighborhood == 3:
                    footprint = Vector2i(1, 1)
                elif neighborhood == 4:
                    footprint = Vector2i(2, 2)
                if x + footprint.x >= anchor.x + bx + ROAD_STEP or y + footprint.y >= anchor.y + by + ROAD_STEP:
                    continue
                if x + footprint.x > max_x or y + footprint.y > max_y or x < min_x - 4 or y < min_y - 4:
                    continue
                if overlaps_plot(x, y, footprint.x, footprint.y, plots):
                    continue
                var foot := Vector2i(x, y)
                var where: Vector2 = world.project_cell(foot, Vector2(float(footprint.x) * 0.5, float(footprint.y) * 0.5))
                var sprite: Texture2D = TREE_ART if neighborhood == 3 or posmod(seed, 9) == 0 else HOUSE_ART[posmod(seed / 5 + neighborhood, HOUSE_ART.size())]
                var size_px := clampf(float(maxi(footprint.x, footprint.y)) * 30.0 * world.zoom_level, 27.0, 130.0)
                if sprite == TREE_ART:
                    size_px = 28.0 * world.zoom_level
                var height_px := size_px * float(sprite.get_height()) / float(sprite.get_width())
                objects.append({"depth": where.y, "texture": sprite,
                    "rect": Rect2(where.x - size_px * 0.5, where.y - height_px * 0.85, size_px, height_px)})
    # A small park texture and sidewalk boundaries create visual landmarks.
    for by in range(0, SIZE - ROAD_STEP, ROAD_STEP):
        for bx in range(0, SIZE - ROAD_STEP, ROAD_STEP):
            var center := Vector2i(anchor.x + bx + 4, anchor.y + by + 4)
            if district_at(center.x, center.y, anchor) != 3:
                continue
            if center.x < min_x or center.x > max_x or center.y < min_y or center.y > max_y:
                continue
            if overlaps_plot(center.x - 2, center.y - 2, 4, 4, plots):
                continue
            var corners := PackedVector2Array([
                world.project_cell(center + Vector2i(-2, -2)),
                world.project_cell(center + Vector2i(2, -2)),
                world.project_cell(center + Vector2i(2, 2)),
                world.project_cell(center + Vector2i(-2, 2))])
            canvas.draw_colored_polygon(corners, Color("#427b50", 0.55))
    objects.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
        return float(a["depth"]) < float(b["depth"]))
    for item in objects:
        canvas.draw_texture_rect(item["texture"], item["rect"], false)
static func draw_minimap(canvas: CanvasItem, world: Node2D) -> void:
    if world.lod() > 2:
        return
    var screen: Vector2 = world.get_viewport_rect().size
    if screen.x < 600.0 or screen.y < 300.0:
        return
    var origin := Vector2(14, 76)
    var cell_px := 2.0
    var bounds := Rect2(origin - Vector2(7, 7), Vector2(SIZE, SIZE) * cell_px + Vector2(14, 24))
    canvas.draw_rect(bounds, Color("#142634", 0.89), true)
    var anchor: Vector2i = world.generated_focus_cell - Vector2i(SIZE / 2, SIZE / 2)
    var colors := [Color("#b58b56"), Color("#87b68c"), Color("#8b8b97"), Color("#4c9b6b"), Color("#d6bb78")]
    for y in range(SIZE):
        for x in range(SIZE):
            var c: Color = Color("#6b7378") if road_at(anchor.x + x, anchor.y + y, anchor) else colors[district_at(anchor.x + x, anchor.y + y, anchor)]
            canvas.draw_rect(Rect2(origin + Vector2(x, y) * cell_px, Vector2(cell_px, cell_px)), c, true)
    var center: Vector2i = world.camera_center_cell()
    var cursor := origin + Vector2(center - anchor) * cell_px
    canvas.draw_rect(Rect2(cursor - Vector2(4, 4), Vector2(8, 8)), Color.WHITE, false, 2.0)
    canvas.draw_string(ThemeDB.fallback_font, origin + Vector2(0, SIZE * cell_px + 13), "РАЙОНЫ", HORIZONTAL_ALIGNMENT_LEFT, -1, 11, Color.WHITE)