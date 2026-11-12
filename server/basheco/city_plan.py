"""Deterministic versioned city planning proposal. No DB writes or publication.

This is a server-side source of truth for *candidate* cells, not player-owned
buildings. A separate approval/import step must check existing occupancy.
"""
from __future__ import annotations

import hashlib
import json

VERSION = 2
SIZE = 56
STEP = 8
FOOTPRINTS = ((1, 1), (1, 2), (2, 2), (3, 2), (3, 3))
DISTRICTS = ("center", "residential", "industrial", "park", "commercial")
BASE_RESIDENTS = {"house": 4, "apartment": 16, "highrise": 40}


def district_at(x: int, y: int) -> str:
    distance = abs(x - SIZE // 2) + abs(y - SIZE // 2)
    if distance < 16:
        return "center"
    if x > SIZE // 2 + 9 and y > SIZE // 2 + 3:
        return "industrial"
    if x < SIZE // 2 - 9 and y < SIZE // 2 - 9:
        return "park"
    if y < SIZE // 2 - 9:
        return "commercial"
    return "residential"


def land_band(x: int, y: int) -> int:
    """Relative desirability, not an actual currency valuation."""
    distance = abs(x - SIZE // 2) + abs(y - SIZE // 2)
    return 3 if distance < 14 else 2 if distance < 28 else 1


def generate(settlement_id: str, focus_x: int, focus_y: int) -> dict:
    if not settlement_id or len(settlement_id) > 80:
        raise ValueError("Invalid settlement")
    anchor_x, anchor_y = focus_x - SIZE // 2, focus_y - SIZE // 2
    seed = int.from_bytes(hashlib.sha256(f"basheco:city:{VERSION}:{settlement_id}".encode()).digest()[:8], "big")
    objects: list[dict] = []
    occupied: set[tuple[int, int]] = set()

    def put(kind: str, x: int, y: int, w: int = 1, h: int = 1, **extra: object) -> bool:
        cells = {(a, b) for a in range(x, x + w) for b in range(y, y + h)}
        if cells & occupied:
            return False
        occupied.update(cells)
        objects.append({"kind": kind, "cell": [anchor_x + x, anchor_y + y],
                        "size": [w, h], **extra})
        return True

    # Two widths are represented as classes for rendering; all streets occupy
    # one cell so intersection topology stays unambiguous.
    for y in range(SIZE):
        for x in range(SIZE):
            if x % STEP == 0 or y % STEP == 0:
                road_class = "avenue" if x % (STEP * 2) == 0 or y % (STEP * 2) == 0 else "local"
                put("road", x, y, road_class=road_class)

    for by in range(0, SIZE - STEP, STEP):
        for bx in range(0, SIZE - STEP, STEP):
            zone = district_at(bx + 3, by + 3)
            for slot in range(4):
                x, y = bx + 1 + (slot % 2) * 3, by + 1 + (slot // 2) * 3
                salt = (seed + bx * 37 + by * 71 + slot * 59) % 2147483647
                if zone == "park":
                    put("tree", x, y, zone=zone)
                    continue
                w, h = FOOTPRINTS[salt % len(FOOTPRINTS)]
                if zone == "center":
                    w, h = (2, 2) if slot else (3, 3)
                elif zone == "industrial":
                    w, h = (3, 2) if slot % 2 == 0 else (2, 2)
                elif zone == "commercial":
                    w, h = (2, 2)
                if x + w >= bx + STEP or y + h >= by + STEP:
                    continue
                building_type = "highrise" if zone == "center" else "apartment" if w * h >= 4 and zone == "residential" else "house"
                residents = BASE_RESIDENTS[building_type] if zone in ("center", "residential") else 0
                put("building", x, y, w, h, zone=zone, building_type=building_type,
                    residents_capacity_hint=residents, land_band=land_band(x, y))
    digest = hashlib.sha256(json.dumps(objects, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"schema": "basheco.city_plan/2", "generator_version": VERSION,
            "settlement_id": settlement_id, "focus_cell": [focus_x, focus_y],
            "size_cells": [SIZE, SIZE], "objects": objects,
            "content_hash": digest, "published": False}