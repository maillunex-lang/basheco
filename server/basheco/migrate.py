"""Apply each numbered SQL migration once under a transaction."""
from pathlib import Path
from basheco.db import connect

def main():
    files = sorted((Path(__file__).resolve().parent.parent / "sql").glob("[0-9]*.sql"))
    with connect() as conn:
        with conn.transaction():
            conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
            applied = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
            for f in files:
                if f.name not in applied:
                    conn.execute(f.read_text(encoding="utf-8"))
                    conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (f.name,))
                    print("Applied migration", f.name, flush=True)
    print("Migrations complete", flush=True)

if __name__ == "__main__":
    main()
