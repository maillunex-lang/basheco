extends RefCounted
## Real geography of the single BASHECO world (data/world, EPSG:32640).
## There is one atlas and one coordinate system for every settlement. Chunks of
## 64x64 global cells are streamed around the camera and released when far away.
## OSM objects are read-only background and never become playable plots.
const WorldGrid = preload("res://scripts/world_grid.gd")
const ChunkNode = preload("res://scripts/geo_chunk_node.gd")
const ATLAS_DIR := "res://data/world/"
const ATLAS_SCHEMA := "basheco.world_atlas/2"
const CHUNK_SCHEMA := "basheco.world_chunk/2"
const BUILDING_SPRITES := [
    preload("res://assets/kenney/building_45.png"),
    preload("res://assets/kenney/building_55.png"),
    preload("res://assets/kenney/building_85.png"),
    preload("res://assets/kenney/building_115.png")
]
const TREE_SPRITES := [
    preload("res://assets/kenney/detail_10.png"),
    preload("res://assets/kenney/city_36.png")
]
const MAX_BUILDING_SPRITES := 140
const MAX_TREE_SPRITES := 60
const MAX_ACTIVE_CHUNKS := 64
const CHUNKS_PER_FRAME := 2
const LOAD_RING_CHUNKS := 1      # polygons may reach one chunk past their home chunk
const STREAMING_MAX_LOD := 2     # at overview zoom no detail chunks are held at all
var manifest: Dictionary = {}
var settlements: Dictionary = {}       # id -> {name, kind, focus_cell, rings, anchor}
var settlement_order: Array[String] = []
var chunk_index: Dictionary = {}       # Vector2i global chunk -> feature count
var loaded: Dictionary = {}            # Vector2i -> ChunkNode
var uid_owner: Dictionary = {}         # feature uid -> Vector2i chunk that draws it
var requested_chunks: Array[Vector2i] = []
var pending_chunks: Array[Vector2i] = []
var active_chunk_ids: Array[Vector2i] = []
var static_nodes: Array = []
var terrain_range: Dictionary = {}     # settlement id -> Vector2(min, max) metres
var nav_bounds: Array[int] = [0, 0, 0, 0]
var layer: Node2D
var ready := false
var stats := {"loads": 0, "evictions": 0, "duplicates": 0, "rejected": 0}

static func _read_json(path: String) -> Variant:
    var file := FileAccess.open(path, FileAccess.READ)
    if file == null:
        return null
    return JSON.parse_string(file.get_as_text())

## Convert atlas points [[E, N], ...] to cells relative to anchor (64-bit math first).
static func to_relative(points: Array, anchor: Vector2i) -> PackedVector2Array:
    var result := PackedVector2Array()
    for point in points:
        if typeof(point) != TYPE_ARRAY or point.size() < 2:
            return PackedVector2Array()
        var cell := WorldGrid.metres_to_cell_f(float(point[0]), float(point[1]))
        result.append(Vector2(cell[0] - float(anchor.x), cell[1] - float(anchor.y)))
    return result

func load_world(parent: Node2D) -> void:
    ready = false
    var data: Variant = _read_json(ATLAS_DIR + "manifest.json")
    if typeof(data) != TYPE_DICTIONARY or str(data.get("schema", "")) != ATLAS_SCHEMA:
        push_error("World atlas missing or of another format")
        return
    if not WorldGrid.matches(data):
        push_error("World atlas uses another grid than this client")
        return
    manifest = data
    layer = Node2D.new()
    layer.name = "Geography2D"
    parent.add_child(layer)
    for entry in manifest.get("chunks", []):
        chunk_index[Vector2i(int(entry[0]), int(entry[1]))] = int(entry[2])
    var bounds: Array = manifest.get("navigation_bounds_cells", [0, 0, 0, 0])
    nav_bounds = [int(bounds[0]), int(bounds[1]), int(bounds[2]), int(bounds[3])]
    _extend_navigation_bounds_from_registry()
    for item in manifest.get("settlements", []):
        var id := str(item["id"])
        var focus := Vector2i(int(item["focus_cell"][0]), int(item["focus_cell"][1]))
        settlements[id] = {"name": str(item["name"]), "kind": str(item.get("kind", "")),
            "focus_cell": focus, "anchor": WorldGrid.chunk_origin_cell(WorldGrid.cell_to_chunk(focus.x, focus.y)),
            "rings": []}
        settlement_order.append(id)
    _load_boundaries()
    _load_elevation()
    _load_coverage()
    _load_large()
    ready = true

## The OSM atlas covers only two fragments; navigation covers all confirmed
## settlement anchors of the republic. Never clamp a valid catalog location to
## the legacy Ufa/Mikhailovka atlas bounds.
func _extend_navigation_bounds_from_registry() -> void:
    var data: Variant = _read_json("res://data/admin_navigation.json")
    if typeof(data) != TYPE_DICTIONARY or str(data.get("schema", "")) != "basheco.navigation/1":
        return
    var margin := 128
    for district in data.get("districts", []):
        for settlement in district.get("locations", []):
            var cell: Variant = settlement.get("cell")
            if typeof(cell) != TYPE_ARRAY or cell.size() != 2:
                continue
            var x := int(cell[0])
            var y := int(cell[1])
            nav_bounds[0] = mini(nav_bounds[0], x - margin)
            nav_bounds[1] = mini(nav_bounds[1], y - margin)
            nav_bounds[2] = maxi(nav_bounds[2], x + margin)
            nav_bounds[3] = maxi(nav_bounds[3], y + margin)

func _static_node(anchor: Vector2i, features: Array, node_name: String) -> void:
    var node: Node2D = ChunkNode.new()
    node.name = node_name
    node.anchor_cell = anchor
    node.features = features
    layer.add_child(node)
    static_nodes.append(node)

func _load_boundaries() -> void:
    var data: Variant = _read_json(ATLAS_DIR + "boundaries.json")
    if typeof(data) != TYPE_DICTIONARY or str(data.get("crs", "")) != WorldGrid.CRS:
        return
    for boundary in data.get("boundaries", []):
        var id := str(boundary.get("location_id", ""))
        if not settlements.has(id):
            continue
        var anchor: Vector2i = settlements[id]["anchor"]
        var features: Array = []
        for ring in boundary.get("rings_m", []):
            var points := to_relative(ring, anchor)
            if points.size() >= 3:
                settlements[id]["rings"].append(points)
                features.append({"kind": "boundary", "geom": "line", "pts": points})
        settlements[id]["boundary_source_url"] = str(boundary.get("source_url", ""))
        _static_node(anchor, features, "Boundary_" + id)

func _load_elevation() -> void:
    var data: Variant = _read_json(ATLAS_DIR + "elevation.json")
    if typeof(data) != TYPE_DICTIONARY or str(data.get("crs", "")) != WorldGrid.CRS:
        return
    for grid in data.get("grids", []):
        var id := str(grid.get("location_id", ""))
        var width := int(grid.get("width", 0))
        var height := int(grid.get("height", 0))
        var samples: Array = grid.get("samples_m", [])
        if not settlements.has(id) or str(grid.get("dataset", "")) != "srtm30m":
            continue
        if width < 2 or height < 2 or samples.size() != width * height:
            continue
        var anchor: Vector2i = settlements[id]["anchor"]
        var cells: Array = []
        var lowest := INF
        var highest := -INF
        for sample in samples:
            var relative := to_relative([sample], anchor)
            cells.append({"tile": relative[0], "height": float(sample[2])})
            lowest = minf(lowest, float(sample[2]))
            highest = maxf(highest, float(sample[2]))
        terrain_range[id] = Vector2(lowest, highest)
        var features: Array = []
        # 10 m contour lines interpolated from the sampled SRTM grid (unchanged method).
        for level in range(int(ceil(lowest / 10.0)) * 10, int(floor(highest / 10.0)) * 10 + 1, 10):
            for y in range(height - 1):
                for x in range(width - 1):
                    var a: Dictionary = cells[y * width + x]
                    var b: Dictionary = cells[y * width + x + 1]
                    var c: Dictionary = cells[(y + 1) * width + x + 1]
                    var d: Dictionary = cells[(y + 1) * width + x]
                    var crossings: Array[Vector2] = []
                    for edge in [[a, b], [b, c], [c, d], [d, a]]:
                        var h0 := float(edge[0]["height"])
                        var h1 := float(edge[1]["height"])
                        if (h0 < level and h1 >= level) or (h1 < level and h0 >= level):
                            crossings.append((edge[0]["tile"] as Vector2).lerp(edge[1]["tile"], (float(level) - h0) / (h1 - h0)))
                    if crossings.size() == 2 or crossings.size() == 4:
                        features.append({"kind": "contour", "geom": "line", "pts": PackedVector2Array([crossings[0], crossings[1]])})
                    if crossings.size() == 4:
                        features.append({"kind": "contour", "geom": "line", "pts": PackedVector2Array([crossings[2], crossings[3]])})
        _static_node(anchor, features, "Contours_" + id)

func _load_coverage() -> void:
    # Outline of every imported source extract: outside it the map is simply not imported yet.
    for source in manifest.get("sources", []):
        var id := str(source.get("location_id", ""))
        if not settlements.has(id):
            continue
        var anchor: Vector2i = settlements[id]["anchor"]
        var points := to_relative(source.get("coverage_ring_m", []), anchor)
        if points.size() >= 4:
            _static_node(anchor, [{"kind": "coverage", "geom": "line", "pts": points}], "Coverage_" + str(source.get("id", "")))

func _load_large() -> void:
    var data: Variant = _read_json(ATLAS_DIR + "large.json")
    if typeof(data) != TYPE_DICTIONARY or str(data.get("schema", "")) != CHUNK_SCHEMA:
        return
    var groups: Dictionary = {}
    for raw in data.get("features", []):
        var points: Array = raw.get("points", [])
        if points.is_empty():
            continue
        var home := WorldGrid.metres_to_cell(float(points[0][0]), float(points[0][1]))
        var chunk := WorldGrid.cell_to_chunk(home.x, home.y)
        if not groups.has(chunk):
            groups[chunk] = []
        groups[chunk].append(raw)
    for chunk in groups:
        var anchor := WorldGrid.chunk_origin_cell(chunk)
        var features: Array = []
        for raw in groups[chunk]:
            var feature := _prepare(raw, anchor, Vector2i(2147483647, 0))
            if not feature.is_empty():
                features.append(feature)
        _static_node(anchor, features, "Large_%d_%d" % [chunk.x, chunk.y])

func _prepare(raw: Dictionary, anchor: Vector2i, owner: Vector2i) -> Dictionary:
    var uid := str(raw.get("uid", ""))
    var points := to_relative(raw.get("points", []), anchor)
    if uid.is_empty() or points.size() < 2:
        stats["rejected"] += 1
        return {}
    if uid_owner.has(uid):
        stats["duplicates"] += 1
        return {}
    uid_owner[uid] = owner
    var minimum := points[0]
    var maximum := points[0]
    for point in points:
        minimum = minimum.min(point)
        maximum = maximum.max(point)
    var feature := {"uid": uid, "osm_id": str(raw.get("osm_id", "")), "kind": str(raw.get("kind", "")),
        "subtype": str(raw.get("subtype", "")), "geom": str(raw.get("geom", "line")),
        "pts": points, "min": minimum, "max": maximum, "fill_ok": false}
    if feature["geom"] == "polygon" and points.size() >= 4:
        var ring := points.duplicate()
        ring.resize(ring.size() - 1)
        if not Geometry2D.triangulate_polygon(ring).is_empty():
            feature["fill"] = ring
            feature["fill_ok"] = true
    return feature

## Chunks that must be present for the current camera: on-screen chunks plus a ring.
func desired_chunks(world: Node2D) -> Array[Vector2i]:
    var desired: Array[Vector2i] = []
    if not ready or world.lod() > STREAMING_MAX_LOD:
        return desired
    var bounds: Array[int] = world.visible_cell_bounds()
    var first := WorldGrid.cell_to_chunk(bounds[0], bounds[1])
    var last := WorldGrid.cell_to_chunk(bounds[2] - 1, bounds[3] - 1)
    var screen := Rect2(Vector2.ZERO, world.get_viewport_rect().size)
    var reach: float = float(WorldGrid.CHUNK_CELLS) * 64.0 * world.zoom_level * float(LOAD_RING_CHUNKS + 1)
    screen = screen.grow(reach)
    var center: Vector2i = world.camera_center_cell()
    var center_chunk := Vector2(float(center.x) / WorldGrid.CHUNK_CELLS, float(center.y) / WorldGrid.CHUNK_CELLS)
    if (last.x - first.x + 3) * (last.y - first.y + 3) > 4096:
        return desired
    for cy in range(first.y - LOAD_RING_CHUNKS, last.y + LOAD_RING_CHUNKS + 1):
        for cx in range(first.x - LOAD_RING_CHUNKS, last.x + LOAD_RING_CHUNKS + 1):
            var key := Vector2i(cx, cy)
            if not chunk_index.has(key):
                continue
            var middle := WorldGrid.chunk_origin_cell(key) + Vector2i(WorldGrid.CHUNK_CELLS / 2, WorldGrid.CHUNK_CELLS / 2)
            if screen.has_point(world.project_cell(middle)):
                desired.append(key)
    desired.sort_custom(func(a: Vector2i, b: Vector2i) -> bool:
        return (Vector2(a) + Vector2(0.5, 0.5)).distance_squared_to(center_chunk) < (Vector2(b) + Vector2(0.5, 0.5)).distance_squared_to(center_chunk))
    if desired.size() > MAX_ACTIVE_CHUNKS:
        desired.resize(MAX_ACTIVE_CHUNKS)
    return desired

## Schedule loads and release far chunks. Cheap when the wanted set did not change.
func update_view(world: Node2D) -> void:
    if not ready:
        return
    var desired := desired_chunks(world)
    if desired != requested_chunks:
        requested_chunks = desired
        for key in loaded.keys():
            if not desired.has(key):
                _evict(key)
        pending_chunks.clear()
        for key in desired:
            if not loaded.has(key):
                pending_chunks.append(key)
        _refresh_active()
    apply_camera(world)

func _evict(key: Vector2i) -> void:
    var node: Node2D = loaded[key]
    for feature in node.features:
        uid_owner.erase(feature["uid"])
    loaded.erase(key)
    layer.remove_child(node)
    node.queue_free()
    stats["evictions"] += 1

func _refresh_active() -> void:
    active_chunk_ids.clear()
    for key in requested_chunks:
        if loaded.has(key):
            active_chunk_ids.append(key)

## Bounded cooperative streaming: at most CHUNKS_PER_FRAME small JSON files per frame.
func process_pending_chunks(world: Node2D) -> bool:
    if pending_chunks.is_empty():
        return false
    var loaded_any := false
    for i in range(mini(CHUNKS_PER_FRAME, pending_chunks.size())):
        var key: Vector2i = pending_chunks.pop_front()
        if not requested_chunks.has(key) or loaded.has(key):
            continue
        if _load_chunk(key):
            loaded_any = true
    if loaded_any:
        _refresh_active()
        apply_camera(world)
    return loaded_any

func _load_chunk(key: Vector2i) -> bool:
    var path := str(manifest.get("chunk_path_template", "")).replace("{x}", str(key.x)).replace("{y}", str(key.y))
    var data: Variant = _read_json(path)
    if typeof(data) != TYPE_DICTIONARY or str(data.get("schema", "")) != CHUNK_SCHEMA \
            or str(data.get("crs", "")) != WorldGrid.CRS or str(data.get("grid_version", "")) != WorldGrid.GRID_VERSION:
        push_warning("Geography chunk missing or incompatible: " + str(key))
        return false
    var declared: Array = data.get("chunk", [])
    if declared.size() != 2 or Vector2i(int(declared[0]), int(declared[1])) != key:
        push_warning("Geography chunk has another address: " + str(key))
        return false
    var node: Node2D = ChunkNode.new()
    node.name = "Chunk_%d_%d" % [key.x, key.y]
    node.anchor_cell = WorldGrid.chunk_origin_cell(key)
    for raw in data.get("features", []):
        var feature := _prepare(raw, node.anchor_cell, key)
        if not feature.is_empty():
            node.features.append(feature)
    loaded[key] = node
    layer.add_child(node)
    stats["loads"] += 1
    return true

## Position every geography node for the current camera (no geometry is rebuilt).
func apply_camera(world: Node2D) -> void:
    if not ready:
        return
    var basis_x: Vector2 = Vector2(world.TILE_W * 0.5, world.TILE_H * 0.5) * world.zoom_level
    var basis_y: Vector2 = Vector2(-world.TILE_W * 0.5, world.TILE_H * 0.5) * world.zoom_level
    var band: float = world.zoom_band()
    var level: int = world.lod()
    for node in static_nodes + loaded.values():
        node.transform = Transform2D(basis_x, basis_y, world.project_cell(node.anchor_cell))
        node.configure(band, level)

func loaded_feature_count() -> int:
    var total := 0
    for node in loaded.values():
        total += node.features.size()
    return total

## Settlement whose sourced boundary contains the cell, or "" outside all of them.
func settlement_at(cell: Vector2i) -> String:
    for id in settlement_order:
        var anchor: Vector2i = settlements[id]["anchor"]
        var point := Vector2(cell - anchor)
        for ring in settlements[id]["rings"]:
            if Geometry2D.is_point_in_polygon(point, ring):
                return id
    return ""

func nearest_settlement(cell: Vector2i) -> String:
    var best := ""
    var best_distance := INF
    for id in settlement_order:
        var distance := Vector2(cell - (settlements[id]["focus_cell"] as Vector2i)).length()
        if distance < best_distance:
            best_distance = distance
            best = id
    return best

## Screen-space sprites for sourced buildings and forests (upright, never skewed).
func render_sprites(world: Node2D, canvas: CanvasItem) -> void:
    if not ready or world.lod() > 0:
        return
    var bounds: Array[int] = world.visible_cell_bounds()
    var drawn_buildings := 0
    var drawn_trees := 0
    var decorations: Array[Dictionary] = []
    var nodes: Array = static_nodes.duplicate()
    for key in active_chunk_ids:
        if loaded.has(key):
            nodes.append(loaded[key])
    for node in nodes:
        var anchor: Vector2i = node.anchor_cell
        var low := Vector2(float(bounds[0] - anchor.x), float(bounds[1] - anchor.y))
        var high := Vector2(float(bounds[2] - anchor.x), float(bounds[3] - anchor.y))
        for feature in node.features:
            var kind := str(feature["kind"])
            if kind != "building" and kind != "forest":
                continue
            var minimum: Vector2 = feature["min"]
            var maximum: Vector2 = feature["max"]
            if maximum.x < low.x or maximum.y < low.y or minimum.x > high.x or minimum.y > high.y:
                continue
            if kind == "building" and drawn_buildings < MAX_BUILDING_SPRITES:
                var center := (minimum + maximum) * 0.5
                var where: Vector2 = world.project_cell(anchor, center)
                var footprint := maxf(maximum.x - minimum.x, maximum.y - minimum.y)
                var sprite_width: float = clampf(footprint * 9.0 * world.zoom_level, 22.0, 68.0)
                var seed_x := float(anchor.x) + center.x
                var seed_y := float(anchor.y) + center.y
                var texture: Texture2D = BUILDING_SPRITES[posmod(int(absf(seed_x * 17.0 + seed_y * 31.0)), BUILDING_SPRITES.size())]
                var sprite_height: float = sprite_width * float(texture.get_height()) / float(texture.get_width())
                decorations.append({
                    "depth": where.y, "texture": texture,
                    "rect": Rect2(where.x - sprite_width * 0.5, where.y - sprite_height * 0.86, sprite_width, sprite_height),
                    "tint": Color(1, 1, 1, 0.12) if world.fade_occluding_buildings else Color.WHITE
                })
                drawn_buildings += 1
            elif kind == "forest" and feature.get("fill_ok", false) and drawn_trees < MAX_TREE_SPRITES:
                # Trees stand on a fixed 8-cell lattice of the world grid, inside the real polygon.
                var from_x := maxi(bounds[0], anchor.x + int(floor(minimum.x)))
                var to_x := mini(bounds[2], anchor.x + int(ceil(maximum.x)))
                var from_y := maxi(bounds[1], anchor.y + int(floor(minimum.y)))
                var to_y := mini(bounds[3], anchor.y + int(ceil(maximum.y)))
                var gx := WorldGrid.floor_div(from_x + 7, 8) * 8
                while gx <= to_x and drawn_trees < MAX_TREE_SPRITES:
                    var gy := WorldGrid.floor_div(from_y + 7, 8) * 8
                    while gy <= to_y and drawn_trees < MAX_TREE_SPRITES:
                        var local := Vector2(float(gx - anchor.x), float(gy - anchor.y))
                        if Geometry2D.is_point_in_polygon(local, feature["fill"]):
                            var tree_at: Vector2 = world.project_cell(Vector2i(gx, gy))
                            var tree_width: float = 28.0 * world.zoom_level
                            var tree_seed := posmod(gx * 17 + gy * 31, TREE_SPRITES.size())
                            decorations.append({
                                "depth": tree_at.y, "texture": TREE_SPRITES[tree_seed],
                                "rect": Rect2(tree_at.x - tree_width * 0.5, tree_at.y - tree_width, tree_width, tree_width),
                                "tint": Color.WHITE
                            })
                            drawn_trees += 1
                        gy += 8
                    gx += 8
    # Isometric painter order: northern objects first, southern objects in front.
    # Only visible sourced objects are considered, with fixed per-frame caps.
    decorations.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
        return float(a["depth"]) < float(b["depth"]))
    for decoration in decorations:
        canvas.draw_texture_rect(decoration["texture"], decoration["rect"], false, decoration["tint"])