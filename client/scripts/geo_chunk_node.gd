extends Node2D
## One piece of real world geography (a 64x64-cell chunk or a static layer).
## Geometry is kept in cells relative to anchor_cell and is drawn once; moving
## the camera only changes this node's transform, so nothing is re-projected per
## frame. OSM shapes are drawn as they are: never snapped to the cell grid.
const PX_PER_CELL := 28.0  # mean on-screen size of one cell at zoom 1 (isometric)
# Rendering widths in metres by OSM highway class. A drawing style, not survey data.
const ROAD_METRES := {
    "motorway": 14.0, "trunk": 14.0, "primary": 12.0, "secondary": 10.0, "tertiary": 8.0,
    "motorway_link": 8.0, "trunk_link": 8.0, "primary_link": 8.0, "secondary_link": 7.0,
    "tertiary_link": 7.0, "residential": 6.0, "unclassified": 6.0, "living_street": 6.0,
    "service": 4.0, "track": 3.0, "pedestrian": 4.0, "footway": 2.0, "path": 2.0,
    "steps": 2.0, "cycleway": 2.0, "bridleway": 2.0
}
const MINOR_ROADS := ["service", "track", "pedestrian", "footway", "path", "steps", "cycleway", "bridleway"]
const WATER_METRES := {"river": 14.0, "canal": 8.0, "stream": 3.0, "drain": 2.0, "ditch": 2.0}
var anchor_cell := Vector2i.ZERO
var features: Array = []
var draw_zoom := 1.0
var lod := 0

func configure(zoom: float, new_lod: int) -> void:
    if is_equal_approx(zoom, draw_zoom) and new_lod == lod:
        return
    draw_zoom = zoom
    lod = new_lod
    queue_redraw()

func _px(pixels: float) -> float:
    return pixels / (PX_PER_CELL * draw_zoom)

func _width(metres: float, minimum_px: float) -> float:
    return maxf(metres / 6.0, _px(minimum_px))

func _fill(feature: Dictionary, color: Color) -> void:
    # Self-intersecting OSM rings must never reach the canvas triangulator.
    if feature.get("fill_ok", false):
        draw_colored_polygon(feature["fill"], color)

func _draw() -> void:
    for feature in features:
        match str(feature["kind"]):
            "farmland":
                _fill(feature, Color("#a3ad63", 0.24))
                draw_polyline(feature["pts"], Color("#a3ad63", 0.8), _px(2.0), false)
            "forest":
                _fill(feature, Color("#36734c", 0.3))
                draw_polyline(feature["pts"], Color("#4b9164", 0.8), _px(2.0), false)
    for feature in features:
        if str(feature["kind"]) != "water":
            continue
        if str(feature["geom"]) == "polygon":
            _fill(feature, Color("#327fa8", 0.65))
            draw_polyline(feature["pts"], Color("#4a9cc7", 0.9), _px(2.0), false)
        else:
            draw_polyline(feature["pts"], Color("#4a9cc7", 0.9),
                _width(float(WATER_METRES.get(str(feature["subtype"]), 3.0)), 2.0), false)
    for casing in [true, false]:
        for feature in features:
            if str(feature["kind"]) != "road":
                continue
            var subtype := str(feature["subtype"])
            var minor := MINOR_ROADS.has(subtype)
            if lod >= 2 and minor:
                continue
            var metres := float(ROAD_METRES.get(subtype, 6.0))
            if casing:
                draw_polyline(feature["pts"], Color("#263e46", 0.95), _width(metres + 2.0, 2.2 if minor else 3.4), false)
            else:
                draw_polyline(feature["pts"], Color("#9ca6a3", 0.95), _width(metres, 1.2 if minor else 2.2), false)
    if lod <= 1:
        for feature in features:
            if str(feature["kind"]) == "building":
                _fill(feature, Color("#8fa3aa", 0.2))
                draw_polyline(feature["pts"], Color("#b6c6cb", 0.65), _px(1.0), false)
    for feature in features:
        match str(feature["kind"]):
            "contour":
                if lod <= 1:
                    draw_polyline(feature["pts"], Color("#91ae86", 0.48), _px(1.2), false)
            "boundary":
                draw_polyline(feature["pts"], Color("#e2bf72", 0.9), _px(2.0), false)
            "coverage":
                var points: PackedVector2Array = feature["pts"]
                for i in range(points.size() - 1):
                    draw_dashed_line(points[i], points[i + 1], Color("#7fb6c9", 0.55), _px(1.2), _px(9.0), false)
