"""Offline OSM XML -> WGS84 source snapshot for the single BASHECO world atlas.

Usage:
  python -m basheco.import_osm_xml --input /data/extract.osm --source-id sterlitamak-osm \
      --location sterlitamak --source-url https://api.openstreetmap.org/api/0.6/map?bbox=... \
      --downloaded-utc 2026-11-12T00:00:00Z --geodata server/geodata
  python -m basheco.world_atlas          # rebuild client/data/world in EPSG:32640

There is no --origin argument any more: a settlement has no origin of its own.
Every source is projected by pyproj into the one world grid (EPSG:32640, 6 m
cells, 64x64 chunks). Register the new source under its settlement in
geodata/settlements.json before rebuilding. This tool never downloads anything.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from basheco.osm_source import normalise, write


def convert(input_file: Path, geodata_dir: Path, source_id: str, location: str,
            source_url: str, downloaded_utc: str) -> dict:
    if not input_file.is_file():
        raise FileNotFoundError(input_file)
    snapshot = normalise(input_file, source_id, location, source_url, downloaded_utc)
    write(snapshot, geodata_dir / "sources" / f"{source_id}.json")
    return snapshot


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--geodata", type=Path, required=True)
    p.add_argument("--source-id", required=True)
    p.add_argument("--location", required=True)
    p.add_argument("--source-url", required=True)
    p.add_argument("--downloaded-utc", required=True)
    a = p.parse_args()
    snapshot = convert(a.input, a.geodata, a.source_id, a.location, a.source_url, a.downloaded_utc)
    print(json.dumps({"features": len(snapshot["features"]), "kinds": snapshot["feature_counts"],
                      "skipped": snapshot["skipped"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
