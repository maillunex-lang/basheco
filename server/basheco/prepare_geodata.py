"""Convert an existing licensed OSM snapshot into metre-based, clipped visual chunks.

Usage: python -m basheco.prepare_geodata INPUT_MANIFEST OUTPUT_DIR
Does not download external sources or create any gameplay/cadastral plots.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from basheco.geodata import LocalProjection, clipped_linestring

CHUNK_METRES = 64.0
SUPPORTED = {'road', 'building', 'water', 'forest', 'farmland'}


def prepare(manifest_path: Path, output_dir: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    bbox = manifest['bbox']
    if len(bbox) != 4 or bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
        raise ValueError('Invalid source bbox')
    projection = LocalProjection((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
    # Only use geometry fully contained in this small snapshot. Clipping roads
    # handles crossings without the previous "all points must be inside" bug.
    corners = [projection.project(bbox[0], bbox[1]), projection.project(bbox[2], bbox[3])]
    west, east = sorted((corners[0][0], corners[1][0]))
    north, south = sorted((corners[0][1], corners[1][1]))
    clip_bbox = (west, north, east, south)
    seen = set()
    out = {}
    counts = {}
    for item in manifest['chunks']:
        source = item['path']
        if not source.startswith('res://data/ufa_chunks/') or '..' in source:
            raise ValueError('Unexpected source path')
        filename = source.rsplit('/', 1)[-1]
        data = json.loads((manifest_path.parent / filename).read_text(encoding='utf-8'))
        for feature in data.get('features', []):
            kind = feature.get('kind')
            fid = (kind, str(feature.get('osm_id')))
            if kind not in SUPPORTED or fid in seen:
                continue
            seen.add(fid)
            coords = feature.get('coordinates', [])
            if len(coords) < 2:
                continue
            projected = [projection.project(float(c[0]), float(c[1])) for c in coords]
            if kind == 'road':
                segments = clipped_linestring(projected, clip_bbox)
                for a, b in segments:
                    midpoint = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                    key = (int(midpoint[0] // CHUNK_METRES), int(midpoint[1] // CHUNK_METRES))
                    out.setdefault(key, []).append({'id': fid[1], 'kind': kind,
                                                     'points_m': [list(a), list(b)]})
                    counts[kind] = counts.get(kind, 0) + 1
            else:
                # Keep polygon geometry only if entirely inside the snapshot.
                # Real polygon clipping and multi-chunk coverage are future work.
                if not all(west <= x <= east and north <= y <= south for x, y in projected):
                    continue
                cx = sum(p[0] for p in projected) / len(projected)
                cy = sum(p[1] for p in projected) / len(projected)
                key = (int(cx // CHUNK_METRES), int(cy // CHUNK_METRES))
                out.setdefault(key, []).append({'id': fid[1], 'kind': kind,
                                                 'points_m': [list(p) for p in projected]})
                counts[kind] = counts.get(kind, 0) + 1
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks = []
    for (cx, cy), features in sorted(out.items()):
        filename = f'chunk_{cx}_{cy}.json'
        (output_dir / filename).write_text(json.dumps({'features': features},
                    ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        chunks.append({'x': cx, 'y': cy, 'path': filename, 'feature_count': len(features)})
    result = {'location_id': 'ufa', 'status': 'pilot_snapshot_not_full_city',
              'source_url': manifest.get('source_url'),
              'source_downloaded_utc': manifest.get('downloaded_utc'),
              'attribution': manifest.get('attribution'), 'license': manifest.get('license'),
              'projection': 'local_equirectangular_metres', 'origin_lon': projection.origin_lon,
              'origin_lat': projection.origin_lat, 'chunk_metres': CHUNK_METRES,
              'bounds_m': list(clip_bbox), 'feature_counts': counts, 'chunks': chunks}
    (output_dir / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                                encoding='utf-8')
    return result


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: python -m basheco.prepare_geodata INPUT_MANIFEST OUTPUT_DIR')
    result = prepare(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps({'status': result['status'], 'feature_counts': result['feature_counts'],
                      'chunk_count': len(result['chunks'])}, ensure_ascii=False))
