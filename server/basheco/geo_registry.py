"""Administrative geography of Bashkortostan: region, 63 municipalities, settlements.

Real administrative data only. It is kept apart from every game object: nothing
here knows about plots, companies or generated territories.

Two steps:

  python -m basheco.geo_registry normalise RAW_DIR   # needs downloaded raw files
  python -m basheco.geo_registry build                # offline, deterministic

`normalise` turns raw downloads (OSM API XML, Wikidata SPARQL JSON; never
committed) into compact source snapshots under geodata/admin/sources/.
`build` turns those snapshots into the registry under geodata/admin/. A rebuild
from the same snapshots reproduces every file byte for byte and never changes
an identifier that was issued before (id_registry.json).

Nothing is invented: a settlement without a trustworthy coordinate keeps an
empty one, population is taken only with its year and reference, and every
mismatch is written to issues.json instead of being smoothed over.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from basheco.world_grid import CELL_METRES, CRS, GRID_VERSION, metres_to_cell
from basheco.world_projection import lonlat_to_metres

DATASET_VERSION = "bashkortostan-admin/2026-01-01/r1"
REFERENCE_DATE = "2026-01-01"
REGION_RELATION = "77677"
REGION_OKTMO = "80000000"
REGION_NAME = "Республика Башкортостан"
SIMPLIFY_METRES = {"overview": 200.0, "detail": 40.0}
OSM_API = "https://api.openstreetmap.org/api/0.6/relation/{id}/full"
SPARQL = "https://query.wikidata.org/sparql"
SETTLEMENT_TYPES = (  # order = priority when a Wikidata item has several classes
    ("город", ("город",)),  # a town that used to be an urban-type settlement is a town
    ("рабочий посёлок", ("рабочий посёлок", "посёлок городского типа")),
    ("село", ("село",)),
    ("деревня", ("деревня",)),
    ("хутор", ("хутор",)),
    ("посёлок", ("посёлок",)),
)
ABOLISHED = ("бывший населённый пункт", "бывшая деревня", "исчезнувший населённый пункт")
LEGACY_SLUGS = {  # pre-registry text ids used by world_sectors / geo_locations
    "ufa": {"name": "Уфа", "type": "город", "near": (55.972, 54.7386)},
    "mikhailovka": {"name": "Михайловка", "type": None, "near": (55.8925, 54.8055)},
}


def default_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "geodata" / "admin"


def _dump(path: Path, value, compact: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(value, ensure_ascii=False, indent=1)
    path.write_text(text + "\n", encoding="utf-8")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- step 1: raw downloads -> source snapshots -----------------------------------

def _relation(xml_file: Path, relation_id: str, ways: dict) -> dict:
    root = ET.parse(xml_file).getroot()
    nodes = {n.get("id"): (round(float(n.get("lon")), 7), round(float(n.get("lat")), 7), n)
             for n in root.findall("node")}
    way_nodes = {w.get("id"): [nd.get("ref") for nd in w.findall("nd")] for w in root.findall("way")}
    relation = next(r for r in root.findall("relation") if r.get("id") == relation_id)
    tags = {t.get("k"): t.get("v") for t in relation.findall("tag")}
    members = []
    centre = None
    for member in relation.findall("member"):
        kind, ref, role = member.get("type"), member.get("ref"), member.get("role")
        if kind == "way" and role in ("outer", "inner"):
            if ref not in way_nodes or any(n not in nodes for n in way_nodes[ref]):
                raise ValueError(f"Relation {relation_id}: boundary way {ref} is incomplete")
            ways[ref] = [[nodes[n][0], nodes[n][1]] for n in way_nodes[ref]]
            members.append([ref, role])
        elif kind == "node" and role == "admin_centre" and ref in nodes:
            node_tags = {t.get("k"): t.get("v") for t in nodes[ref][2].findall("tag")}
            centre = {"osm_node": ref, "name": node_tags.get("name"),
                      "lon": nodes[ref][0], "lat": nodes[ref][1]}
    return {"osm_relation": relation_id, "name": tags.get("name"), "admin_level": tags.get("admin_level"),
            "boundary": tags.get("boundary"), "wikidata": tags.get("wikidata"),
            "oktmo_tag": tags.get("oktmo:user") or tags.get("oktmo"),
            "admin_centre": centre, "members": members,
            "subareas": sorted((m.get("ref") for m in relation.findall("member")
                                if m.get("type") == "relation" and m.get("role") == "subarea"), key=int)}


def normalise(raw_dir: Path, out_dir: Path) -> dict:
    """Raw downloads -> geodata/admin/sources/*.json. Requires RAW_DIR/download_log.json."""
    log = _load(raw_dir / "download_log.json")
    ways: dict[str, list] = {}
    region = _relation(raw_dir / "rb_full.xml", REGION_RELATION, ways)
    municipalities = [_relation(raw_dir / "rel" / f"{rid}.xml", rid, ways) for rid in region["subareas"]]
    for item in municipalities:
        item.pop("subareas")
    region.pop("subareas")
    _dump(out_dir / "sources" / "osm_admin.json", {
        "schema": "basheco.geo_source.osm_admin/1", "crs": "EPSG:4326", "axis_order": "lon,lat",
        "region": region, "municipalities": municipalities,
        "ways": {key: ways[key] for key in sorted(ways, key=int)}})

    items: dict[str, dict] = {}
    for row in _load(raw_dir / "wd_items.json")["results"]["bindings"]:
        qid = row["s"]["value"].rsplit("/", 1)[1]
        item = items.setdefault(qid, {"qid": qid, "label": row["sLabel"]["value"], "oktmo": set(),
                                      "types": set(), "parents": set(), "coords": set()})
        if "oktmo" in row:
            item["oktmo"].add(row["oktmo"]["value"])
        if "typeLabel" in row:
            item["types"].add(row["typeLabel"]["value"])
        if "parent" in row:
            item["parents"].add(row["parent"]["value"].rsplit("/", 1)[1])
        if "coord" in row:
            item["coords"].add(row["coord"]["value"])
    population: dict[str, list] = {}
    for row in _load(raw_dir / "wd_population.json")["results"]["bindings"]:
        if "date" not in row or row.get("rank", {}).get("value", "").endswith("DeprecatedRank"):
            continue
        source = row.get("statedInLabel", {}).get("value")
        url = row.get("refurl", {}).get("value")
        if not source and not url:
            continue  # a number without a reference is not used
        if source and re.fullmatch(r"Q\d+", source):
            source = None
        if not source and not url:
            continue
        qid = row["s"]["value"].rsplit("/", 1)[1]
        try:
            value = int(float(row["pop"]["value"]))
        except ValueError:
            continue
        population.setdefault(qid, []).append(
            {"value": value, "year": int(row["date"]["value"][:4]), "source": source, "source_url": url})
    rows = []
    for qid, item in items.items():
        if not item["oktmo"]:
            continue
        coords = []
        for text in sorted(item["coords"]):
            match = re.fullmatch(r"Point\(([-\d.eE]+) ([-\d.eE]+)\)", text)
            if match:
                coords.append([round(float(match.group(1)), 6), round(float(match.group(2)), 6)])
        statements = sorted(population.get(qid, []),
                            key=lambda p: (p["year"], p["source"] or "", p["source_url"] or "", p["value"]))
        rows.append({"qid": qid, "label": item["label"], "oktmo": sorted(item["oktmo"]),
                     "types": sorted(item["types"]), "parents": sorted(item["parents"]),
                     "coords": coords, "population": statements[-1] if statements else None})
    rows.sort(key=lambda r: (r["oktmo"], r["qid"]))
    _dump(out_dir / "sources" / "wikidata_units.json", {
        "schema": "basheco.geo_source.wikidata/1",
        "selection": "items located (P131, transitively) in Q5710 that have an OKTMO code (P764)",
        "items": rows})
    wd_item, wd_pop = raw_dir / "wd_items.json", raw_dir / "wd_population.json"
    osm_times = sorted(v for k, v in log.items() if k.endswith(".xml"))
    sources = {"schema": "basheco.geo_sources/1", "sources": [
        {"id": "osm-admin-boundaries", "title": "OpenStreetMap: административные границы",
         "url": OSM_API.format(id=REGION_RELATION) + " и 63 вложенных отношения (subarea, admin_level=6)",
         "retrieved_utc": [osm_times[0], osm_times[-1]], "license": "ODbL 1.0",
         "attribution": "© OpenStreetMap contributors",
         "raw_sha256": {"rb_full.xml": _sha256(raw_dir / "rb_full.xml"),
                        "relations": hashlib.sha256("".join(
                            _sha256(raw_dir / "rel" / f"{m['osm_relation']}.xml") for m in municipalities
                        ).encode()).hexdigest()},
         "reflects": "состояние карты OSM на момент загрузки, не официальный реестр"},
        {"id": "wikidata-units", "title": "Wikidata: населённые пункты и муниципальные единицы с кодами ОКТМО",
         "url": SPARQL, "retrieved_utc": log.get("wd_items.json"), "license": "CC0 1.0",
         "raw_sha256": {"wd_items.json": _sha256(wd_item), "wd_population.json": _sha256(wd_pop)},
         "reflects": "данные Wikidata на момент запроса; коды ОКТМО и население внесены участниками со ссылками на Росстат"},
        {"id": "oktmo-rosstat", "title": "ОКТМО, Росстат (официальный классификатор)",
         "url": "https://rosstat.gov.ru/opendata/7708234640-oktmo", "retrieved_utc": None, "license": None,
         "status": "НЕ ПОЛУЧЕН: сайт Росстата недоступен из среды сборки. Сверка с официальным файлом не выполнена"},
    ]}
    _dump(out_dir / "sources.json", sources, compact=False)
    return sources


# --- step 2: source snapshots -> registry ----------------------------------------

def assemble_rings(members: list, ways: dict) -> list[dict]:
    """Join boundary ways into closed rings. Returns [{role, parts:[[way_id, reversed]]}]."""
    rings = []
    for role in ("outer", "inner"):
        pending = [way for way, r in members if r == role]
        while pending:
            first = pending.pop(0)
            parts = [[first, False]]
            start, end = tuple(ways[first][0]), tuple(ways[first][-1])
            while start != end:
                for index, way in enumerate(pending):
                    a, b = tuple(ways[way][0]), tuple(ways[way][-1])
                    if a == end:
                        parts.append([way, False]); end = b
                    elif b == end:
                        parts.append([way, True]); end = a
                    else:
                        continue
                    pending.pop(index)
                    break
                else:
                    raise ValueError("Boundary ring is not closed")
            rings.append({"role": role, "parts": parts})
    return rings


def ring_points(ring: dict, ways: dict) -> list:
    points: list = []
    for way, reverse in ring["parts"]:
        chain = ways[way][::-1] if reverse else ways[way]
        points.extend(chain if not points else chain[1:])
    return points


def shoelace(points: list) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1]))) / 2


def polygon_area(rings: list[dict], ways: dict) -> float:
    total = 0.0
    for ring in rings:
        area = shoelace(ring_points(ring, ways))
        total += area if ring["role"] == "outer" else -area
    return total


def point_in_rings(point, rings: list[list]) -> bool:
    """Even-odd rule over all rings (outer and inner)."""
    x, y = point
    inside = False
    for ring in rings:
        for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
            if (y0 <= y < y1) or (y1 <= y < y0):
                if x0 + (y - y0) * (x1 - x0) / (y1 - y0) > x:
                    inside = not inside
    return inside


def simplify(points: list, tolerance: float) -> list:
    """Douglas-Peucker with fixed end points (shared borders stay shared)."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        (x0, y0), (x1, y1) = points[first], points[last]
        dx, dy = x1 - x0, y1 - y0
        length = (dx * dx + dy * dy) ** 0.5
        worst, index = 0.0, -1
        for i in range(first + 1, last):
            px, py = points[i]
            if length == 0:
                distance = ((px - x0) ** 2 + (py - y0) ** 2) ** 0.5
            else:
                distance = abs(dy * (px - x0) - dx * (py - y0)) / length
            if distance > worst:
                worst, index = distance, i
        if worst > tolerance:
            keep[index] = True
            stack.append((first, index))
            stack.append((index, last))
    return [p for p, k in zip(points, keep) if k]


def settlement_type(types: list[str]) -> str | None:
    lowered = [t.lower() for t in types]
    for name, needles in SETTLEMENT_TYPES:
        for needle in needles:
            if any(t == needle or t.startswith(needle + " ") for t in lowered):
                return name
    return None


def build(out_dir: Path) -> dict:
    osm = _load(out_dir / "sources" / "osm_admin.json")
    units = _load(out_dir / "sources" / "wikidata_units.json")["items"]
    ways_lonlat = osm["ways"]
    issues: list[dict] = []

    def issue(kind: str, subject: str, text: str, **extra) -> None:
        issues.append({"kind": kind, "subject": subject, "description": text, **extra})

    registry_path = out_dir / "id_registry.json"
    registry = _load(registry_path)["ids"] if registry_path.exists() else {}
    by_first_oktmo = {entry["oktmo_at_issue"]: key for key, entry in registry.items()}

    def stable_id(prefix: str, oktmo: str) -> str:
        if oktmo in by_first_oktmo:
            return by_first_oktmo[oktmo]
        new_id = prefix + oktmo
        registry[new_id] = {"oktmo_at_issue": oktmo, "issued_in": DATASET_VERSION}
        by_first_oktmo[oktmo] = new_id
        return new_id

    # Boundaries: one geometry per OSM way, shared by both neighbours.
    ways_m = {key: [list(map(lambda v: round(v, 1), lonlat_to_metres(lon, lat))) for lon, lat in points]
              for key, points in ways_lonlat.items()}
    by_qid = {row["qid"]: row for row in units}
    municipal_oktmo: dict[str, dict] = {}
    municipalities = []
    for source in osm["municipalities"]:
        name = source["name"]
        if source["admin_level"] != "6" or source["boundary"] != "administrative":
            raise ValueError("Unexpected municipal relation: " + str(name))
        kind = "муниципальный район" if name.endswith("район") else "городской округ"
        oktmo = None
        unit = by_qid.get(source["wikidata"] or "")
        codes = [c for c in (unit["oktmo"] if unit else []) if len(c) == 8 and c.endswith("000")]
        if len(codes) == 1:
            oktmo = codes[0]
        if source["oktmo_tag"]:
            if oktmo and oktmo != source["oktmo_tag"]:
                issue("oktmo_mismatch", name, "Код ОКТМО в OSM и Wikidata различается",
                      osm=source["oktmo_tag"], wikidata=oktmo)
            oktmo = oktmo or source["oktmo_tag"]
        rings = assemble_rings(source["members"], ways_lonlat)
        municipalities.append({"source": source, "name": name, "type": kind, "oktmo": oktmo, "rings": rings,
                               "rings_lonlat": [ring_points(r, ways_lonlat) for r in rings]})
    # A municipality whose code is unknown gets it from its own settlements below.
    region_rings = assemble_rings(osm["region"]["members"], ways_lonlat)

    settlements_raw = []
    unit_names: dict[str, str] = {}
    for row in units:
        long_codes = [c for c in row["oktmo"] if len(c) == 11]
        for code in row["oktmo"]:
            if len(code) == 8 and not code.endswith("000"):
                unit_names.setdefault(code, row["label"])
        if len(long_codes) == 1 and long_codes[0].startswith("80"):
            settlements_raw.append((long_codes[0], row))
        elif long_codes:
            issue("oktmo_ambiguous", row["qid"], "У объекта несколько кодов ОКТМО или код другого региона",
                  codes=row["oktmo"])
    seen_codes: dict[str, str] = {}
    located: dict[str, list] = {}
    for code, row in sorted(settlements_raw, key=lambda item: (item[0], item[1]["qid"])):
        if code in seen_codes:
            issue("oktmo_duplicate", row["qid"], "Код ОКТМО уже занят другим объектом Wikidata",
                  oktmo=code, other=seen_codes[code])
            continue
        seen_codes[code] = row["qid"]
        located.setdefault(code[:5] + "000", []).append((code, row))

    # Municipal code by spatial vote when Wikidata did not give it.
    for item in municipalities:
        if item["oktmo"]:
            continue
        votes: dict[str, int] = {}
        for code, rows in located.items():
            for _, row in rows[:40]:
                if row["coords"] and point_in_rings(row["coords"][0], item["rings_lonlat"]):
                    votes[code] = votes.get(code, 0) + 1
        if votes:
            item["oktmo"] = max(sorted(votes), key=lambda c: votes[c])
            issue("municipality_code_inferred", item["name"],
                  "Код ОКТМО муниципалитета определён по кодам его населённых пунктов", oktmo=item["oktmo"])
    for item in municipalities:
        if not item["oktmo"] or item["oktmo"] in municipal_oktmo:
            raise ValueError("Municipality without a unique OKTMO code: " + item["name"])
        municipal_oktmo[item["oktmo"]] = item

    municipalities.sort(key=lambda m: m["oktmo"])
    municipal_out = []
    settlement_files: dict[str, list] = {}
    counts = {"settlements": 0, "with_coordinates": 0, "coordinates_confirmed": 0, "with_population": 0,
              "by_type": {}}
    all_settlements = []
    for item in municipalities:
        municipality_id = stable_id("M", item["oktmo"])
        rows_out = []
        names: dict[str, int] = {}
        for code, row in located.pop(item["oktmo"], []):
            name = row["label"]
            if re.fullmatch(r"Q\d+", name):
                issue("no_russian_name", row["qid"], "У объекта Wikidata нет русского названия; запись не включена",
                      oktmo=code)
                continue
            if "(" in name:
                clean = re.sub(r"\s*\(.*\)\s*$", "", name)
                issue("name_normalised", code, "Из названия убрано уточнение в скобках", original=name, used=clean)
                name = clean
            kind = settlement_type(row["types"])
            unit_prefix = re.match(r"(городское|сельское) поселение (.+)$", name)
            if unit_prefix:
                # The code belongs to a settlement, but the source item describes its municipal unit.
                issue("name_from_municipal_unit", code,
                      "Код населённого пункта в источнике привязан к записи о поселении; название взято из неё",
                      original=name, used=unit_prefix.group(2))
                name = unit_prefix.group(2)
                kind = kind or ("город" if unit_prefix.group(1) == "городское" else None)
            if kind is None:
                kind = "населённый пункт"
                issue("type_unclear", code, "Тип населённого пункта не определён по источнику", types=row["types"])
            if any(t.lower() in ABOLISHED for t in row["types"]):
                issue("possibly_abolished", code, "В источнике пункт помечен как бывший; требуется сверка с ОКТМО",
                      name=name)
            entry = {"id": stable_id("S", code), "name": name, "type": kind,
                     "municipality_id": municipality_id, "oktmo": code,
                     "unit_oktmo": code[:8], "unit_name": unit_names.get(code[:8]),
                     "wikidata": row["qid"], "lon": None, "lat": None, "easting": None, "northing": None,
                     "world_cell": None, "coordinate_source": None, "coordinate_status": "missing",
                     "population": None}
            # Prefer a coordinate that agrees with the settlement's own municipality.
            candidates = row["coords"]
            agreeing = [c for c in candidates if point_in_rings(c, item["rings_lonlat"])]
            if len(candidates) > 1:
                issue("several_coordinates", code,
                      "В источнике несколько координат; взята лежащая внутри своего муниципалитета, иначе первая",
                      name=name, coords=candidates)
            chosen = (agreeing or candidates or [None])[0]
            if chosen is not None and not agreeing:
                actual = next((m["name"] for m in municipalities if point_in_rings(chosen, m["rings_lonlat"])), None)
                if actual is None:
                    # Outside the republic altogether: not a usable coordinate.
                    issue("coordinates_rejected", code, "Координаты из источника лежат вне республики и не использованы",
                          name=name, coords=chosen)
                    chosen = None
                else:
                    issue("outside_boundary", code,
                          "Точка лежит вне границы муниципалитета, к которому пункт отнесён по коду ОКТМО",
                          name=name, expected=item["name"], found_in=actual)
            if chosen is not None:
                lon, lat = chosen
                east, north = lonlat_to_metres(lon, lat)
                entry.update({"lon": lon, "lat": lat, "easting": round(east, 1), "northing": round(north, 1),
                              "world_cell": list(metres_to_cell(east, north)),
                              "coordinate_source": "wikidata:P625",
                              "coordinate_status": "inside_municipality" if agreeing else "outside_municipality"})
                counts["with_coordinates"] += 1
                counts["coordinates_confirmed"] += bool(agreeing)
            elif not candidates:
                issue("no_coordinates", code, "Нет координат в источнике", name=name)
            if row["population"]:
                entry["population"] = {**row["population"], "via": "wikidata:P1082"}
                counts["with_population"] += 1
            names[name] = names.get(name, 0) + 1
            rows_out.append(entry)
        for entry in rows_out:
            entry["same_name_in_municipality"] = names[entry["name"]] > 1
        rows_out.sort(key=lambda e: e["oktmo"])
        for entry in rows_out:
            counts["by_type"][entry["type"]] = counts["by_type"].get(entry["type"], 0) + 1
        counts["settlements"] += len(rows_out)
        settlement_files[municipality_id] = rows_out
        all_settlements.extend(rows_out)
        xs = [p[0] for ring in item["rings"] for way, _ in ring["parts"] for p in ways_m[way]]
        ys = [p[1] for ring in item["rings"] for way, _ in ring["parts"] for p in ways_m[way]]
        centre = item["source"]["admin_centre"] or {}
        municipal_out.append({
            "id": municipality_id, "name": item["name"], "type": item["type"], "oktmo": item["oktmo"],
            "osm_relation": item["source"]["osm_relation"], "wikidata": item["source"]["wikidata"],
            "admin_centre": centre.get("name"),
            "admin_centre_lonlat": [centre["lon"], centre["lat"]] if centre else None,
            "bbox_m": [min(xs), min(ys), max(xs), max(ys)],
            "area_km2": round(polygon_area(item["rings"], ways_m) / 1e6, 1),
            "settlement_count": len(rows_out), "rings": item["rings"]})
    for code, rows in sorted(located.items()):
        for settlement_code, row in rows:
            issue("unknown_municipality", settlement_code,
                  "Код ОКТМО не относится ни к одному из 63 муниципалитетов", name=row["label"])

    # Legacy text ids -> registry ids (explicit, checked by position).
    legacy = {}
    for slug, rule in LEGACY_SLUGS.items():
        near_east, near_north = lonlat_to_metres(*rule["near"])
        candidates = [s for s in all_settlements if s["name"] == rule["name"] and s["easting"] is not None
                      and (rule["type"] is None or s["type"] == rule["type"])
                      and ((s["easting"] - near_east) ** 2 + (s["northing"] - near_north) ** 2) ** 0.5 < 15000]
        if len(candidates) == 1:
            legacy[slug] = candidates[0]["id"]
        else:
            issue("legacy_id_unresolved", slug, "Не удалось однозначно сопоставить старый идентификатор",
                  candidates=[c["id"] for c in candidates])

    # Files.
    region_area = polygon_area(region_rings, ways_m)
    municipal_area = sum(polygon_area(m["rings"], ways_m) for m in municipal_out)
    used = sorted({way for m in municipal_out for ring in m["rings"] for way, _ in ring["parts"]}
                  | {way for ring in region_rings for way, _ in ring["parts"]}, key=int)
    boundaries_dir = out_dir / "boundaries"
    lod_stats = {}
    for lod, tolerance in SIMPLIFY_METRES.items():
        simplified = {way: [[round(x), round(y)] for x, y in simplify(ways_m[way], tolerance)] for way in used}
        # Simplification works per way. A small ring may collapse; such rings get
        # their full source geometry back so every boundary stays a real polygon.
        restored = set()
        for rings in [region_rings] + [m["rings"] for m in municipal_out]:
            for ring in rings:
                original = shoelace(ring_points(ring, ways_m)[:-1])
                points = ring_points(ring, simplified)
                if len(points) < 5 or shoelace(points[:-1]) < 0.8 * original:
                    for way, _ in ring["parts"]:
                        simplified[way] = [[round(x), round(y)] for x, y in ways_m[way]]
                        restored.add(way)
        _dump(boundaries_dir / f"ways_{lod}.json", {
            "schema": "basheco.geo_boundary_ways/1", "crs": CRS, "grid_version": GRID_VERSION,
            "units": "metres, [easting, northing]", "tolerance_m": tolerance,
            "dataset_version": DATASET_VERSION, "ways": simplified})
        lod_stats[lod] = {"tolerance_m": tolerance, "points": sum(len(v) for v in simplified.values()),
                          "ways_kept_unsimplified": len(restored)}
    lod_stats["source"] = {"points": sum(len(ways_m[w]) for w in used)}
    _dump(out_dir / "region.json", {
        "schema": "basheco.geo_region/1", "dataset_version": DATASET_VERSION,
        "id": stable_id("R", REGION_OKTMO), "name": REGION_NAME, "oktmo": REGION_OKTMO,
        "osm_relation": REGION_RELATION, "wikidata": osm["region"]["wikidata"],
        "area_km2_projected": round(region_area / 1e6, 1), "rings": region_rings}, compact=False)
    _dump(out_dir / "municipalities.json", {
        "schema": "basheco.geo_municipalities/1", "dataset_version": DATASET_VERSION,
        "ring_format": "rings[].parts = [way_id, reversed]; geometry in boundaries/ways_*.json",
        "municipalities": municipal_out})
    settlements_dir = out_dir / "settlements"
    if settlements_dir.exists():
        for stale in settlements_dir.glob("*.json"):
            stale.unlink()
    for municipality_id, rows_out in settlement_files.items():
        _dump(settlements_dir / f"{municipality_id}.json", {
            "schema": "basheco.geo_settlements/1", "dataset_version": DATASET_VERSION,
            "municipality_id": municipality_id, "settlements": rows_out})
    _dump(out_dir / "legacy_ids.json", {"schema": "basheco.geo_legacy_ids/1", "ids": legacy}, compact=False)
    _dump(registry_path, {"schema": "basheco.geo_id_registry/1",
                          "rule": "id = вид записи + код ОКТМО на момент первой выдачи; выданный id не меняется никогда",
                          "ids": {key: registry[key] for key in sorted(registry)}})
    issues.sort(key=lambda i: (i["kind"], str(i["subject"])))
    issue_counts: dict[str, int] = {}
    for entry in issues:
        issue_counts[entry["kind"]] = issue_counts.get(entry["kind"], 0) + 1
    _dump(out_dir / "issues.json", {"schema": "basheco.geo_import_issues/1", "dataset_version": DATASET_VERSION,
                                    "counts": dict(sorted(issue_counts.items())), "issues": issues}, compact=False)
    types = {}
    for m in municipal_out:
        types[m["type"]] = types.get(m["type"], 0) + 1
    version = {
        "schema": "basheco.geo_dataset_version/1", "dataset_version": DATASET_VERSION,
        "target_reference_date": REFERENCE_DATE,
        "actual_state": "границы и перечень отражают OSM и Wikidata на дату загрузки (см. sources.json), а не официальный срез на 1 января 2026 года",
        "verification": {
            "official_oktmo_file_compared": False,
            "municipality_count_confirmed_by_primary_legal_source": False,
            "note": "Сайт Росстата недоступен из среды сборки. До сверки с официальным файлом ОКТМО полнота перечня и официальность названий не подтверждены",
        },
        "counts": {"municipalities": len(municipal_out), "municipalities_by_type": dict(sorted(types.items())),
                   **{k: v for k, v in counts.items() if k != "by_type"},
                   "settlements_by_type": dict(sorted(counts["by_type"].items())),
                   "issues": dict(sorted(issue_counts.items()))},
        "boundaries": {"levels": lod_stats, "shared_ways": len(used),
                       "region_area_km2": round(region_area / 1e6, 1),
                       "sum_of_municipal_areas_km2": round(municipal_area / 1e6, 1)},
        "grid": {"crs": CRS, "grid_version": GRID_VERSION, "cell_metres": CELL_METRES},
        "names": "только официальные русские названия; другие языки на этом этапе не ведутся",
    }
    _dump(out_dir / "dataset_version.json", version, compact=False)
    return version


def main() -> None:
    out_dir = default_dir()
    if len(sys.argv) == 3 and sys.argv[1] == "normalise":
        normalise(Path(sys.argv[2]), out_dir)
        print("Source snapshots written to", out_dir / "sources")
    elif len(sys.argv) == 2 and sys.argv[1] == "build":
        version = build(out_dir)
        print(json.dumps(version["counts"], ensure_ascii=False))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
