"""Download one bounded OSM extract (manual step, respects the OSM API usage policy).

Usage: python tools/import_osm.py WEST,SOUTH,EAST,NORTH OUTPUT.osm
Then:  python -m basheco.import_osm_xml --input OUTPUT.osm ...   (see that module)

Source and licence: https://www.openstreetmap.org/copyright (ODbL 1.0).
The raw XML contains contributor metadata and must not be committed; only the
normalised snapshot produced by basheco.import_osm_xml is stored in the repository.
"""
import sys
import urllib.request

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    west, south, east, north = (float(v) for v in sys.argv[1].split(","))
    if not (west < east and south < north and (east - west) * (north - south) <= 0.25):
        raise SystemExit("Invalid or too large bbox for the OSM API")
    url = f"https://api.openstreetmap.org/api/0.6/map?bbox={west},{south},{east},{north}"
    request = urllib.request.Request(url, headers={"User-Agent": "osm-extract-tool/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response, open(sys.argv[2], "wb") as out:
        out.write(response.read())
    print("Saved", sys.argv[2], "from", url)
