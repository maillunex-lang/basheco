"""Offline, read-only boundary audit of generated location footprints.

The OSM administrative boundary is NOT a building-permission or land-cover map.
A passing boundary check never certifies that a cell is dry, buildable, or owned.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from basheco.geo_registry import point_in_rings, ring_points
from basheco.location_generator import DEFAULT_ROOT, build
from basheco.land_constraints import assess_cells, footprint_cells
from basheco.world_grid import CELL_METRES, cell_to_metre_corner


def audit(root: Path = DEFAULT_ROOT) -> dict:
    bundle = build(root)
    municipalities = {m["id"]: m for m in json.loads(
        (root / "municipalities.json").read_text(encoding="utf-8"))["municipalities"]}
    boundary = json.loads((root / "boundaries" / "ways_detail.json").read_text(encoding="utf-8"))
    ways = boundary["ways"]
    if boundary["dataset_version"] != json.loads(
            (root / "dataset_version.json").read_text(encoding="utf-8"))["dataset_version"]:
        raise ValueError("Boundary dataset version mismatch")
    polygons = {}
    results = []
    for selection, location in zip(bundle["selection"], bundle["locations"]):
        mid = selection["municipality_id"]
        if mid not in polygons:
            polygons[mid] = [ring_points(r, ways) for r in municipalities[mid]["rings"]]
        rings = polygons[mid]
        problems = []
        checked = 0
        for obj in location["objects"]:
            x, y = obj["cell"]
            w, h = obj["size"]
            # Full rectangle corners and centre; edge crossings between these
            # samples remain unresolved, so this is screening, not certification.
            east, north = cell_to_metre_corner(x, y)
            for px, py in ((east, north), (east + w * CELL_METRES, north),
                           (east, north - h * CELL_METRES),
                           (east + w * CELL_METRES, north - h * CELL_METRES),
                           (east + w * CELL_METRES / 2, north - h * CELL_METRES / 2)):
                checked += 1
                if not point_in_rings((px, py), rings):
                    problems.append({"kind": obj["kind"], "cell": [x, y],
                                     "sample_m": [px, py]})
                    break
        land = assess_cells(footprint_cells(location), None)
        results.append({"settlement_id": selection["settlement_id"],
                        "municipality_id": mid,
                        "sampled_points": checked,
                        "boundary_sample_pass": not problems,
                        "boundary_conflicts": problems,
                        "water_verified": False, "terrain_verified": False,
                        "land_rights_verified": False,
                        "land_constraints": land,
                        "safe_to_publish": not problems and land["safe_to_build"]})
    counts = Counter("boundary_pass" if r["boundary_sample_pass"] else "boundary_conflict"
                     for r in results)
    return {"schema": "basheco.geography_audit/1",
            "dataset_version": boundary["dataset_version"],
            "candidate_count": len(results),
            "boundary_sample_pass": counts["boundary_pass"],
            "boundary_conflict": counts["boundary_conflict"],
            "safe_to_publish": sum(r["safe_to_publish"] for r in results),
            "limitations": ["Simplified OSM administrative boundaries (40 m tolerance)",
                            "Five sample points per object do not prove full footprint containment",
                            "No verified water, terrain, protected land, or parcel rights layers",
                            "No land constraint evidence is shipped; all cells are unknown",
                            "Existing candidate geometry is not modified"],
            "locations": results}


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit()
    data = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data, encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("candidate_count", "boundary_sample_pass",
          "boundary_conflict", "safe_to_publish")}, ensure_ascii=False))


if __name__ == "__main__":
    main()