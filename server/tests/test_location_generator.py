"""Stage 1.3 population-based, capped, deterministic offline candidate generation."""
import json
from collections import Counter

from basheco.location_generator import (
    LIMIT, PILOT, SCHEMA, _population, build, choose_settlements, generate,
)


def test_selection_capped_and_sourced():
    selected = choose_settlements()
    counts = Counter(s["municipality_id"] for s in selected)
    assert len(counts) == 63
    assert max(counts.values()) <= LIMIT
    assert all(1 <= n <= LIMIT for n in counts.values())
    assert len({s["settlement_id"] for s in selected}) == len(selected)
    assert any(s["settlement_id"] == PILOT for s in selected)
    assert all(s["population"] is not None and s["population"] > 0 for s in selected)
    assert all(s["selection"] in ("population", "approved_pilot") for s in selected)


def test_generator_deterministic_no_overlap_and_chunk_integrity():
    chosen = choose_settlements()
    for record in chosen:
        a = generate(record)
        b = generate(record)
        assert a == b
        assert a["cell_size_m"] == 6
        assert a["chunk_size_cells"] == 64
        occupied = set()
        road = set()
        houses = 0
        for obj in a["objects"]:
            x, y = obj["cell"]
            w, h = obj["size"]
            assert w >= 1 and h >= 1
            footprint = {(xx, yy) for xx in range(x, x + w) for yy in range(y, y + h)}
            assert not footprint & occupied
            occupied.update(footprint)
            if obj["kind"] == "road":
                road.update(footprint)
            elif obj["kind"] == "house":
                houses += 1
        assert houses == 15
        assert len(road) == 61
        assert all([x // 64, y // 64] in a["chunks"] for x, y in occupied)


def test_publication_is_pilot_only_and_catalog_unchanged():
    data = build()
    assert data["schema"] == SCHEMA
    assert data["published_settlement_ids"] == [PILOT]
    assert len(data["selection"]) == len(data["locations"])
    assert len(data["locations"]) <= 63 * LIMIT
    assert json.dumps(data, ensure_ascii=False, sort_keys=True) == json.dumps(
        build(), ensure_ascii=False, sort_keys=True
    )


def test_unknown_population_not_ranked_as_largest():
    assert _population({"population": {"value": 20000}}) is None
    assert _population({"population": {"value": None, "source": "x"}}) is None
    assert _population({"population": {"value": 0, "source": "x"}}) is None