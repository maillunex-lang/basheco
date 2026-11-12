"""Normalise a bounded OSM XML extract into a WGS84 source snapshot.

The snapshot is the reproducible input of the world atlas (see world_atlas.py).
It keeps real OSM identifiers, object types and untouched node coordinates and
drops contributor metadata (user names, uids, changesets). Nothing is invented:
objects that cannot be assembled from the extract are counted as skipped.

Usage:
  python -m basheco.osm_source INPUT.osm SOURCE_ID LOCATION_ID SOURCE_URL DOWNLOADED_UTC OUTPUT.json
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SCHEMA = "basheco.osm_source/1"
KINDS = ("road", "building", "water", "forest", "farmland")
_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")


def classify(tags: dict[str, str]) -> tuple[str, str] | None:
    """Return (kind, subtype) taken literally from OSM tags, or None."""
    if tags.get("building") not in (None, "no"):
        return "building", tags["building"]
    if tags.get("highway"):
        return "road", tags["highway"]
    if tags.get("waterway") in {"river", "stream", "canal", "drain", "ditch"}:
        return "water", tags["waterway"]
    if tags.get("natural") == "water":
        return "water", tags.get("water", "water")
    if tags.get("landuse") in {"reservoir", "basin"}:
        return "water", tags["landuse"]
    if tags.get("landuse") == "forest" or tags.get("natural") == "wood":
        return "forest", tags.get("landuse") or tags["natural"]
    if tags.get("landuse") in {"farmland", "farmyard", "meadow", "orchard", "vineyard"}:
        return "farmland", tags["landuse"]
    return None


def _assemble_rings(parts: list[list[str]]) -> list[list[str]] | None:
    """Join outer member ways end-to-end into closed node rings; None if impossible."""
    remaining = [list(p) for p in parts if len(p) >= 2]
    rings = []
    while remaining:
        ring = remaining.pop(0)
        while ring[0] != ring[-1]:
            for index, part in enumerate(remaining):
                if part[0] == ring[-1]:
                    ring.extend(part[1:])
                elif part[-1] == ring[-1]:
                    ring.extend(reversed(part[:-1]))
                else:
                    continue
                remaining.pop(index)
                break
            else:
                return None
        if len(ring) < 4:
            return None
        rings.append(ring)
    return rings


def normalise(xml_file: Path, source_id: str, location_id: str, source_url: str,
              downloaded_utc: str) -> dict:
    for value in (source_id, location_id):
        if not _ID.fullmatch(value):
            raise ValueError("Invalid identifier")
    if not source_url.startswith("https://"):
        raise ValueError("A verifiable https source URL is required")
    if not downloaded_utc:
        raise ValueError("Download time is required")
    root = ET.parse(xml_file).getroot()
    bounds = root.find("bounds")
    if bounds is None:
        raise ValueError("OSM bounds missing: extract coverage would be unknown")
    bbox = [float(bounds.get(k)) for k in ("minlon", "minlat", "maxlon", "maxlat")]
    if not (-180 <= bbox[0] < bbox[2] <= 180 and -90 <= bbox[1] < bbox[3] <= 90):
        raise ValueError("Invalid OSM bounds")
    nodes = {n.get("id"): (float(n.get("lon")), float(n.get("lat")))
             for n in root.iter("node") if n.get("lon") is not None and n.get("lat") is not None}
    ways: dict[str, tuple[list[str], dict[str, str]]] = {}
    for way in root.iter("way"):
        refs = [nd.get("ref") for nd in way.findall("nd")]
        tags = {t.get("k"): t.get("v") for t in way.findall("tag")}
        ways[way.get("id")] = (refs, tags)
    features = []
    skipped = {"incomplete_geometry": 0, "open_area": 0, "relation_not_assembled": 0}
    used_by_relation: set[str] = set()

    def add(osm_id: str, kind: str, subtype: str, tags: dict, refs: list[str]) -> None:
        if any(ref not in nodes for ref in refs):
            skipped["incomplete_geometry"] += 1
            return
        closed = len(refs) >= 4 and refs[0] == refs[-1]
        linear = kind == "road" or (kind == "water" and "waterway" in tags)
        if not linear and not closed:
            skipped["open_area"] += 1
            return
        if len(refs) < 2:
            skipped["incomplete_geometry"] += 1
            return
        feature = {"osm_id": osm_id, "kind": kind, "subtype": subtype,
                   "geometry": "line" if linear else "polygon",
                   "coordinates": [list(nodes[ref]) for ref in refs]}
        if tags.get("name"):
            feature["name"] = tags["name"]
        features.append(feature)

    for relation in root.iter("relation"):
        tags = {t.get("k"): t.get("v") for t in relation.findall("tag")}
        if tags.get("type") != "multipolygon":
            continue
        found = classify(tags)
        if found is None or found[0] == "road":
            continue
        outers = [m.get("ref") for m in relation.findall("member")
                  if m.get("type") == "way" and m.get("role") in ("outer", "")]
        if not outers or any(ref not in ways for ref in outers):
            skipped["relation_not_assembled"] += 1
            continue
        rings = _assemble_rings([ways[ref][0] for ref in outers])
        if rings is None:
            skipped["relation_not_assembled"] += 1
            continue
        used_by_relation.update(outers)
        for index, ring in enumerate(rings):
            # Inner rings (holes) are not exported yet: documented limitation.
            add(f"relation/{relation.get('id')}/outer/{index}", found[0], found[1], tags, ring)

    for way_id, (refs, tags) in ways.items():
        found = classify(tags)
        if found is None:
            continue
        if way_id in used_by_relation and found[0] != "road":
            continue
        add(f"way/{way_id}", found[0], found[1], tags, refs)

    features.sort(key=lambda f: f["osm_id"])
    counts: dict[str, int] = {}
    for feature in features:
        counts[feature["kind"]] = counts.get(feature["kind"], 0) + 1
    return {
        "schema": SCHEMA, "source_id": source_id, "location_id": location_id,
        "crs": "EPSG:4326", "axis_order": "lon,lat", "bbox_lonlat": bbox,
        "source": "OpenStreetMap", "source_url": source_url,
        "downloaded_utc": downloaded_utc, "license": "ODbL 1.0",
        "attribution": "© OpenStreetMap contributors",
        "coverage": "Only objects intersecting bbox_lonlat; ways are kept whole and may extend past it",
        "limitations": "Multipolygon holes are not exported; relations with members outside the extract are skipped",
        "feature_counts": counts, "skipped": skipped, "features": features,
    }


def write(snapshot: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n",
                      encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 7:
        raise SystemExit(__doc__)
    result = normalise(Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    write(result, Path(sys.argv[6]))
    print(json.dumps({"features": len(result["features"]), "kinds": result["feature_counts"],
                      "skipped": result["skipped"]}, ensure_ascii=False))
