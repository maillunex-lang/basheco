"""Download and simplify an attributed OSM snapshot for a small central-Ufa demo.

Source: https://www.openstreetmap.org/copyright (ODbL).
No parcel ownership or real estate rights are inferred from OSM geometries.
Run manually; the committed snapshot is a reproducible, dated demo fixture.
"""
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

BBOX = (55.9710, 54.7377, 55.9730, 54.7395)
URL = "https://api.openstreetmap.org/api/0.6/map?bbox=" + ",".join(map(str, BBOX))
CENTER = (55.9720, 54.7386)

def extract(raw: bytes) -> dict:
    root = ET.fromstring(raw)
    nodes = {}
    for node in root.findall("node"):
        nodes[node.attrib["id"]] = (
            round(float(node.attrib["lon"]), 7),
            round(float(node.attrib["lat"]), 7),
        )
    features = []
    for way in root.findall("way"):
        tags = {tag.attrib["k"]: tag.attrib["v"] for tag in way.findall("tag")}
        kind = "road" if "highway" in tags else ("building" if "building" in tags else None)
        if not kind:
            continue
        coords = [nodes[nd.attrib["ref"]] for nd in way.findall("nd") if nd.attrib["ref"] in nodes]
        if len(coords) < (2 if kind == "road" else 4):
            continue
        if kind == "building" and coords[0] != coords[-1]:
            continue
        features.append({
            "osm_id": way.attrib["id"],
            "kind": kind,
            "type": tags.get("highway", tags.get("building", "")),
            "coordinates": coords,
        })
    return {
        "city": "Уфа",
        "source": "OpenStreetMap contributors",
        "license": "ODbL 1.0",
        "attribution": "© OpenStreetMap contributors",
        "source_url": URL,
        "bbox": list(BBOX),
        "center": list(CENTER),
        "downloaded_utc": datetime.now(timezone.utc).isoformat(),
        "features": features,
    }

if __name__ == "__main__":
    with urllib.request.urlopen(URL, timeout=25) as response:
        data = extract(response.read())
    with open(sys.argv[1], "w", encoding="utf-8") as out:
        json.dump(data, out, ensure_ascii=False, separators=(",", ":"))
    print("OSM features:", len(data["features"]), "roads:", sum(x["kind"]=="road" for x in data["features"]), "buildings:", sum(x["kind"]=="building" for x in data["features"]))
