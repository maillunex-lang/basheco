"""Conservative land-cover/terrain evidence gate for generated construction.

No land-cover or elevation sources are bundled. Missing, untrusted, or partial
evidence is UNKNOWN and must never be treated as buildable.
"""
from __future__ import annotations

from collections import Counter

REQUIRED_LAYERS = ("water", "terrain", "protected_area", "land_rights")
KNOWN_STATES = frozenset(("clear", "blocked", "unknown"))
SCHEMA = "basheco.land_constraints/1"


def assess_cells(cells: set[tuple[int, int]], evidence: dict | None) -> dict:
    """Check every footprint cell against all four required evidence layers.

    Evidence is an offline, independently verified cell-by-cell report, NOT an
    authorization token. A report must include a nonempty source, source version,
    and a per-layer mapping of each cell to a known state. 'clear' alone is not
    sufficient unless provenance and complete coverage exist.
    """
    if not cells:
        raise ValueError("No occupied cells")
    reasons = []
    counts = Counter()
    if not isinstance(evidence, dict) or evidence.get("schema") != SCHEMA:
        reasons.append("missing_or_unsupported_evidence")
        evidence = {}
    if not isinstance(evidence.get("source"), str) or not evidence.get("source", "").strip():
        reasons.append("missing_source")
    if not isinstance(evidence.get("source_version"), str) or not evidence.get("source_version", "").strip():
        reasons.append("missing_source_version")
    layers = evidence.get("layers")
    if not isinstance(layers, dict):
        layers = {}
    for layer in REQUIRED_LAYERS:
        layer_data = layers.get(layer)
        if not isinstance(layer_data, dict):
            reasons.append("missing_layer:" + layer)
            counts["unknown"] += len(cells)
            continue
        for x, y in cells:
            value = layer_data.get(f"{x},{y}", "unknown")
            if value not in KNOWN_STATES:
                value = "unknown"
            counts[value] += 1
            if value == "blocked":
                reasons.append(f"blocked:{layer}:{x},{y}")
            elif value == "unknown":
                reasons.append(f"unknown:{layer}:{x},{y}")
    safe = not reasons
    return {"safe_to_build": safe,
            "decision": "clear" if safe else "blocked" if counts["blocked"] else "unknown",
            "checked_cells": len(cells), "required_layers": list(REQUIRED_LAYERS),
            "clear_checks": counts["clear"], "blocked_checks": counts["blocked"],
            "unknown_checks": counts["unknown"], "reasons": sorted(set(reasons))}


def footprint_cells(location: dict) -> set[tuple[int, int]]:
    occupied = set()
    for obj in location["objects"]:
        x, y = obj["cell"]
        w, h = obj["size"]
        if any(type(v) is not int for v in (x, y, w, h)) or min(w, h) <= 0:
            raise ValueError("Invalid footprint")
        for cx in range(x, x + w):
            for cy in range(y, y + h):
                if (cx, cy) in occupied:
                    raise ValueError("Overlapping generated footprint")
                occupied.add((cx, cy))
    return occupied