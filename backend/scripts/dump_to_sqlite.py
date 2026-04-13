"""Dump all data from Supabase PostgreSQL to local SQLite.

Usage:
    cd backend
    python scripts/dump_to_sqlite.py

Creates ads_platform.db in the backend directory.
"""

import sys
from datetime import datetime
from pathlib import Path

# Ensure backend/ is on sys.path so 'app' can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import MetaData, create_engine, event, inspect, text

# Source: Supabase PostgreSQL
PG_URL = "postgresql://postgres.utlmunpccnlvkfulzwfs:Meander2026_.@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"

# Destination: local SQLite
SQLITE_PATH = Path(__file__).resolve().parent.parent / "ads_platform.db"
SQLITE_URL = f"sqlite:///{SQLITE_PATH}"

# Skip these tables
SKIP_TABLES = {"alembic_version"}


def main():
    print(f"Source: Supabase PostgreSQL")
    print(f"Destination: {SQLITE_PATH}")
    print()

    # Connect to PostgreSQL (reflect schema for reading data)
    pg_engine = create_engine(PG_URL)
    pg_meta = MetaData()
    pg_meta.reflect(bind=pg_engine)

    tables = [t for t in pg_meta.tables if t not in SKIP_TABLES]
    print(f"Found {len(tables)} tables to dump")

    # Remove existing SQLite file
    if SQLITE_PATH.exists():
        SQLITE_PATH.unlink()
        print(f"Removed existing {SQLITE_PATH.name}")

    # Create SQLite engine using app's own models (clean schema, no PG-specific defaults)
    sqlite_engine = create_engine(SQLITE_URL, connect_args={"check_same_thread": False})

    @event.listens_for(sqlite_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=OFF")  # OFF during import
        cursor.close()

    # Import ALL app model files so Base.metadata has every table
    from app.models.base import Base
    import app.models  # noqa: F401
    # Also import models that may not be in __init__.py
    import app.models.ad_angle  # noqa: F401
    import app.models.ad_combo  # noqa: F401
    import app.models.ad_copy  # noqa: F401
    import app.models.ad_material  # noqa: F401
    import app.models.keypoint  # noqa: F401
    import app.models.approval  # noqa: F401
    import app.models.campaign_auto_config  # noqa: F401
    import app.models.notification  # noqa: F401
    import app.models.user  # noqa: F401
    import app.models.video_transcript  # noqa: F401

    # Create tables from app models (SQLite-compatible schema)
    Base.metadata.create_all(bind=sqlite_engine)
    print("Created all tables in SQLite from app models")
    print()

    # Now copy data: read from PG reflected tables, write to SQLite
    # We need a separate metadata for SQLite to get the table objects
    sqlite_meta = MetaData()
    sqlite_meta.reflect(bind=sqlite_engine)

    total_rows = 0

    for table_name in sorted(tables):
        pg_table = pg_meta.tables.get(table_name)
        sqlite_table = sqlite_meta.tables.get(table_name)

        if pg_table is None or sqlite_table is None:
            print(f"  SKIP {table_name} (not in both DBs)")
            continue

        # Read all rows from PostgreSQL
        with pg_engine.connect() as pg_conn:
            rows = pg_conn.execute(pg_table.select()).fetchall()

        if not rows:
            print(f"  {table_name}: 0 rows (empty)")
            continue

        # Find common columns and columns only in SQLite (need defaults)
        pg_col_names = [c.name for c in pg_table.columns]
        pg_col_set = set(pg_col_names)
        sqlite_cols = {c.name: c for c in sqlite_table.columns}
        common_cols = [c for c in pg_col_names if c in sqlite_cols]

        # Build defaults for SQLite-only columns (not in PG)
        sqlite_only_defaults = {}
        for col_name, col in sqlite_cols.items():
            if col_name not in pg_col_set:
                if col.default is not None:
                    sqlite_only_defaults[col_name] = col.default.arg if not callable(col.default.arg) else col.default.arg()
                elif col.nullable:
                    sqlite_only_defaults[col_name] = None
                else:
                    # NOT NULL with no default — use type-appropriate zero
                    sqlite_only_defaults[col_name] = 0

        # Insert into SQLite in batches
        with sqlite_engine.begin() as sqlite_conn:
            batch = []
            for row in rows:
                values = dict(sqlite_only_defaults)
                for col_name in common_cols:
                    idx = pg_col_names.index(col_name)
                    val = row[idx]
                    if isinstance(val, datetime) and val.tzinfo is not None:
                        val = val.replace(tzinfo=None)
                    values[col_name] = val
                batch.append(values)

            if batch:
                sqlite_conn.execute(sqlite_table.insert(), batch)

        total_rows += len(rows)
        print(f"  {table_name}: {len(rows)} rows")

    print()
    print(f"Done! {total_rows} total rows dumped to {SQLITE_PATH.name}")
    print(f"File size: {SQLITE_PATH.stat().st_size / 1024 / 1024:.1f} MB")

    pg_engine.dispose()
    sqlite_engine.dispose()


if __name__ == "__main__":
    main()
