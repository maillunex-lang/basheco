"""Immutable, unpublished-by-default scenery snapshots. No player data mutation."""
from __future__ import annotations
import hashlib
import json
from collections import Counter, defaultdict

from basheco.location_generator import LIMIT, PILOT, SCHEMA
from basheco.world_grid import cell_to_chunk


def prepare(bundle: dict) -> list[dict]:
    if bundle.get("schema") != SCHEMA or bundle.get("generator_version") != 1:
        raise ValueError("Unsupported generated bundle")
    selected = bundle["selection"]
    locations = bundle["locations"]
    if len(selected) != len(locations):
        raise ValueError("Missing generated location")
    lookup = {s["settlement_id"]: s for s in selected}
    if len(lookup) != len(selected):
        raise ValueError("Duplicate settlement")
    counts = Counter(s["municipality_id"] for s in selected)
    if any(n > LIMIT for n in counts.values()):
        raise ValueError("More than five candidates in municipality")
    if bundle.get("published_settlement_ids") != [PILOT]:
        raise ValueError("Unexpected publication plan")
    result = []
    occupied_global = set()
    for loc in locations:
        sid = loc["settlement_id"]
        if sid not in lookup or loc.get("version") != 1:
            raise ValueError("Unknown generated location")
        if loc.get("cell_size_m") != 6 or loc.get("chunk_size_cells") != 64:
            raise ValueError("Grid mismatch")
        chunks = defaultdict(list)
        for obj in loc["objects"]:
            x, y = obj["cell"]
            w, h = obj["size"]
            if obj["kind"] not in ("house", "road") or min(w, h) < 1:
                raise ValueError("Invalid generated object")
            for xx in range(x, x + w):
                for yy in range(y, y + h):
                    if (xx, yy) in occupied_global:
                        raise ValueError("Overlapping generated cells")
                    occupied_global.add((xx, yy))
                    chunks[cell_to_chunk(xx, yy)].append({
                        "kind": obj["kind"], "cell": [xx, yy],
                        "origin": obj["cell"], "size": obj["size"]})
        digest = hashlib.sha256(json.dumps(loc, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":")).encode()).hexdigest()
        result.append({"id": sid, "municipality": lookup[sid]["municipality_id"],
                       "version": loc["version"], "hash": digest, "chunks": chunks})
    return result


def import_unpublished(bundle: dict, dry_run: bool = True) -> dict:
    """Never replace existing snapshots; no automatic publication."""
    prepared = prepare(bundle)
    report = {"candidates": len(prepared), "inserted": 0, "unchanged": 0, "dry_run": dry_run}
    if dry_run:
        return report
    from basheco.db import connect
    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (13042026,))
        for item in prepared:
            row = conn.execute("SELECT content_hash FROM generated_locations WHERE settlement_id=%s FOR UPDATE", (item["id"],)).fetchone()
            if row:
                if row["content_hash"] != item["hash"]:
                    raise ValueError("Immutable snapshot conflict: " + item["id"])
                report["unchanged"] += 1
                continue
            conn.execute("INSERT INTO generated_locations(settlement_id,municipality_id,generator_version,content_hash) VALUES(%s,%s,%s,%s)",
                         (item["id"], item["municipality"], item["version"], item["hash"]))
            for (cx, cy), objects in item["chunks"].items():
                conn.execute("INSERT INTO generated_location_chunks(settlement_id,chunk_x,chunk_y,content) VALUES(%s,%s,%s,%s::jsonb)",
                             (item["id"], cx, cy, json.dumps(objects)))
            report["inserted"] += 1
    return report


def published_locations() -> list[dict]:
    from basheco.db import connect
    with connect() as conn:
        return conn.execute("SELECT settlement_id,municipality_id,generator_version FROM generated_locations WHERE published ORDER BY municipality_id,settlement_id").fetchall()


def published_chunk(settlement_id: str, chunk_x: int, chunk_y: int) -> dict | None:
    from basheco.db import connect
    with connect() as conn:
        row = conn.execute("SELECT c.content,l.generator_version FROM generated_location_chunks c JOIN generated_locations l USING(settlement_id) WHERE c.settlement_id=%s AND c.chunk_x=%s AND c.chunk_y=%s AND l.published",
                           (settlement_id, chunk_x, chunk_y)).fetchone()
    if not row:
        return None
    return {"settlement_id": settlement_id, "chunk": [chunk_x, chunk_y],
            "generator_version": row["generator_version"], "objects": row["content"]}

def publish_location(settlement_id: str) -> dict:
    """Explicit publication, serialized against importer; never edits player assets.

    Fail closed when generated cells overlap existing player plots or objects.
    This check does not protect against future concurrent placement operations;
    those must acquire the same lock or check published scenery occupancy.
    """
    if settlement_id != PILOT:
        raise ValueError("Only the approved pilot may be published in this stage")
    from basheco.db import connect
    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (13042026,))
        location = conn.execute(
            "SELECT published FROM generated_locations WHERE settlement_id=%s FOR UPDATE",
            (settlement_id,),
        ).fetchone()
        if location is None:
            raise ValueError("Generated location is not imported")
        if location["published"]:
            return {"settlement_id": settlement_id, "published": True, "unchanged": True}
        # Global grid player plots use half-open cell rectangles.
        conflict = conn.execute("""
            SELECT 1 FROM generated_location_chunks c
            JOIN LATERAL jsonb_array_elements(c.content) obj ON true
            JOIN world_plots p ON p.world_cell_x IS NOT NULL
                AND (obj->'cell'->>0)::bigint >= p.world_cell_x
                AND (obj->'cell'->>0)::bigint < p.world_cell_x + p.width_tiles
                AND (obj->'cell'->>1)::bigint >= p.world_cell_y
                AND (obj->'cell'->>1)::bigint < p.world_cell_y + p.height_tiles
            WHERE c.settlement_id=%s LIMIT 1
        """, (settlement_id,)).fetchone()
        if conflict:
            raise ValueError("Generated scenery overlaps a player plot")
        conflict = conn.execute("""
            SELECT 1 FROM generated_location_chunks c
            JOIN LATERAL jsonb_array_elements(c.content) obj ON true
            JOIN world_object_cells p
                ON p.cell_x=(obj->'cell'->>0)::bigint
                AND p.cell_y=(obj->'cell'->>1)::bigint
            WHERE c.settlement_id=%s LIMIT 1
        """, (settlement_id,)).fetchone()
        if conflict:
            raise ValueError("Generated scenery overlaps a player-owned object")
        conn.execute(
            "UPDATE generated_locations SET published=true WHERE settlement_id=%s",
            (settlement_id,),
        )
    return {"settlement_id": settlement_id, "published": True, "unchanged": False}