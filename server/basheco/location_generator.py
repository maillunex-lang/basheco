"""Offline, deterministic stage-1.3 candidate generation. No DB mutations.

A municipality has at most five candidates, chosen by sourced population.
Unpopulated records are NOT assumed to be large. The historical Mikhailovka
pilot is a separately approved exception to the ranking, still within the cap.
Candidate locations are NOT published to the client until separately approved.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from basheco.world_grid import CELL_METRES, CHUNK_CELLS, cell_to_chunk

SCHEMA = "basheco.location_candidates/1"
VERSION = 1
LIMIT = 5
PILOT = "S80652440101"
DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "geodata" / "admin"
FOOTPRINTS = ((1, 1), (1, 2), (2, 2), (3, 2), (3, 3))


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _population(record: dict) -> int | None:
    data = record.get("population")
    if not isinstance(data, dict):
        return None
    value = data.get("value")
    return value if type(value) is int and value > 0 and data.get("source") else None


def choose_settlements(root: Path = DEFAULT_ROOT) -> list[dict]:
    result: list[dict] = []
    municipalities = _read(root / "municipalities.json")
    for municipality in municipalities["municipalities"]:
        mid = municipality["id"]
        settlements = _read(root / "settlements" / f"{mid}.json")["settlements"]
        eligible = [s for s in settlements if _population(s) is not None
                    and isinstance(s.get("world_cell"), list)
                    and len(s["world_cell"]) == 2
                    and s.get("coordinate_status") == "inside_municipality"]
        eligible.sort(key=lambda s: (-_population(s), s["id"]))
        selected = eligible[:LIMIT]
        # Preserve the already-approved Mikhailovka pilot without exceeding cap.
        pilot = next((s for s in settlements if s["id"] == PILOT), None)
        if pilot and pilot not in selected and isinstance(pilot.get("world_cell"), list):
            selected = selected[:LIMIT - 1] + [pilot]
        for s in selected:
            result.append({"municipality_id": mid, "settlement_id": s["id"],
                           "name": s["name"], "cell": s["world_cell"],
                           "population": _population(s),
                           "population_year": (s.get("population") or {}).get("year"),
                           "selection": "approved_pilot" if s["id"] == PILOT else "population"})
    return result


def _seed(settlement_id: str) -> int:
    return int.from_bytes(hashlib.sha256(f"basheco:gen:{VERSION}:{settlement_id}".encode()).digest()[:8], "big")


def generate(record: dict) -> dict:
    """Generate non-overlapping footprints, roads and houses in global grid cells."""
    cx, cy = record["cell"]
    seed = _seed(record["settlement_id"])
    occupied: set[tuple[int, int]] = set()
    objects = []
    def put(kind: str, x: int, y: int, w: int = 1, h: int = 1) -> None:
        footprint = {(a, b) for a in range(x, x + w) for b in range(y, y + h)}
        if footprint & occupied:
            raise ValueError(f"Overlapping {kind} at {(x, y)}")
        occupied.update(footprint)
        obj = {"kind": kind, "cell": [x, y], "size": [w, h]}
        if kind == "house":
            obj["residents_hint"] = w * h * 4  # provisional, NOT official population
        objects.append(obj)
    # Roads form a connected cross, one cell wide. Center intersection once.
    for dy in range(-12, 13):
        put("road", cx, cy + dy)
    for dx in range(-18, 19):
        if dx:
            put("road", cx + dx, cy)
    for row in range(3):
        for col in range(5):
            x, y = cx - 17 + col * 7, cy - 10 + row * 7
            w, h = FOOTPRINTS[(seed + row * 37 + col * 71) % len(FOOTPRINTS)]
            put("house", x, y, w, h)
    chunks = sorted({cell_to_chunk(x, y) for x, y in occupied})
    return {"schema": "basheco.generated_location/1", "version": VERSION,
            "settlement_id": record["settlement_id"], "seed": seed,
            "cell_size_m": CELL_METRES, "chunk_size_cells": CHUNK_CELLS,
            "objects": objects, "chunks": [list(chunk) for chunk in chunks]}


def build(root: Path = DEFAULT_ROOT) -> dict:
    selected = choose_settlements(root)
    generated = [generate(record) for record in selected]
    return {"schema": SCHEMA, "generator_version": VERSION, "max_per_municipality": LIMIT,
            "selection": selected, "locations": generated,
            "published_settlement_ids": [PILOT]}


def main() -> None:
    data = build()
    output = Path(__file__).resolve().parents[2] / "build" / "location_candidates.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"GENERATOR_OK candidates={len(data['locations'])} published={len(data['published_settlement_ids'])} output={output}")


if __name__ == "__main__":
    main()