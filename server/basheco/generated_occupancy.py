"""Transactional occupancy coordination for generated scenery and player parcels.

Callers must acquire this lock before checking or changing world occupancy.
The lock is transaction-scoped, and all checks use one global cell grid.
"""
from __future__ import annotations

from fastapi import HTTPException

OCCUPANCY_LOCK_KEY = 13042026


def lock_occupancy(conn) -> None:
    """Serialize publication, imports, and every supported placement path."""
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (OCCUPANCY_LOCK_KEY,))


def generated_overlap(conn, cell_x: int, cell_y: int, width: int, height: int) -> bool:
    """Does a parcel rectangle overlap any cell in published scenery?"""
    # Migration 015 runs before generated_locations appears in migration 016.
    # Legacy backfills must remain valid on their historical schema.
    if conn.execute("SELECT to_regclass('generated_locations') AS table_name").fetchone()["table_name"] is None:
        return False
    return conn.execute("""
        SELECT 1 FROM generated_locations l
        JOIN generated_location_chunks c USING(settlement_id)
        JOIN LATERAL jsonb_array_elements(c.content) obj ON TRUE
        WHERE l.published
          AND c.chunk_x BETWEEN %s AND %s
          AND c.chunk_y BETWEEN %s AND %s
          AND (obj->'cell'->>0)::bigint >= %s
          AND (obj->'cell'->>0)::bigint < %s
          AND (obj->'cell'->>1)::bigint >= %s
          AND (obj->'cell'->>1)::bigint < %s
        LIMIT 1
    """, (cell_x // 64, (cell_x + width - 1) // 64,
          cell_y // 64, (cell_y + height - 1) // 64,
          cell_x, cell_x + width, cell_y, cell_y + height)).fetchone() is not None


def reject_published_overlap(conn, cell_x: int, cell_y: int,
                             width: int, height: int) -> None:
    if generated_overlap(conn, cell_x, cell_y, width, height):
        raise HTTPException(409, "Parcel overlaps published generated scenery")