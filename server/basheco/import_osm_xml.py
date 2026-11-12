"""Offline OSM XML -> camera-streamed BASHECO geography chunks.

Usage:
  python -m basheco.import_osm_xml --input /data/ufa.osm --location ufa \
      --origin-lon 55.95 --origin-lat 54.73 --output /tmp/ufa_chunks \
      --source-url https://www.openstreetmap.org/

Requires an explicitly obtained .osm extract. Does not query public OSM APIs.
Input XML is trusted as OSM data, never as commands. This parser handles ways,
not multipolygon relations; a future PBF/relation importer is required for full
city-scale coverage. ODbL attribution is mandatory.
"""
from __future__ import annotations

import argparse
import json
import math
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

RADIUS = 6378137.0
CHUNK_M = 256


def classify(tags: dict[str, str]) -> str | None:
    if tags.get("building") not in (None, "no"):
        return "building"
    if tags.get("highway"):
        return "road"
    if tags.get("natural") == "water" or tags.get("waterway") in {"river", "stream", "canal"} or tags.get("landuse") in {"reservoir", "basin"}:
        return "water"
    if tags.get("landuse") == "forest" or tags.get("natural") == "wood":
        return "forest"
    if tags.get("landuse") in {"farmland", "farmyard", "meadow", "orchard", "vineyard"}:
        return "farmland"
    return None


def project(lon: float, lat: float, origin_lon: float, origin_lat: float) -> list[float]:
    return [
        round(RADIUS * math.radians(lon - origin_lon) * math.cos(math.radians(origin_lat)), 2),
        round(-RADIUS * math.radians(lat - origin_lat), 2),
    ]


def convert(input_file: Path, output_dir: Path, location: str, origin_lon: float,
            origin_lat: float, source_url: str, downloaded_utc: str) -> dict:
    if not input_file.is_file():
        raise FileNotFoundError(input_file)
    if not location.replace("_", "").isalnum() or not location.isascii():
        raise ValueError("Invalid location identifier")
    if not (-180 <= origin_lon <= 180 and -90 <= origin_lat <= 90):
        raise ValueError("Invalid origin")
    if not source_url.startswith(("https://", "http://")):
        raise ValueError("A source URL is required")
    # Standard OSM XML nodes precede ways. This is intended for bounded
    # local extracts, not whole-republic planet-scale data.
    nodes: dict[str, tuple[float, float]] = {}
    ways: list[tuple[str, list[str], dict[str, str]]] = []
    for _, elem in ET.iterparse(input_file, events=("end",)):
        if elem.tag == "node":
            if "lat" in elem.attrib and "lon" in elem.attrib:
                nodes[elem.attrib["id"]] = (float(elem.attrib["lon"]), float(elem.attrib["lat"]))
            elem.clear()
        elif elem.tag == "way":
            refs = [n.attrib["ref"] for n in elem.findall("nd") if "ref" in n.attrib]
            tags = {t.attrib["k"]: t.attrib["v"] for t in elem.findall("tag") if "k" in t.attrib and "v" in t.attrib}
            if classify(tags) and len(refs) >= 2:
                ways.append((elem.attrib.get("id", ""), refs, tags))
            elem.clear()
    chunks: dict[tuple[int, int], list[dict]] = defaultdict(list)
    bounds = [math.inf, math.inf, -math.inf, -math.inf]
    counts: dict[str, int] = defaultdict(int)
    for way_id, refs, tags in ways:
        if any(ref not in nodes for ref in refs):
            continue
        kind = classify(tags)
        coords = [project(*nodes[ref], origin_lon, origin_lat) for ref in refs]
        xs = [p[0] for p in coords]
        ys = [p[1] for p in coords]
        xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
        bounds = [min(bounds[0], xmin), min(bounds[1], ymin), max(bounds[2], xmax), max(bounds[3], ymax)]
        counts[kind] += 1
        feature = {"id": int(way_id), "osm_id": "way/" + way_id, "kind": kind, "points_m": coords}
        x0, x1 = math.floor(xmin / CHUNK_M), math.floor(xmax / CHUNK_M)
        y0, y1 = math.floor(ymin / CHUNK_M), math.floor(ymax / CHUNK_M)
        # Do not silently truncate huge ways. Caller must split the extract
        # or use a more advanced polygon clipping pipeline.
        if (x1 - x0 + 1) * (y1 - y0 + 1) > 256:
            raise ValueError(f"Way {way_id} crosses too many chunks; split or clip it")
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                chunks[x, y].append(feature)
    output_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for (x, y), items in sorted(chunks.items()):
        name = f"chunk_{x}_{y}.json"
        (output_dir / name).write_text(json.dumps({"features": items}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        entries.append({"x": x, "y": y, "path": f"res://data/spatial/{location}/{name}", "count": len(items)})
    manifest = {
        "location_id": location, "status": "offline_osm_extract_not_verified_full_coverage",
        "source_url": source_url, "source_downloaded_utc": downloaded_utc,
        "attribution": "© OpenStreetMap contributors", "license": "ODbL 1.0",
        "projection": "local_equirectangular_metres",
        "origin_lon": origin_lon, "origin_lat": origin_lat,
        "spatial_chunk_metres": CHUNK_M, "spatial_chunks": entries,
        "bounds_m": bounds if entries else [0, 0, 0, 0],
        "unique_feature_count": sum(counts.values()), "feature_counts": dict(counts),
        "limitations": "Ways only; OSM multipolygon relations not yet imported",
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--location", required=True)
    p.add_argument("--origin-lon", type=float, required=True)
    p.add_argument("--origin-lat", type=float, required=True)
    p.add_argument("--source-url", required=True)
    p.add_argument("--downloaded-utc", default=datetime.now(timezone.utc).isoformat())
    a = p.parse_args()
    print(json.dumps(convert(a.input, a.output, a.location, a.origin_lon, a.origin_lat, a.source_url, a.downloaded_utc), ensure_ascii=False))


if __name__ == "__main__":
    main()
