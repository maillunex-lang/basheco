"""Administrative geography of Bashkortostan: region, 63 municipalities, settlements.

Real administrative data only. It is kept apart from every game object: nothing
here knows about plots, companies or generated territories.

Two steps:

  python -m basheco.geo_registry normalise RAW_DIR   # needs downloaded raw files
  python -m basheco.geo_registry build                # offline, deterministic

`normalise` turns raw downloads (OKTMO and OKATO CSV, OSM API XML, Wikidata
SPARQL JSON; never committed) into compact source snapshots under
geodata/admin/sources/.

Roles of the sources: OKTMO (OK 033-2013) defines WHICH settlements exist, their
official names, types and municipality. OpenStreetMap gives boundaries.
Wikidata only adds coordinates and population to an OKTMO code; it never adds
or renames a settlement.
`build` turns those snapshots into the registry under geodata/admin/. A rebuild
from the same snapshots reproduces every file byte for byte and never changes
an identifier that was issued before (id_registry.json).

Nothing is invented: a settlement without a trustworthy coordinate keeps an
empty one, population is taken only with its year and reference, and every
mismatch is written to issues.json instead of being smoothed over.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from basheco.world_grid import CELL_METRES, CRS, GRID_VERSION, metres_to_cell
from basheco.world_projection import lonlat_to_metres

DATASET_VERSION = "bashkortostan-admin/2026-01-01/r2"
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
OKTMO_MIRROR = "https://classifikators.ru/assets/downloads/oktmo/oktmo.csv"
OKATO_MIRROR = "https://classifikators.ru/assets/downloads/okato/okato.csv"
OKTMO_TYPES = {"г": "город", "рп": "рабочий посёлок", "с": "село", "д": "деревня", "п": "посёлок",
               "х": "хутор", "кордон": "кордон"}
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


def oktmo_control_digit(code: str) -> int:
    """Control number of an OKTMO/OKATO code (PR 50.1.024-2005)."""
    def remainder(weight: int) -> int:
        total = 0
        for char in code:
            total += int(char) * weight
            weight = weight + 1 if weight < 10 else 1
        return total % 11
    value = remainder(1)
    if value == 10:
        value = remainder(3)
    return 0 if value == 10 else value


def normalise_oktmo(raw_dir: Path, out_dir: Path) -> dict:
    """Bashkortostan part of the full OKTMO file, cross-checked against OKATO."""
    read = lambda name: list(csv.reader((raw_dir / name).open(encoding="utf-8-sig"), delimiter=";"))
    oktmo, okato = read("oktmo.csv"), read("okato.csv")
    # The region is found by its title, not by an assumed code.
    territories = sorted({r[0] for r in oktmo if r[6] == "Муниципальные образования Республики Башкортостан"})
    mentions = sorted({r[0] for r in oktmo if "Республики Башкортостан" in r[6]})
    if len(territories) != 1 or mentions != territories:
        raise ValueError("Bashkortostan is not exactly one OKTMO territory: %s / %s" % (territories, mentions))
    territory = territories[0]
    rows = [r for r in oktmo if r[0] == territory]
    for r in rows:
        code = r[0] + r[1] + r[2] + (r[3] if r[5] == "2" else "")
        if str(oktmo_control_digit(code)) != r[4]:
            raise ValueError("OKTMO control digit mismatch: " + code)
    municipalities, units, settlements = [], [], []
    for r in rows:
        if r[5] == "1" and r[1] != "000" and r[2] == "000" and not r[6].endswith("/") \
                and not r[6].endswith("Республики Башкортостан"):
            municipalities.append({"oktmo": r[0] + r[1] + "000", "name": r[6], "centre": r[7]})
        elif r[5] == "1" and r[2] != "000" and not r[6].endswith("/"):
            units.append({"oktmo": r[0] + r[1] + r[2], "name": r[6], "centre": r[7],
                          "kind": "городское поселение" if r[2][0] == "1" else "сельское поселение"})
        elif r[5] == "2" and r[3] != "000":
            abbreviation, name = r[6].split(" ", 1)
            settlements.append({"oktmo": r[0] + r[1] + r[2] + r[3], "type_abbr": abbreviation, "name": name,
                                "change_no": r[9], "introduced": r[12]})
    # Independent official cross-check: rural settlements of OKATO, by district, type and name.
    key = lambda text: text.replace("ё", "е").strip().lower()
    a_rows = [r for r in okato if r[0] == territory]
    a_names = {r[1]: r[5] for r in a_rows if r[2] == "000" and r[3] == "000" and not r[5].startswith("Сельские")}
    cities = {"уфа": "г уфа", "кумертау": "г кумертау", "сибай": "г сибай", "нефтекамск": "г нефтекамск",
              "бирск": "бирский район", "дюртюли": "дюртюлинский район"}
    a_set: dict = {}
    for r in a_rows:
        if r[3] != "000":
            k = (cities.get(key(a_names[r[1]]), key(a_names[r[1]])), key(r[5]))
            a_set[k] = a_set.get(k, 0) + 1
    m_names = {m["oktmo"][:5]: key(m["name"]).replace("муниципальный район", "район")
               .replace("зато город ", "г ").replace("город ", "г ") for m in municipalities}
    matched, unmatched = 0, []
    remaining = dict(a_set)
    for item in settlements:
        k = (m_names[item["oktmo"][:5]], key(item["type_abbr"] + " " + item["name"]))
        if remaining.get(k, 0) > 0:
            remaining[k] -= 1
            matched += 1
        elif item["type_abbr"] not in ("г", "рп"):
            unmatched.append(item["oktmo"])
    dates = sorted({r[12][6:] + r[12][3:5] + r[12][:2] for r in rows if len(r[12]) == 10})
    snapshot = {
        "schema": "basheco.geo_source.oktmo/1", "classifier": "ОКТМО ОК 033-2013",
        "territory_code": territory, "region": "Республика Башкортостан",
        "rows_in_full_file": len(oktmo), "rows_of_region": len(rows),
        "latest_change_in_region": dates[-1] if dates else None,
        "control_digits_checked": len(rows),
        "okato_cross_check": {"okato_rural_settlements": sum(a_set.values()), "matched_in_oktmo": matched,
                              "oktmo_rural_not_in_okato": unmatched,
                              "okato_not_in_oktmo": sum(v for v in remaining.values() if v > 0)},
        "municipalities": municipalities, "units": units, "settlements": settlements}
    _dump(out_dir / "sources" / "oktmo_bashkortostan.json", snapshot)
    return snapshot


def normalise(raw_dir: Path, out_dir: Path) -> dict:
    """Raw downloads -> geodata/admin/sources/*.json. Requires RAW_DIR/download_log.json."""
    log = _load(raw_dir / "download_log.json")
    oktmo = normalise_oktmo(raw_dir, out_dir)
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
         "reflects": "данные Wikidata на момент запроса; используются только координаты и население по совпадению кода ОКТМО"},
        {"id": "oktmo", "title": "ОКТМО ОК 033-2013 (ведёт Росстат), полный файл",
         "url": OKTMO_MIRROR, "retrieved_utc": log.get("oktmo.csv"), "license": None,
         "raw_sha256": {"oktmo.csv": _sha256(raw_dir / "oktmo.csv")},
         "origin": "зеркало classifikators.ru; сайт Росстата недоступен из среды сборки",
         "checks": "формат совпадает с открытыми данными Росстата; контрольные цифры всех %d строк региона верны; "
                   "сельские населённые пункты совпали с ОКАТО: %d из %d" % (
                       oktmo["control_digits_checked"], oktmo["okato_cross_check"]["matched_in_oktmo"],
                       oktmo["okato_cross_check"]["okato_rural_settlements"]),
         "not_checked": "побайтное совпадение с файлом Росстата",
         "latest_change_in_region": oktmo["latest_change_in_region"]},
        {"id": "okato", "title": "ОКАТО ОК 019-95, полный файл (только для сверки)",
         "url": OKATO_MIRROR, "retrieved_utc": log.get("okato.csv"), "license": None,
         "raw_sha256": {"okato.csv": _sha256(raw_dir / "okato.csv")},
         "origin": "зеркало classifikators.ru"},
        {"id": "registry-rb", "title": "Реестр административно-территориальных единиц и населённых пунктов РБ "
                                       "(постановление Правительства РБ от 29.12.2006 № 391)",
         "url": "https://base.garant.ru/17713113/", "retrieved_utc": None, "license": None,
         "status": "НЕ ИСПОЛЬЗОВАН: постановление опубликовано без текста реестра, публичной версии нет"},
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
    oktmo = _load(out_dir / "sources" / "oktmo_bashkortostan.json")
    official_municipalities = {m["oktmo"]: m for m in oktmo["municipalities"]}
    official_units = {u["oktmo"]: u for u in oktmo["units"]}
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
    municipalities = []
    for source in osm["municipalities"]:
        if source["admin_level"] != "6" or source["boundary"] != "administrative":
            raise ValueError("Unexpected municipal relation: " + str(source["name"]))
        code = None
        unit = by_qid.get(source["wikidata"] or "")
        codes = [c for c in (unit["oktmo"] if unit else []) if len(c) == 8 and c.endswith("000")]
        if len(codes) == 1:
            code = codes[0]
        if source["oktmo_tag"]:
            if code and code != source["oktmo_tag"]:
                issue("oktmo_mismatch", source["name"], "Код ОКТМО в OSM и Wikidata различается",
                      osm=source["oktmo_tag"], wikidata=code)
            code = code or source["oktmo_tag"]
        rings = assemble_rings(source["members"], ways_lonlat)
        municipalities.append({"source": source, "oktmo": code, "rings": rings,
                               "rings_lonlat": [ring_points(r, ways_lonlat) for r in rings]})
    region_rings = assemble_rings(osm["region"]["members"], ways_lonlat)

    # Wikidata is only a lookup by OKTMO code (coordinates, population).
    wikidata: dict[str, dict] = {}
    for row in sorted(units, key=lambda r: r["qid"]):
        long_codes = [c for c in row["oktmo"] if len(c) == 11]
        if len(long_codes) != 1:
            if long_codes:
                issue("wikidata_code_ambiguous", row["qid"], "У объекта Wikidata несколько кодов ОКТМО; не использован",
                      codes=row["oktmo"])
            continue
        if long_codes[0] in wikidata:
            issue("wikidata_code_duplicate", row["qid"], "Код ОКТМО уже занят другим объектом Wikidata; не использован",
                  oktmo=long_codes[0], other=wikidata[long_codes[0]]["qid"])
            continue
        wikidata[long_codes[0]] = row

    official: dict[str, list] = {}
    for item in oktmo["settlements"]:
        official.setdefault(item["oktmo"][:5] + "000", []).append(item)
    # A boundary whose code is unknown gets it from the settlements that lie inside it.
    for item in municipalities:
        if item["oktmo"]:
            continue
        votes: dict[str, int] = {}
        for code, rows in official.items():
            for row in rows[:40]:
                found = wikidata.get(row["oktmo"])
                if found and found["coords"] and point_in_rings(found["coords"][0], item["rings_lonlat"]):
                    votes[code] = votes.get(code, 0) + 1
        if votes:
            item["oktmo"] = max(sorted(votes), key=lambda c: votes[c])
            issue("municipality_code_inferred", item["source"]["name"],
                  "Код ОКТМО границы из OSM определён по населённым пунктам внутри неё", oktmo=item["oktmo"])
    matched_codes = [m["oktmo"] for m in municipalities]
    if sorted(matched_codes) != sorted(official_municipalities):
        raise ValueError("OSM boundaries and OKTMO municipalities do not match one to one")

    municipalities.sort(key=lambda m: m["oktmo"])
    municipal_out = []
    settlement_files: dict[str, list] = {}
    counts = {"settlements": 0, "with_coordinates": 0, "coordinates_confirmed": 0, "with_population": 0,
              "by_type": {}}
    comparison = {"wikidata_items_matched_by_code": 0, "type_differs_from_wikidata": 0,
                  "name_differs_from_wikidata": 0}
    all_settlements = []
    plain = lambda text: re.sub(r"[^a-zа-я0-9]", "", text.lower().replace("ё", "е"))
    for item in municipalities:
        record = official_municipalities[item["oktmo"]]
        item["name"] = record["name"]
        item["type"] = "городской округ" if item["oktmo"][2] == "7" else "муниципальный район"
        municipality_id = stable_id("M", item["oktmo"])
        rows_out = []
        names: dict[tuple, int] = {}
        for row in official.get(item["oktmo"], []):
            code, name = row["oktmo"], row["name"]
            kind = OKTMO_TYPES.get(row["type_abbr"])
            if kind is None:
                raise ValueError("Unknown OKTMO settlement type: " + row["type_abbr"])
            unit = official_units.get(code[:8])
            found = wikidata.get(code)
            entry = {"id": stable_id("S", code), "name": name, "type": kind, "type_abbr": row["type_abbr"],
                     "municipality_id": municipality_id, "oktmo": code,
                     "unit_oktmo": code[:8] if unit else None, "unit_name": unit["name"] if unit else None,
                     "oktmo_change_no": row["change_no"], "oktmo_introduced": row["introduced"],
                     "wikidata": found["qid"] if found else None,
                     "lon": None, "lat": None, "easting": None, "northing": None,
                     "world_cell": None, "coordinate_source": None, "coordinate_status": "missing",
                     "population": None}
            if found:
                comparison["wikidata_items_matched_by_code"] += 1
                other_type = settlement_type(found["types"])
                comparison["type_differs_from_wikidata"] += other_type != kind
                comparison["name_differs_from_wikidata"] += plain(found["label"]) != plain(name)
            # Prefer a coordinate that agrees with the settlement's own municipality.
            candidates = found["coords"] if found else []
            agreeing = [c for c in candidates if point_in_rings(c, item["rings_lonlat"])]
            if len(candidates) > 1:
                issue("several_coordinates", code,
                      "В источнике несколько координат; взята лежащая внутри своего муниципалитета, иначе первая",
                      name=name, coords=candidates)
            chosen = (agreeing or candidates or [None])[0]
            if chosen is not None and not agreeing:
                actual = next((m["source"]["name"] for m in municipalities
                               if point_in_rings(chosen, m["rings_lonlat"])), None)
                if actual is None:
                    # Outside the republic altogether: not a usable coordinate.
                    issue("coordinates_rejected", code, "Координаты из источника лежат вне республики и не использованы",
                          name=name, coords=chosen)
                    chosen = None
                else:
                    issue("outside_boundary", code,
                          "Точка лежит вне границы муниципалитета, к которому пункт отнесён в ОКТМО",
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
                issue("no_coordinates", code, "Нет координат: в Wikidata нет объекта с этим кодом ОКТМО или у него нет координат",
                      name=row["type_abbr"] + " " + name, municipality=item["name"])
            if found and found["population"]:
                entry["population"] = {**found["population"], "via": "wikidata:P1082"}
                counts["with_population"] += 1
            names[(kind, name)] = names.get((kind, name), 0) + 1
            rows_out.append(entry)
        for entry in rows_out:
            entry["same_name_in_municipality"] = names[(entry["type"], entry["name"])] > 1
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
            "admin_centre": record["centre"], "osm_name": item["source"]["name"],
            "osm_relation": item["source"]["osm_relation"], "wikidata": item["source"]["wikidata"],
            "admin_centre_lonlat": [centre["lon"], centre["lat"]] if centre else None,
            "bbox_m": [min(xs), min(ys), max(xs), max(ys)],
            "area_km2": round(polygon_area(item["rings"], ways_m) / 1e6, 1),
            "settlement_count": len(rows_out), "rings": item["rings"]})
    official_codes = {row["oktmo"] for row in oktmo["settlements"]}
    for code in sorted(set(wikidata) - official_codes):
        issue("wikidata_code_not_in_oktmo", code,
              "Объект Wikidata с кодом, которого нет в ОКТМО; в справочник не включён",
              name=wikidata[code]["label"], wikidata=wikidata[code]["qid"])
    current_ids = {e["id"] for e in all_settlements} | {m["id"] for m in municipal_out}
    for key in sorted(registry):
        if key[0] in "SM" and key not in current_ids:
            registry[key]["retired"] = True  # an issued id is never reused or deleted

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
        "actual_state": "перечень, названия, типы и принадлежность: ОКТМО с изменениями, действующими по региону на дату файла; границы: OSM на дату загрузки (см. sources.json)",
        "verification": {
            "settlement_list_source": "ОКТМО ОК 033-2013",
            "oktmo_file_is_rosstat_original": False,
            "oktmo_latest_change_in_region": oktmo["latest_change_in_region"],
            "okato_cross_check": oktmo["okato_cross_check"],
            "registry_of_republic_compared": False,
            "note": "Файл ОКТМО получен с зеркала и побайтно с файлом Росстата не сверен. Реестр РБ (постановление № 391) публично не опубликован и не использовался",
        },
        "comparison_with_wikidata": comparison,
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
