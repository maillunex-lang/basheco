"""Convert a bounded OSM API XML extract to a provenance-labelled visual atlas.

Download separately and respect OSM API usage policy. This script does not
synthesize missing forests, water, buildings, roads or elevation.
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree
from basheco.geodata import LocalProjection, clipped_linestring, clip_polygon

def classify(tags: dict[str, str]) -> str | None:
    if 'waterway' in tags or tags.get('natural') == 'water' or 'water' in tags:
        return 'water'
    if tags.get('natural') == 'wood' or tags.get('landuse') == 'forest':
        return 'forest'
    if tags.get('landuse') in ('farmland', 'farmyard', 'meadow'):
        return 'farmland'
    if 'building' in tags:
        return 'building'
    if 'highway' in tags:
        return 'road'
    return None

def build_atlas(xml_file: Path, location_id: str, output_file: Path) -> dict:
    if not location_id or not all(c.islower() or c.isdigit() or c in '_-' for c in location_id):
        raise ValueError('Invalid location ID')
    tree = ElementTree.parse(xml_file)
    root = tree.getroot()
    bounds = root.find('bounds')
    if bounds is None:
        raise ValueError('OSM bounds missing')
    west, south, east, north = (float(bounds.get(k)) for k in ('minlon','minlat','maxlon','maxlat'))
    if not (west < east and south < north and east - west <= 0.05 and north - south <= 0.05):
        raise ValueError('Invalid or too large OSM extract')
    projection = LocalProjection((west + east) / 2, (south + north) / 2)
    nodes = {n.get('id'): (float(n.get('lon')), float(n.get('lat')))
             for n in root.findall('node')}
    corners = (projection.project(west, north), projection.project(east, south))
    clip = (corners[0][0], corners[0][1], corners[1][0], corners[1][1])
    features = []
    counts = {}
    for way in root.findall('way'):
        tags = {tag.get('k'): tag.get('v') for tag in way.findall('tag')}
        kind = classify(tags)
        if kind is None:
            continue
        refs = [ref.get('ref') for ref in way.findall('nd')]
        if len(refs) < 2 or any(ref not in nodes for ref in refs):
            continue
        points = [projection.project(*nodes[ref]) for ref in refs]
        if kind in ('road', 'water') and (kind == 'road' or 'waterway' in tags):
            geometry = [[list(a), list(b)] for a, b in clipped_linestring(points, clip)]
        else:
            clipped = clip_polygon(points, clip) if len(points) >= 3 else []
            geometry = [list(map(list, clipped))] if clipped else []
        for geom in geometry:
            if len(geom) < 2:
                continue
            features.append({'id': str(way.get('id')), 'kind': kind, 'points_m': geom})
            counts[kind] = counts.get(kind, 0) + 1
    result = {'manifest': {
        'location_id': location_id, 'status': 'pilot_snapshot_not_full_settlement',
        'source_url': f'https://api.openstreetmap.org/api/0.6/map?bbox={west},{south},{east},{north}',
        'source_downloaded_utc': datetime.now(timezone.utc).isoformat(),
        'attribution': '© OpenStreetMap contributors', 'license': 'ODbL 1.0',
        'projection': 'local_equirectangular_metres',
        'origin_lon': projection.origin_lon, 'origin_lat': projection.origin_lat,
        'bounds_m': list(clip), 'feature_counts': counts,
        'elevation_source': None, 'elevation_status': 'not_available'
    }, 'features': features}
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')),
                           encoding='utf-8')
    return result

if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit('Usage: python -m basheco.osm_snapshot INPUT.osm LOCATION_ID OUTPUT.json')
    atlas = build_atlas(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]))
    print(json.dumps({'features': len(atlas['features']),
                      'kinds': atlas['manifest']['feature_counts']}, ensure_ascii=False))
