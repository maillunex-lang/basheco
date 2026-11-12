"""Fetch a small verified SRTM elevation grid via OpenTopoData.

Run manually, not in-game. Public service limits apply. Data is sampled and
attributed; no missing values are fabricated.
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = 'https://api.opentopodata.org/v1/srtm30m'

def fetch_grid(location_id: str, bbox: tuple[float,float,float,float],
               width: int, height: int, output: Path) -> dict:
    if not 2 <= width <= 10 or not 2 <= height <= 10:
        raise ValueError('Grid limited to 100 sample points')
    west, south, east, north = bbox
    if not (west < east and south < north and east-west < 0.05 and north-south < 0.05):
        raise ValueError('Invalid bounds')
    coordinates = [(south + (north-south)*y/(height-1),
                    west + (east-west)*x/(width-1))
                   for y in range(height) for x in range(width)]
    query = urlencode({'locations': '|'.join(f'{lat:.7f},{lon:.7f}' for lat,lon in coordinates)})
    url = ENDPOINT + '?' + query
    with urlopen(Request(url, headers={'User-Agent':'BASHECO-Alpha/0.1 github.com/maillunex-lang/basheco'}),
                 timeout=35) as response:
        data = json.load(response)
    results = data.get('results', [])
    if data.get('status') != 'OK' or len(results) != len(coordinates):
        raise RuntimeError('Elevation service did not return complete grid')
    heights = []
    for (lat, lon), item in zip(coordinates, results):
        position = item.get('location') or {}
        if item.get('dataset') != 'srtm30m' or item.get('elevation') is None:
            raise RuntimeError('Missing or incorrect elevation dataset')
        if abs(position.get('lat',0)-lat) > 0.00001 or abs(position.get('lng',0)-lon) > 0.00001:
            raise RuntimeError('Elevation location mismatch')
        heights.append(float(item['elevation']))
    result = {
        'location_id': location_id, 'dataset': 'srtm30m',
        'provider': 'OpenTopoData', 'source_url': ENDPOINT,
        'downloaded_utc': datetime.now(timezone.utc).isoformat(),
        'unit': 'metres', 'bbox_lonlat': list(bbox), 'width': width,
        'height': height, 'elevations_m': heights,
        'note': 'Sampled SRTM elevation surface; not building heights or cadastral survey.'
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')),
                      encoding='utf-8')
    return result

if __name__ == '__main__':
    if len(sys.argv) != 8:
        raise SystemExit('Usage: python -m basheco.elevation_snapshot LOCATION WEST SOUTH EAST NORTH GRID_SIZE OUTPUT')
    _, location, west, south, east, north, size, output = sys.argv
    result = fetch_grid(location, (float(west),float(south),float(east),float(north)),
                        int(size),int(size),Path(output))
    print(json.dumps({'location_id': location, 'min_m': min(result['elevations_m']),
                      'max_m': max(result['elevations_m'])}))
