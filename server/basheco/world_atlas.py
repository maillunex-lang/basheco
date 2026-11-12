"""Build the single BASHECO world atlas in EPSG:32640 from WGS84 source snapshots.

Usage:
  python -m basheco.world_atlas [GEODATA_DIR] [OUTPUT_DIR]
Defaults: server/geodata -> client/data/world

Pipeline: EPSG:4326 lon/lat (untouched OSM nodes) -> pyproj -> EPSG:32640 metres
-> global 6 m cells -> global 64x64-cell chunks. There is exactly one origin for
every settlement. Output is deterministic, so a rebuild must reproduce the
committed files byte for byte (covered by tests).

Geometry rules (nothing is generalised into grid-aligned shapes):
 * lines (roads, waterways) keep every source vertex and are cut exactly on chunk
   borders; both neighbours receive the identical cut point, so there is no gap;
 * polygons are stored once, in the chunk of their bounding-box centre. The client
   keeps a one-chunk ring loaded, which covers every polygon classified "local";
 * polygons reaching further than that ring go to large.json (always in memory).
Each exported piece has a globally unique uid: no object is duplicated.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from basheco.world_grid import (
    CELL_METRES, CHUNK_CELLS, CHUNK_METRES, CRS, GRID_VERSION, SOURCE_CRS,
    chunk_bounds_metres, grid_spec, metres_to_cell, metres_to_chunk, cell_to_chunk,
)
from basheco.world_projection import lonlat_to_metres, metres_to_lonlat

ATLAS_SCHEMA = "basheco.world_atlas/2"
CHUNK_SCHEMA = "basheco.world_chunk/2"
NAVIGATION_MARGIN_CHUNKS = 8
MAX_LARGE_FEATURES = 2000
# Synthetic projection probes across the republic's longitude span. They are test
# coordinates for server/client parity, NOT places and never rendered.
PROJECTION_PROBES = (
    ("probe-central-meridian", 57.0, 54.0), ("probe-west-of-zone", 53.2, 52.0),
    ("probe-north-east", 59.9, 56.5), ("probe-south", 58.3, 51.6),
    ("probe-zone-west-edge", 54.0, 55.5),
)


def _round(value: float) -> float:
    return round(value, 2)


def project_points(coordinates) -> list[tuple[float, float]]:
    points = []
    for lon, lat in coordinates:
        east, north = lonlat_to_metres(float(lon), float(lat))
        points.append((_round(east), _round(north)))
    return points


def split_line(points: list[tuple[float, float]]) -> list[tuple[tuple[int, int], list[tuple[float, float]]]]:
    """Cut a polyline on chunk borders. Returns [(chunk, points)], in line order."""
    pieces: list[tuple[tuple[int, int], list[tuple[float, float]]]] = []
    for a, b in zip(points, points[1:]):
        if a == b:
            continue
        cuts = {0.0, 1.0}
        for axis in (0, 1):
            low, high = sorted((a[axis], b[axis]))
            if low == high:
                continue
            k = math.floor(low / CHUNK_METRES) + 1
            while k * CHUNK_METRES < high:
                cuts.add((k * CHUNK_METRES - a[axis]) / (b[axis] - a[axis]))
                k += 1
        ordered = sorted(cuts)
        stops = [a]
        for t in ordered[1:-1]:
            stops.append((_round(a[0] + (b[0] - a[0]) * t), _round(a[1] + (b[1] - a[1]) * t)))
        stops.append(b)
        for p, q in zip(stops, stops[1:]):
            if p == q:
                continue
            chunk = metres_to_chunk((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
            if pieces and pieces[-1][0] == chunk and pieces[-1][1][-1] == p:
                pieces[-1][1].append(q)
            else:
                pieces.append((chunk, [p, q]))
    return pieces


def polygon_home(points: list[tuple[float, float]]) -> tuple[tuple[int, int], bool]:
    """Home chunk and whether the polygon stays inside the home chunk's 3x3 ring."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    home = metres_to_chunk((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    east_min, north_min, east_max, north_max = chunk_bounds_metres(*home)
    local = (min(xs) >= east_min - CHUNK_METRES and max(xs) <= east_max + CHUNK_METRES
             and min(ys) >= north_min - CHUNK_METRES and max(ys) <= north_max + CHUNK_METRES)
    return home, local


def _control_point(name: str, lon: float, lat: float, kind: str) -> dict:
    east, north = lonlat_to_metres(lon, lat)
    back_lon, back_lat = metres_to_lonlat(east, north)
    cell = metres_to_cell(east, north)
    return {"name": name, "kind": kind, "lon": lon, "lat": lat,
            "easting": east, "northing": north,
            "inverse_lon": back_lon, "inverse_lat": back_lat,
            "cell": list(cell), "chunk": list(cell_to_chunk(*cell))}


def _dump(path: Path, value, compact: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(value, ensure_ascii=False, indent=1)
    path.write_text(text + "\n", encoding="utf-8")


def build(geodata_dir: Path, output_dir: Path) -> dict:
    catalog = json.loads((geodata_dir / "settlements.json").read_text(encoding="utf-8"))
    chunks: dict[tuple[int, int], list[dict]] = {}
    large: list[dict] = []
    uids: set[str] = set()
    sources_out = []
    settlements_out = []
    boundaries_out = []
    elevation_out = []
    control_points = [_control_point(n, lon, lat, "projection_probe") for n, lon, lat in PROJECTION_PROBES]
    totals: dict[str, int] = {}
    extent = [math.inf, math.inf, -math.inf, -math.inf]

    def grow(points) -> None:
        for east, north in points:
            extent[0] = min(extent[0], east); extent[1] = min(extent[1], north)
            extent[2] = max(extent[2], east); extent[3] = max(extent[3], north)

    def emit(target: list[dict], feature: dict) -> None:
        if feature["uid"] in uids:
            raise ValueError("Duplicate geographic object: " + feature["uid"])
        uids.add(feature["uid"])
        target.append(feature)

    seen_sources: set[str] = set()
    for settlement in catalog["settlements"]:
        location_id = settlement["id"]
        coverage = []
        for source_id in settlement["sources"]:
            if source_id in seen_sources:
                raise ValueError("Source listed twice: " + source_id)
            seen_sources.add(source_id)
            snapshot = json.loads((geodata_dir / "sources" / f"{source_id}.json").read_text(encoding="utf-8"))
            if snapshot.get("crs") != SOURCE_CRS or snapshot.get("source_id") != source_id:
                raise ValueError("Source snapshot must be EPSG:4326: " + source_id)
            if snapshot.get("location_id") != location_id:
                raise ValueError("Source/location mismatch: " + source_id)
            west, south, east, north = snapshot["bbox_lonlat"]
            corners = project_points([(west, south), (west, north), (east, north), (east, south)])
            coverage.append(snapshot["bbox_lonlat"])
            counts: dict[str, int] = {}
            for item in snapshot["features"]:
                points = project_points(item["coordinates"])
                grow(points)
                base = {"osm_id": item["osm_id"], "kind": item["kind"], "subtype": item["subtype"],
                        "source": source_id, "location_id": location_id}
                if item.get("name"):
                    base["name"] = item["name"]
                uid_base = f"{source_id}:{item['osm_id']}"
                counts[item["kind"]] = counts.get(item["kind"], 0) + 1
                if item["geometry"] == "line":
                    for index, (chunk, piece) in enumerate(split_line(points)):
                        emit(chunks.setdefault(chunk, []), {
                            "uid": f"{uid_base}#{index}", **base, "geom": "line",
                            "points": [list(p) for p in piece]})
                else:
                    home, local = polygon_home(points)
                    feature = {"uid": uid_base, **base, "geom": "polygon",
                               "points": [list(p) for p in points]}
                    if local:
                        emit(chunks.setdefault(home, []), feature)
                    else:
                        emit(large, feature)
            for kind, count in counts.items():
                totals[kind] = totals.get(kind, 0) + count
            sources_out.append({
                "id": source_id, "location_id": location_id, "source": snapshot["source"],
                "source_url": snapshot["source_url"], "downloaded_utc": snapshot["downloaded_utc"],
                "license": snapshot["license"], "attribution": snapshot["attribution"],
                "bbox_lonlat": snapshot["bbox_lonlat"],
                "coverage_ring_m": [list(p) for p in corners + corners[:1]],
                "feature_counts": dict(sorted(counts.items())),
                "skipped": snapshot.get("skipped", {}),
                "coverage": snapshot.get("coverage"), "limitations": snapshot.get("limitations"),
            })
        if not coverage:
            raise ValueError("Settlement without sourced coverage: " + location_id)
        focus_lon = (min(c[0] for c in coverage) + max(c[2] for c in coverage)) / 2
        focus_lat = (min(c[1] for c in coverage) + max(c[3] for c in coverage)) / 2
        focus = _control_point(f"{location_id}-focus", focus_lon, focus_lat, "settlement_focus")
        control_points.append(focus)
        for index, (lon, lat) in enumerate(((coverage[0][0], coverage[0][1]), (coverage[0][2], coverage[0][3]))):
            control_points.append(_control_point(f"{location_id}-bbox-{index}", lon, lat, "source_bbox_corner"))
        entry = {"id": location_id, "name": settlement["name"], "kind": settlement["kind"],
                 "focus_lonlat": [focus_lon, focus_lat],
                 "focus_m": [focus["easting"], focus["northing"]],
                 "focus_cell": focus["cell"], "focus_chunk": focus["chunk"],
                 "focus_definition": "centre of sourced OSM extract coverage, not an official centre",
                 "sources": settlement["sources"]}
        if settlement.get("boundary"):
            boundary = json.loads((geodata_dir / settlement["boundary"]).read_text(encoding="utf-8"))
            if boundary.get("location_id") != location_id or boundary["geometry"]["type"] != "MultiPolygon":
                raise ValueError("Invalid boundary: " + location_id)
            rings = []
            for polygon in boundary["geometry"]["coordinates"]:
                for ring in polygon:
                    projected = project_points(ring)
                    grow(projected)
                    rings.append([list(p) for p in projected])
            boundaries_out.append({
                "location_id": location_id, "source": boundary["source"],
                "source_url": boundary["source_url"], "license": boundary["license"],
                "retrieved_utc": boundary["retrieved_utc"],
                "simplification_tolerance_degrees": boundary.get("simplification_tolerance_degrees"),
                "rings_m": rings})
            entry["boundary_source_url"] = boundary["source_url"]
        if settlement.get("elevation"):
            grid = json.loads((geodata_dir / settlement["elevation"]).read_text(encoding="utf-8"))
            width, height = int(grid["width"]), int(grid["height"])
            west, south, east, north = grid["bbox_lonlat"]
            if grid.get("location_id") != location_id or len(grid["elevations_m"]) != width * height:
                raise ValueError("Invalid elevation grid: " + location_id)
            samples = []
            for y in range(height):
                for x in range(width):
                    lon = west + (east - west) * x / (width - 1)
                    lat = south + (north - south) * y / (height - 1)
                    e, n = project_points([(lon, lat)])[0]
                    samples.append([e, n, float(grid["elevations_m"][y * width + x])])
            elevation_out.append({
                "location_id": location_id, "dataset": grid["dataset"], "provider": grid["provider"],
                "source_url": grid["source_url"], "downloaded_utc": grid["downloaded_utc"],
                "note": grid.get("note"), "width": width, "height": height, "samples_m": samples})
        settlements_out.append(entry)

    if len(large) > MAX_LARGE_FEATURES:
        raise ValueError("Too many large polygons: a tiling pipeline is required before import")
    chunk_dir = output_dir / "chunks"
    if chunk_dir.exists():
        for stale in chunk_dir.glob("chunk_*.json"):
            stale.unlink()
    index = []
    for (cx, cy), features in sorted(chunks.items()):
        features.sort(key=lambda f: f["uid"])
        _dump(chunk_dir / f"chunk_{cx}_{cy}.json", {
            "schema": CHUNK_SCHEMA, "grid_version": GRID_VERSION, "crs": CRS,
            "chunk": [cx, cy], "bounds_m": list(chunk_bounds_metres(cx, cy)),
            "features": features})
        index.append([cx, cy, len(features)])
    large.sort(key=lambda f: f["uid"])
    _dump(output_dir / "large.json", {"schema": CHUNK_SCHEMA, "grid_version": GRID_VERSION,
                                      "crs": CRS, "features": large})
    _dump(output_dir / "boundaries.json", {"schema": "basheco.world_boundaries/2", "crs": CRS,
                                           "grid_version": GRID_VERSION, "boundaries": boundaries_out})
    _dump(output_dir / "elevation.json", {"schema": "basheco.world_elevation/2", "crs": CRS,
                                          "grid_version": GRID_VERSION, "grids": elevation_out})
    _dump(output_dir / "control_points.json", {
        "schema": "basheco.control_points/1", "crs": CRS, "source_crs": SOURCE_CRS,
        "grid_version": GRID_VERSION, "computed_with": "pyproj (PROJ) EPSG:4326 -> EPSG:32640",
        "points": control_points}, compact=False)
    west_cell, north_cell = metres_to_cell(extent[0], extent[3])
    east_cell, south_cell = metres_to_cell(extent[2], extent[1])
    margin = NAVIGATION_MARGIN_CHUNKS * CHUNK_CELLS
    manifest = {
        "schema": ATLAS_SCHEMA, **grid_spec(),
        "units": "points are [easting, northing] metres, rounded to 0.01 m",
        "license": "ODbL 1.0", "attribution": "© OpenStreetMap contributors",
        "coverage": "partial",
        "coverage_note": "Real geography is imported only inside each source bbox. Everything else in the republic is empty until its sources are imported; emptiness is missing data, not open land.",
        "chunk_path_template": "res://data/world/chunks/chunk_{x}_{y}.json",
        "navigation_bounds_cells": [west_cell - margin, north_cell - margin,
                                    east_cell + margin, south_cell + margin],
        "feature_counts": dict(sorted(totals.items())),
        "source_object_count": sum(totals.values()),
        "exported_piece_count": len(uids), "large_feature_count": len(large),
        "settlements": settlements_out, "sources": sources_out, "chunks": index,
    }
    _dump(output_dir / "manifest.json", manifest, compact=False)
    return manifest


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    geodata = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "server" / "geodata"
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else root / "client" / "data" / "world"
    manifest = build(geodata, output)
    print(json.dumps({"chunks": len(manifest["chunks"]), "pieces": manifest["exported_piece_count"],
                      "objects": manifest["source_object_count"], "large": manifest["large_feature_count"],
                      "kinds": manifest["feature_counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
