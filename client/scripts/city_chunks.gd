extends RefCounted
## Chunk helpers for game plots. Coordinates are global world cells (world_grid.gd);
## chunks are a loading detail of the one continuous world, never separate maps.
const WorldGrid = preload("res://scripts/world_grid.gd")
const CHUNK_SIZE := WorldGrid.CHUNK_CELLS

static func chunk_for_tile(x: int, y: int) -> Vector2i:
    return WorldGrid.cell_to_chunk(x, y)

static func chunks_for_bounds(bounds: Array[int], padding: int = 1) -> Array[Vector2i]:
    var found: Array[Vector2i] = []
    if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
        return found
    var first := WorldGrid.cell_to_chunk(bounds[0], bounds[1])
    var last := WorldGrid.cell_to_chunk(bounds[2] - 1, bounds[3] - 1)
    for cy in range(first.y - padding, last.y + padding + 1):
        for cx in range(first.x - padding, last.x + padding + 1):
            found.append(Vector2i(cx, cy))
    return found

static func plot_intersects_bounds(plot: Dictionary, bounds: Array[int]) -> bool:
    var x := int(plot["cell_x"])
    var y := int(plot["cell_y"])
    return x < bounds[2] and y < bounds[3] and x + int(plot["width_cells"]) > bounds[0] and y + int(plot["height_cells"]) > bounds[1]
