from basheco.city_plan import generate, DISTRICTS, SIZE, district_at, land_band


def test_determinism_and_isolation():
    a = generate("S80652440101", 5000, -6000)
    assert a == generate("S80652440101", 5000, -6000)
    assert a["content_hash"] != generate("S80652440102", 5000, -6000)["content_hash"]
    assert a["schema"] == "basheco.city_plan/2"
    assert a["published"] is False


def test_grid_no_overlap_and_road_connectivity():
    plan = generate("S80652440101", 5000, -6000)
    cells = set()
    roads = set()
    for obj in plan["objects"]:
        x, y = obj["cell"]
        w, h = obj["size"]
        for cx in range(x, x + w):
            for cy in range(y, y + h):
                assert (cx, cy) not in cells
                cells.add((cx, cy))
                if obj["kind"] == "road":
                    roads.add((cx, cy))
    assert len(roads) > 600
    # Every road segment belongs to the same connected network.
    seen = {next(iter(roads))}
    frontier = list(seen)
    while frontier:
        x, y = frontier.pop()
        for cell in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if cell in roads and cell not in seen:
                seen.add(cell)
                frontier.append(cell)
    assert seen == roads


def test_districts_building_sizes_capacity_and_land_bands():
    plan = generate("S80652440101", 5000, -6000)
    assert len(DISTRICTS) == 5
    assert {o["zone"] for o in plan["objects"] if "zone" in o} == set(DISTRICTS)
    buildings = [o for o in plan["objects"] if o["kind"] == "building"]
    assert buildings
    assert any(o["size"] == [1, 1] for o in buildings)
    assert any(o["size"] == [3, 3] for o in buildings)
    assert all(o["residents_capacity_hint"] >= 0 for o in buildings)
    assert any(o["residents_capacity_hint"] > 0 for o in buildings)
    assert land_band(28, 28) == 3
    assert land_band(0, 0) == 1
    assert district_at(28, 28) == "center"