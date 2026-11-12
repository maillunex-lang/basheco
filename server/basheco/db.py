"""PostgreSQL connection: callers use one transaction per operation."""
import os
import psycopg
from psycopg.rows import dict_row

def connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required")
    return psycopg.connect(url, row_factory=dict_row, connect_timeout=5)
