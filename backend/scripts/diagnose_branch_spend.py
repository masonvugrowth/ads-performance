"""Diagnose budget vs actual spend per (branch, platform, month) for 2026.

Why this exists: user reported Google spend in /budget looks too low. The
budget dashboard's `_get_actual_spend()` joins accounts to a branch via
ilike substring match against `BRANCH_ACCOUNT_MAP[branch]` patterns, so an
account named "MS Google" or "Saigon Hotel - GA" instead of the expected
"Meander Saigon" / "Saigon" can silently fall out of the totals.

This script prints, for every (platform, branch) pair:
  - which AdAccounts matched the branch patterns
  - per-month spend from metrics_cache (campaign-level only — same filter
    the dashboard uses)
And lists every active AdAccount that did NOT map to any branch — those
are the candidates for renaming or for adding to BRANCH_ACCOUNT_MAP.

Usage:
    cd backend && python -m scripts.diagnose_branch_spend [--month 2]
"""
import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func

from app.core.branches import BRANCH_ACCOUNT_MAP, BRANCH_CURRENCY
from app.database import SessionLocal
from app.models.account import AdAccount
from app.models.campaign import Campaign
from app.models.metrics import MetricsCache
from app.services.budget_service import _get_account_ids_for_branch


YEAR = 2026


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", type=int, default=None,
                        help="Single month (1-12) — default prints all 12")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        # 1) All active accounts (id, platform, currency, name)
        all_accounts = (
            db.query(AdAccount)
            .filter(AdAccount.is_active.is_(True))
            .order_by(AdAccount.platform, AdAccount.account_name)
            .all()
        )
        print(f"\n=== Active AdAccounts ({len(all_accounts)}) ===")
        mapped_account_ids: set[str] = set()
        for a in all_accounts:
            print(f"  [{a.platform:6}] {a.account_name!r:55} id={a.account_id} curr={a.currency}")

        # 2) Per-branch matched accounts
        print(f"\n=== Branch -> matched account_ids ===")
        for branch in BRANCH_ACCOUNT_MAP:
            ids = _get_account_ids_for_branch(db, branch)
            mapped_account_ids.update(ids)
            matches = [a for a in all_accounts if str(a.id) in ids]
            print(f"\n  {branch} (currency={BRANCH_CURRENCY.get(branch, '?')}, patterns={BRANCH_ACCOUNT_MAP[branch]}):")
            if not matches:
                print(f"    !! NO MATCHES — every AdAccount whose name doesn't contain "
                      f"any of the patterns above is invisible to /budget for this branch.")
                continue
            for m in matches:
                print(f"    [{m.platform:6}] {m.account_name!r}")

        # 3) Unmapped accounts — orphans
        orphans = [a for a in all_accounts if str(a.id) not in mapped_account_ids]
        if orphans:
            print(f"\n=== ORPHAN accounts (matched 0 branches) — {len(orphans)} ===")
            for a in orphans:
                print(f"  [{a.platform:6}] {a.account_name!r:55} id={a.account_id}")
        else:
            print(f"\n=== ORPHAN accounts: none ===")

        # 4) Per (branch, platform, month) spend totals — same filter as dashboard
        months_to_show = [args.month] if args.month else list(range(1, 13))
        print(f"\n=== Per-(branch, platform, month) campaign-level spend, {YEAR} ===")
        print(f"   (same filter as /budget/dashboard: ad_set_id IS NULL, platform=channel)")

        for branch in BRANCH_ACCOUNT_MAP:
            ids = _get_account_ids_for_branch(db, branch)
            if not ids:
                continue
            print(f"\n  {branch}:")
            # Per-platform per-month
            for platform in ("meta", "google", "tiktok"):
                rows = (
                    db.query(
                        func.extract("month", MetricsCache.date).label("m"),
                        func.sum(MetricsCache.spend).label("s"),
                    )
                    .join(Campaign, Campaign.id == MetricsCache.campaign_id)
                    .filter(
                        Campaign.account_id.in_(ids),
                        MetricsCache.platform == platform,
                        func.extract("year", MetricsCache.date) == YEAR,
                        MetricsCache.ad_set_id.is_(None),
                    )
                    .group_by(func.extract("month", MetricsCache.date))
                    .all()
                )
                spend_by_month = {int(r.m): float(r.s or 0) for r in rows}
                if not spend_by_month:
                    continue
                pieces = []
                for m in months_to_show:
                    s = spend_by_month.get(m, 0)
                    if s > 0:
                        pieces.append(f"M{m:02d}={s:>14,.0f}")
                if pieces:
                    print(f"    {platform:6}: {'  '.join(pieces)} ({BRANCH_CURRENCY.get(branch, '?')})")

        # 5) Per-account direct spend for the requested month — sanity check
        if args.month:
            print(f"\n=== Per-account spend for {YEAR}-{args.month:02d} (campaign-level) ===")
            rows = (
                db.query(
                    AdAccount.account_name,
                    AdAccount.platform,
                    AdAccount.currency,
                    func.sum(MetricsCache.spend).label("s"),
                )
                .join(Campaign, Campaign.account_id == AdAccount.id)
                .join(MetricsCache, MetricsCache.campaign_id == Campaign.id)
                .filter(
                    func.extract("year", MetricsCache.date) == YEAR,
                    func.extract("month", MetricsCache.date) == args.month,
                    MetricsCache.ad_set_id.is_(None),
                    AdAccount.is_active.is_(True),
                )
                .group_by(AdAccount.id, AdAccount.account_name, AdAccount.platform, AdAccount.currency)
                .order_by(AdAccount.platform, AdAccount.account_name)
                .all()
            )
            for r in rows:
                print(f"  [{r.platform:6}] {r.account_name!r:55} {float(r.s or 0):>14,.0f} {r.currency}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
