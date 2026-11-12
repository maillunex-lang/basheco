extends RefCounted
## The ONE world grid of BASHECO, shared with the server (server/basheco/world_grid.py).
## Source coordinates: WGS84 (EPSG:4326). World metres: EPSG:32640 (UTM zone 40N).
## cell_x = floor(E / 6), cell_y = floor(-N / 6), chunk = floor(cell / 64).
## A settlement never has its own origin. The server stays authoritative: the
## client only mirrors the formulas and is checked against server control points.
##
## Precision: GDScript int/float scalars are 64-bit, Vector2 is 32-bit. Global
## values therefore live in int/float scalars or Vector2i; Vector2 is used only
## for small offsets relative to a nearby anchor cell.
const GRID_VERSION := "basheco-grid/1"
const CRS := "EPSG:32640"
const SOURCE_CRS := "EPSG:4326"
const CELL_METRES := 6
const CHUNK_CELLS := 64
const CHUNK_METRES := 384
const ORIGIN_EASTING := 0
const ORIGIN_NORTHING := 0

# WGS84 ellipsoid and UTM zone 40N (central meridian 57 E), Krueger series to n^3.
const _A := 6378137.0
const _F := 1.0 / 298.257223563
const _K0 := 0.9996
const _LON0 := 57.0
const _FALSE_EASTING := 500000.0

static func metres_to_cell(easting: float, northing: float) -> Vector2i:
    return Vector2i(floori((easting - ORIGIN_EASTING) / CELL_METRES),
        floori((ORIGIN_NORTHING - northing) / CELL_METRES))

## Continuous cell coordinates (64-bit) of a projected point: [cell_x, cell_y].
static func metres_to_cell_f(easting: float, northing: float) -> PackedFloat64Array:
    return PackedFloat64Array([(easting - ORIGIN_EASTING) / CELL_METRES,
        (ORIGIN_NORTHING - northing) / CELL_METRES])

static func cell_to_metres(cell_x: float, cell_y: float) -> PackedFloat64Array:
    return PackedFloat64Array([ORIGIN_EASTING + cell_x * CELL_METRES,
        ORIGIN_NORTHING - cell_y * CELL_METRES])

static func floor_div(value: int, divisor: int) -> int:
    var quotient := value / divisor
    if (value % divisor != 0) and ((value < 0) != (divisor < 0)):
        quotient -= 1
    return quotient

static func cell_to_chunk(cell_x: int, cell_y: int) -> Vector2i:
    return Vector2i(floor_div(cell_x, CHUNK_CELLS), floor_div(cell_y, CHUNK_CELLS))

static func chunk_origin_cell(chunk: Vector2i) -> Vector2i:
    return Vector2i(chunk.x * CHUNK_CELLS, chunk.y * CHUNK_CELLS)

static func _constants() -> Array[float]:
    var n := _F / (2.0 - _F)
    var big_a := _A / (1.0 + n) * (1.0 + n * n / 4.0 + pow(n, 4) / 64.0)
    return [big_a, n, sqrt(_F * (2.0 - _F))]

## WGS84 degrees -> EPSG:32640 metres [easting, northing].
static func lonlat_to_metres(lon: float, lat: float) -> PackedFloat64Array:
    var c := _constants()
    var n := c[1]
    var e := c[2]
    var alpha: Array[float] = [n / 2.0 - 2.0 * n * n / 3.0 + 5.0 * pow(n, 3) / 16.0,
        13.0 * n * n / 48.0 - 3.0 * pow(n, 3) / 5.0, 61.0 * pow(n, 3) / 240.0]
    var phi := deg_to_rad(lat)
    var lam := deg_to_rad(lon - _LON0)
    var t := sinh(atanh(sin(phi)) - e * atanh(e * sin(phi)))
    var xi := atan(t / cos(lam))
    var eta := atanh(sin(lam) / sqrt(1.0 + t * t))
    var east := eta
    var north := xi
    for j in range(3):
        var k := 2.0 * float(j + 1)
        east += alpha[j] * cos(k * xi) * sinh(k * eta)
        north += alpha[j] * sin(k * xi) * cosh(k * eta)
    return PackedFloat64Array([_FALSE_EASTING + _K0 * c[0] * east, _K0 * c[0] * north])

## EPSG:32640 metres -> WGS84 degrees [lon, lat].
static func metres_to_lonlat(easting: float, northing: float) -> PackedFloat64Array:
    var c := _constants()
    var n := c[1]
    var beta: Array[float] = [n / 2.0 - 2.0 * n * n / 3.0 + 37.0 * pow(n, 3) / 96.0,
        n * n / 48.0 + pow(n, 3) / 15.0, 17.0 * pow(n, 3) / 480.0]
    var delta: Array[float] = [2.0 * n - 2.0 * n * n / 3.0 - 2.0 * pow(n, 3),
        7.0 * n * n / 3.0 - 8.0 * pow(n, 3) / 5.0, 56.0 * pow(n, 3) / 15.0]
    var xi := northing / (_K0 * c[0])
    var eta := (easting - _FALSE_EASTING) / (_K0 * c[0])
    var xi1 := xi
    var eta1 := eta
    for j in range(3):
        var k := 2.0 * float(j + 1)
        xi1 -= beta[j] * sin(k * xi) * cosh(k * eta)
        eta1 -= beta[j] * cos(k * xi) * sinh(k * eta)
    var chi := asin(sin(xi1) / cosh(eta1))
    var lat := chi
    for j in range(3):
        lat += delta[j] * sin(2.0 * float(j + 1) * chi)
    return PackedFloat64Array([_LON0 + rad_to_deg(atan(sinh(eta1) / cos(xi1))), rad_to_deg(lat)])

static func lonlat_to_cell(lon: float, lat: float) -> Vector2i:
    var metres := lonlat_to_metres(lon, lat)
    return metres_to_cell(metres[0], metres[1])

## True when a server/atlas grid description is exactly this client's grid.
static func matches(spec: Dictionary) -> bool:
    return str(spec.get("grid_version", "")) == GRID_VERSION and str(spec.get("crs", "")) == CRS \
        and int(spec.get("cell_metres", 0)) == CELL_METRES and int(spec.get("chunk_cells", 0)) == CHUNK_CELLS \
        and int(spec.get("origin_easting", -1)) == ORIGIN_EASTING and int(spec.get("origin_northing", -1)) == ORIGIN_NORTHING
