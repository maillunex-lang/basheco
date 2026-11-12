"""Explicit maintenance command; run periodically after backup policy review.

Deletes only expired sessions and rate-limit buckets older than 48 hours.
Does not delete immutable financial postings or security audit events.
"""
from basheco.db import connect


def cleanup() -> dict[str, int]:
    with connect() as conn:
        sessions = conn.execute(
            "DELETE FROM sessions WHERE expires_at < now() RETURNING token_hash"
        ).fetchall()
        limits = conn.execute(
            "DELETE FROM request_limits WHERE window_start < now() - interval '48 hours' "
            "RETURNING bucket"
        ).fetchall()
    return {"expired_sessions": len(sessions), "old_rate_limits": len(limits)}


if __name__ == "__main__":
    print(cleanup())
