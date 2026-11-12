extends RefCounted
## Shared continuous coordinates. Chunks are a rendering/loading detail, not separate maps.
const CHUNK_SIZE := 64

static func chunk_for_tile(x: int, y: int) -> Vector2i:
    return Vector2i(floori(float(x) / CHUNK_SIZE), floori(float(y) / CHUNK_SIZE))

static func chunks_for_bounds(bounds: Array[int], padding: int = 1) -> Array[Vector2i]:
    var found: Array[Vector2i] = []
    if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
        return found
    var left := floori(float(bounds[0]) / CHUNK_SIZE) - padding
    var top := floori(float(bounds[1]) / CHUNK_SIZE) - padding
    var right := floori(float(bounds[2] - 1) / CHUNK_SIZE) + padding
    var bottom := floori(float(bounds[3] - 1) / CHUNK_SIZE) + padding
    for cy in range(top, bottom + 1):
        for cx in range(left, right + 1):
            found.append(Vector2i(cx, cy))
    return found

static func plot_intersects_bounds(plot: Dictionary, bounds: Array[int]) -> bool:
    var x := int(plot["tile_x"])
    var y := int(plot["tile_y"])
    return x < bounds[2] and y < bounds[3] and x + int(plot["width_tiles"]) > bounds[0] and y + int(plot["height_tiles"]) > bounds[1]
