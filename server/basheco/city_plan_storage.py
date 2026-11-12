"""Safe draft-only city plan storage. Never publishes or mutates player assets."""
from __future__ import annotations

from basheco.city_plan import generate, VERSION


def save_draft(settlement_id: str, focus_x: int, focus_y: int, *, dry_run: bool = True) -> dict:
    plan = generate(settlement_id, focus_x, focus_y)
    report = {"settlement_id": settlement_id, "content_hash": plan["content_hash"],
              "objects": len(plan["objects"]), "published": False,
              "dry_run": dry_run}
    if dry_run:
        return report
    from basheco.generated_occupancy import lock_occupancy
    from basheco.db import connect
    from psycopg.types.json import Jsonb
    with connect() as conn:
        lock_occupancy(conn)
        existing = conn.execute(
            "SELECT content_hash FROM city_plan_snapshots WHERE settlement_id=%s FOR UPDATE",
            (settlement_id,)).fetchone()
        if existing:
            if existing["content_hash"] != plan["content_hash"]:
                raise ValueError("Immutable city plan conflict; explicit migration required")
            report["unchanged"] = True
            return report
        # Drafts are intentionally non-authoritative. Publishing needs a separate
        # transactional occupancy and legacy-snapshot migration procedure.
        conn.execute(
            "INSERT INTO city_plan_snapshots"
            "(settlement_id,generator_version,focus_cell_x,focus_cell_y,content_hash,content)"
            " VALUES(%s,%s,%s,%s,%s,%s)",
            (settlement_id, VERSION, focus_x, focus_y, plan["content_hash"], Jsonb(plan)),
        )
        report["unchanged"] = False
    return report