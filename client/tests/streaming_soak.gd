extends SceneTree
## Long camera trips between the settlements: chunks must be released, memory and
## node counts must not grow from lap to lap. Prints only measured values.
## With a window (not --headless) it also reports real frame times of this machine.
const LAPS := 6
var failures := 0

func check(condition: bool, message: String) -> void:
    if not condition:
        failures += 1
        printerr("FAIL: " + message)

func _initialize() -> void:
    call_deferred("_run")

func travel(world: Node2D, target: Vector2i, frame_times: Array) -> Dictionary:
    var peak_chunks := 0
    var peak_features := 0
    var steps := 0
    while world.camera_center_cell().distance_to(target) > 30 and steps < 5000:
        var direction := Vector2(target - world.camera_center_cell()).normalized() * 6.0
        world.camera_offset -= world.iso(direction.x, direction.y) * world.zoom_level
        world._camera_changed()
        var started := Time.get_ticks_usec()
        await process_frame
        frame_times.append(Time.get_ticks_usec() - started)
        peak_chunks = maxi(peak_chunks, world.geo_background.loaded.size())
        peak_features = maxi(peak_features, world.geo_background.loaded_feature_count())
        steps += 1
    return {"steps": steps, "peak_chunks": peak_chunks, "peak_features": peak_features}

func _run() -> void:
    var world: Node2D = load("res://scenes/world.tscn").instantiate()
    root.add_child(world)
    await process_frame
    world.get_node("Login")._preview_map()
    world.get_node("Geography").hide()
    var geo = world.geo_background
    var ufa: Vector2i = geo.settlements["ufa"]["focus_cell"]
    var mikhailovka: Vector2i = geo.settlements["mikhailovka"]["focus_cell"]
    world.open_location("ufa")
    world.zoom_at(world.get_viewport_rect().size * 0.5, 0.6 / world.zoom_level)
    var memory: Array[float] = []
    var objects: Array[int] = []
    var nodes: Array[int] = []
    var frame_times: Array = []
    var peak_chunks := 0
    var peak_features := 0
    for lap in range(LAPS):
        for target in [mikhailovka, ufa]:
            var result: Dictionary = await travel(world, target, frame_times)
            check(world.camera_center_cell().distance_to(target) <= 30, "lap %d reached target" % lap)
            peak_chunks = maxi(peak_chunks, result["peak_chunks"])
            peak_features = maxi(peak_features, result["peak_features"])
        for _i in range(10):
            await process_frame
        memory.append(Performance.get_monitor(Performance.MEMORY_STATIC) / 1048576.0)
        objects.append(int(Performance.get_monitor(Performance.OBJECT_COUNT)))
        nodes.append(int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)))
    check(peak_chunks <= geo.MAX_ACTIVE_CHUNKS, "chunk cap respected: %d" % peak_chunks)
    check(peak_features < int(geo.manifest["exported_piece_count"]), "atlas never fully in memory")
    check(geo.stats["duplicates"] == 0, "no duplicates after %d laps" % LAPS)
    check(geo.stats["evictions"] > LAPS * 20, "chunks released: %d" % geo.stats["evictions"])
    check(geo.uid_owner.size() < 2 * peak_features + 16, "uid table does not leak")
    # Lap 0 warms caches; afterwards memory and object counts must be flat.
    check(memory[LAPS - 1] - memory[1] < 1.0, "memory growth after warm-up: %.3f MB" % (memory[LAPS - 1] - memory[1]))
    check(absi(objects[LAPS - 1] - objects[1]) <= 8, "object count stable: %d -> %d" % [objects[1], objects[LAPS - 1]])
    check(absi(nodes[LAPS - 1] - nodes[1]) <= 2, "node count stable: %d -> %d" % [nodes[1], nodes[LAPS - 1]])
    frame_times.sort()
    var count := frame_times.size()
    print("BASHECO_SOAK laps=%d frames=%d loads=%d evictions=%d peak_chunks=%d peak_features=%d" % [LAPS, count, geo.stats["loads"], geo.stats["evictions"], peak_chunks, peak_features])
    print("BASHECO_SOAK memory_static_mb_per_lap=%s objects_per_lap=%s nodes_per_lap=%s" % [memory, objects, nodes])
    print("BASHECO_SOAK renderer=%s frame_ms median=%.2f p95=%.2f max=%.2f" % [
        DisplayServer.get_name(), float(frame_times[count / 2]) / 1000.0, float(frame_times[int(count * 0.95)]) / 1000.0, float(frame_times[count - 1]) / 1000.0])
    if failures == 0:
        print("BASHECO_SOAK_OK")
    quit(1 if failures > 0 else 0)
