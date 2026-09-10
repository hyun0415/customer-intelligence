"""Apply ordered, idempotent database migrations from the backend image."""

from pathlib import Path

from src.database import connect

MIGRATION_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"


def apply_migrations() -> None:
    migration_files = sorted(MIGRATION_DIR.glob("*.sql"))
    if not migration_files:
        raise RuntimeError(f"migration 파일이 없습니다: {MIGRATION_DIR}")

    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied = {
            row["filename"]
            for row in conn.execute("SELECT filename FROM schema_migrations")
        }

        for path in migration_files:
            if path.name in applied:
                continue
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"), prepare=False)
                conn.execute(
                    "INSERT INTO schema_migrations (filename) VALUES (%s)",
                    (path.name,),
                )
            print(f"applied: {path.name}", flush=True)


if __name__ == "__main__":
    apply_migrations()
