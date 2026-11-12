"""Export the versioned administrative registry to a compact Godot navigation catalog.

Run from repository root:
    python tools/export_navigation.py
No network, no database and no generated coordinates.\nThe output is committed by the navigation-catalog workflow.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "server/geodata/admin"
TARGET = ROOT / "client/data/admin_navigation.json"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def export() -> dict:
    version = read(SOURCE / "dataset_version.json")
    municipalities = read(SOURCE / "municipalities.json")["municipalities"]
    districts = []
    seen = set()
    for municipality in sorted(municipalities, key=lambda m: (m["name"].casefold(), m["id"])):
        mid = municipality["id"]
        source = read(SOURCE / "settlements" / f"{mid}.json")
        locations = []
        for settlement in source["settlements"]:
            sid = settlement["id"]
            if sid in seen:
                raise ValueError(f"Duplicate settlement id: {sid}")
            seen.add(sid)
            status = settlement.get("coordinate_status", "")
            cell = settlement.get("world_cell")
            verified = status == "inside_municipality" and isinstance(cell, list) and len(cell) == 2
            locations.append({
                "id": sid, "name": settlement["name"], "type": settlement["type"],
                "unit": settlement.get("unit_name", ""),
                "cell": cell if verified else None,
                "coordinate_status": status,
            })
        locations.sort(key=lambda s: (s["name"].casefold(), s["type"], s["id"]))
        districts.append({"id": mid, "name": municipality["name"], "locations": locations})
    expected = version["counts"]
    if len(districts) != expected["municipalities"] or len(seen) != expected["settlements"]:
        raise ValueError(f"Catalog mismatch: {len(districts)} municipalities, {len(seen)} settlements")
    return {"schema": "basheco.navigation/1", "dataset_version": version["dataset_version"], "districts": districts}


if __name__ == "__main__":
    catalog = export()
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Exported {len(catalog['districts'])} municipalities and "
          f"{sum(len(d['locations']) for d in catalog['districts'])} settlements to {TARGET}")
