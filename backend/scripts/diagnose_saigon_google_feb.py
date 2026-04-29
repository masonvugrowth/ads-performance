"""Deep-dive on Saigon Google spend for Feb 2026 — drill into metrics_cache.

User reported Google spend looks too low for Saigon Feb 2026. The basic
diagnostic confirmed the account name maps correctly and the campaign-
level total = 40,900,496 VND. This script shows:
  - per-day spend across the month
  - per-campaign spend (with names)
  - row counts at each granularity (campaign / ad-set / ad)
  - sum at each granularity to surface a sync gap (e.g. only ad-group
    level was synced and campaign-level rows are missing for some days)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func

from app.database import SessionLocal
from app.models.account import AdAccount
from app.models.campaign import Campaign
from app.models.metrics import MetricsCache


SAIGON_GOOGLE_ACCOUNT_NAME = "MEANDER Saigon"


def main() -> None:
    db = SessionLocal()
    try:
        acc = (
            db.query(AdAccount)
            .filter(AdAccount.account_name == SAIGON_GOOGLE_ACCOUNT_NAME, AdAccount.platform == "google")
            .first()
        )
        if not acc:
            print(f"NOT FOUND: account_name={SAIGON_GOOGLE_ACCOUNT_NAME} platform=google")
            return
        print(f"Account: {acc.account_name} (id={acc.id}, platform={acc.platform}, currency={acc.currency})")

        # Campaign list under this account
        campaigns = db.query(Campaign).filter(Campaign.account_id == acc.id).all()
        print(f"\n{len(campaigns)} campaigns under this account")
        camp_ids = [c.id for c in campaigns]

        # Row counts at each level (whole Feb)
        from datetime import date
        start, end = date(2026, 2, 1), date(2026, 2, 28)

        campaign_lvl = (
            db.query(func.count().label("n"), func.sum(MetricsCache.spend).label("s"))
            .filter(
                MetricsCache.campaign_id.in_(camp_ids),
                MetricsCache.platform == "google",
                MetricsCache.date >= start,
                MetricsCache.date <= end,
                MetricsCache.ad_set_id.is_(None),
                MetricsCache.ad_id.is_(None),
            )
            .first()
        )
        adset_lvl = (
            db.query(func.count().label("n"), func.sum(MetricsCache.spend).label("s"))
            .filter(
                MetricsCache.campaign_id.in_(camp_ids),
                MetricsCache.platform == "google",
                MetricsCache.date >= start,
                MetricsCache.date <= end,
                MetricsCache.ad_set_id.isnot(None),
                MetricsCache.ad_id.is_(None),
            )
            .first()
        )
        ad_lvl = (
            db.query(func.count().label("n"), func.sum(MetricsCache.spend).label("s"))
            .filter(
                MetricsCache.campaign_id.in_(camp_ids),
                MetricsCache.platform == "google",
                MetricsCache.date >= start,
                MetricsCache.date <= end,
                MetricsCache.ad_id.isnot(None),
            )
            .first()
        )
        print(f"\n=== metrics_cache row counts + spend totals (Feb 2026) ===")
        print(f"  campaign-level (ad_set_id IS NULL, ad_id IS NULL): {campaign_lvl.n} rows, sum={float(campaign_lvl.s or 0):,.0f}")
        print(f"  ad-group level (ad_set_id set, ad_id IS NULL):     {adset_lvl.n} rows, sum={float(adset_lvl.s or 0):,.0f}")
        print(f"  ad-level (ad_id set):                              {ad_lvl.n} rows, sum={float(ad_lvl.s or 0):,.0f}")

        # Per-day spend (campaign-level only — what dashboard sees)
        print(f"\n=== Per-day campaign-level spend in Feb 2026 ===")
        per_day = (
            db.query(MetricsCache.date.label("d"), func.sum(MetricsCache.spend).label("s"))
            .filter(
                MetricsCache.campaign_id.in_(camp_ids),
                MetricsCache.platform == "google",
                MetricsCache.date >= start,
                MetricsCache.date <= end,
                MetricsCache.ad_set_id.is_(None),
            )
            .group_by(MetricsCache.date)
            .order_by(MetricsCache.date)
            .all()
        )
        for r in per_day:
            print(f"  {r.d.isoformat()}: {float(r.s or 0):>14,.0f} VND")
        print(f"  --- Total: {sum(float(r.s or 0) for r in per_day):,.0f} VND across {len(per_day)} days")

        # Per-campaign spend (campaign-level only)
        print(f"\n=== Per-campaign spend in Feb 2026 (campaign-level rows only) ===")
        per_camp = (
            db.query(
                Campaign.name,
                Campaign.status,
                func.sum(MetricsCache.spend).label("s"),
                func.count(MetricsCache.id).label("n"),
            )
            .join(MetricsCache, MetricsCache.campaign_id == Campaign.id)
            .filter(
                Campaign.account_id == acc.id,
                MetricsCache.platform == "google",
                MetricsCache.date >= start,
                MetricsCache.date <= end,
                MetricsCache.ad_set_id.is_(None),
            )
            .group_by(Campaign.id, Campaign.name, Campaign.status)
            .order_by(func.sum(MetricsCache.spend).desc())
            .all()
        )
        for r in per_camp:
            print(f"  [{r.status:6}] {(r.name or '')[:60]:60} {float(r.s or 0):>14,.0f} VND ({r.n} days)")

        # ALL campaigns (incl. ones with 0 spend) — to confirm sync coverage
        print(f"\n=== All campaigns in this account ({len(campaigns)} total) ===")
        for c in sorted(campaigns, key=lambda x: x.name or ""):
            n_metrics = (
                db.query(func.count(MetricsCache.id))
                .filter(
                    MetricsCache.campaign_id == c.id,
                    MetricsCache.date >= start,
                    MetricsCache.date <= end,
                    MetricsCache.ad_set_id.is_(None),
                )
                .scalar() or 0
            )
            print(f"  [{c.status:6}] {(c.name or '')[:55]:55} feb_rows={n_metrics}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
