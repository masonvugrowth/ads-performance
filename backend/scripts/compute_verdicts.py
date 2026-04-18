"""Compute verdict for all combos, then propagate to copies/materials/angles."""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import text
from app.database import SessionLocal
from app.services.creative_service import auto_classify_all_combos

db = SessionLocal()
try:
    updated = auto_classify_all_combos(db)
    print(f"Updated combos: {updated}")

    # Show summary
    print("\n=== Verdict distribution after classification ===")
    for table, col in [
        ('ad_combos', 'verdict'),
        ('ad_copies', 'derived_verdict'),
        ('ad_materials', 'derived_verdict'),
        ('ad_angles', 'status'),
    ]:
        rows = db.execute(text(f'SELECT {col}, COUNT(*) FROM {table} GROUP BY {col} ORDER BY 2 DESC')).fetchall()
        print(f'  {table:15} {dict(rows)}')

    # Benchmarks per branch
    print("\n=== Branch ROAS benchmarks ===")
    rows = db.execute(text('''
        SELECT a.account_name, COALESCE(SUM(c.spend),0) spend, COALESCE(SUM(c.revenue),0) rev,
               CASE WHEN SUM(c.spend)>0 THEN SUM(c.revenue)/SUM(c.spend) ELSE 0 END roas
        FROM ad_accounts a LEFT JOIN ad_combos c ON c.branch_id=a.id
        WHERE a.platform='meta' GROUP BY a.account_name ORDER BY spend DESC
    ''')).fetchall()
    for r in rows:
        print(f'  {r[0]:25} spend={float(r[1]):>12,.0f} | rev={float(r[2]):>12,.0f} | benchmark ROAS={float(r[3]):.2f}x')
finally:
    db.close()
