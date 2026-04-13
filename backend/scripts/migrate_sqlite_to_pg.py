"""Migrate all data from SQLite to Supabase PostgreSQL.
Uses batch inserts for speed over network connection.
"""

import json, sys, os
from pathlib import Path

os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=True)

from sqlalchemy import create_engine, text
from app.config import settings

sqlite_engine = create_engine("sqlite:///./ads_platform.db")
pg_engine = create_engine(settings.POSTGRES_CONNECTION_STRING)

TABLES = [
    "ad_accounts", "campaigns", "ad_sets", "ads", "metrics_cache",
    "ad_materials", "ad_angles", "ad_copies", "ad_combos", "branch_keypoints",
    "automation_rules", "action_logs", "ai_conversations",
    "budget_plans", "budget_allocations", "api_keys",
    "video_transcripts",
]


def get_col_types(table):
    with pg_engine.connect() as c:
        rows = c.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name=:t"
        ), {"t": table}).fetchall()
    return {r[0]: r[1] for r in rows}


def fix_val(val, dtype):
    if val is None:
        return None
    if dtype == "boolean":
        return bool(val)
    if dtype in ("json", "jsonb") or isinstance(val, (dict, list)):
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
    return val


def migrate(table):
    from sqlalchemy import inspect as sa_inspect
    if table not in sa_inspect(sqlite_engine).get_table_names():
        print(f"  SKIP {table}", flush=True)
        return 0

    with sqlite_engine.connect() as sc:
        rows = sc.execute(text(f"SELECT * FROM {table}")).fetchall()
        if not rows:
            print(f"  SKIP {table} (empty)", flush=True)
            return 0
        s_cols = list(sc.execute(text(f"SELECT * FROM {table} LIMIT 1")).keys())

    pg_types = get_col_types(table)
    common = [c for c in s_cols if c in pg_types]
    col_str = ", ".join(common)
    val_str = ", ".join(f":{c}" for c in common)
    sql = text(f"INSERT INTO {table} ({col_str}) VALUES ({val_str})")

    # Build all param dicts
    all_params = []
    for row in rows:
        rd = dict(zip(s_cols, row))
        params = {c: fix_val(rd[c], pg_types[c]) for c in common}
        all_params.append(params)

    # Batch insert in single transaction
    ok = 0
    with pg_engine.connect() as pc:
        pc.execute(text(f"DELETE FROM {table}"))
        pc.commit()

        # Insert in batches of 50
        batch_size = 50
        for i in range(0, len(all_params), batch_size):
            batch = all_params[i:i+batch_size]
            try:
                for p in batch:
                    pc.execute(sql, p)
                pc.commit()
                ok += len(batch)
            except Exception as e:
                pc.rollback()
                # Fallback: insert one by one
                for p in batch:
                    try:
                        pc.execute(sql, p)
                        pc.commit()
                        ok += 1
                    except Exception as e2:
                        pc.rollback()
                        if ok == 0:
                            err = str(e2).split('\n')[0][:80]
                            print(f"    ERR: {err}", flush=True)

    print(f"  {table}: {ok}/{len(rows)} rows", flush=True)
    return ok


def main():
    print("SQLite -> Supabase PostgreSQL", flush=True)
    print("=" * 40, flush=True)
    total = 0
    for t in TABLES:
        total += migrate(t)
    print(f"\nTotal: {total} rows migrated", flush=True)


if __name__ == "__main__":
    main()
