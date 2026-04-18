"""BUDGET_MIX_OFF_TARGET — account's 30-day budget split deviates from SOP bands.

Per SOP Part 6.1. Emits one recommendation per account (entity_level='account').
Auto-action: update each active campaign's daily_budget pro-rata to bring the
mix into SOP bands while keeping the total unchanged.

An account is treated as "new" (<6 months old) if the oldest active Google
campaign start_date is within the last 180 days.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.services.google_recommendations.base import (
    Detector,
    DetectorFinding,
    DetectorTarget,
)
from app.services.google_recommendations.registry import register
from app.services.google_recommendations.utils import (
    classify_campaign,
    sum_metric_for_campaign,
)

# Target mid-band percentages per SOP Part 6.1.
SOP_BANDS_NEW = {
    "BRANDED_SEARCH": (10, 15),
    "SEARCH": (30, 40),           # non-branded (branded separated below)
    "PMAX": (40, 50),
    "DEMAND_GEN": (10, 15),
}
SOP_BANDS_STABLE = {
    "BRANDED_SEARCH": (5, 10),
    "SEARCH": (25, 35),
    "PMAX": (40, 50),
    "DEMAND_GEN": (15, 20),
}
DEVIATION_TOLERANCE_PP = 5  # percentage points — ignore drift within tolerance


def _account_age_days(db: Session, account_id: str, today: date) -> int | None:
    oldest = (
        db.query(Campaign.start_date)
        .filter(Campaign.platform == "google")
        .filter(Campaign.account_id == account_id)
        .filter(Campaign.start_date.isnot(None))
        .order_by(Campaign.start_date.asc())
        .first()
    )
    if not oldest or not oldest[0]:
        return None
    return (today - oldest[0]).days


def _sop_bands_for_account(age_days: int | None) -> dict[str, tuple[int, int]]:
    if age_days is not None and age_days < 180:
        return SOP_BANDS_NEW
    return SOP_BANDS_STABLE


def _campaign_bucket(camp: Campaign) -> str | None:
    """Return the budget-mix bucket for a campaign."""
    ctype = classify_campaign(camp)
    if ctype is None:
        return None
    if ctype == "SEARCH":
        # Naive branded vs non-branded split based on name tokens.
        if camp.name and "brand" in camp.name.lower():
            return "BRANDED_SEARCH"
        return "SEARCH"
    if ctype in ("PMAX", "DEMAND_GEN"):
        return ctype
    return None


@register
class BudgetMixOffTargetDetector(Detector):
    rec_type = "BUDGET_MIX_OFF_TARGET"

    def scope(
        self, db: Session, account_ids: list[str] | None = None,
    ) -> Iterable[DetectorTarget]:
        q = db.query(Campaign.account_id).filter(Campaign.platform == "google").distinct()
        if account_ids:
            q = q.filter(Campaign.account_id.in_(account_ids))
        for row in q.all():
            acc_id = row[0]
            yield DetectorTarget(
                entity_level="account",
                entity_id=acc_id,
                account_id=acc_id,
                context={},
            )

    def evaluate(
        self, db: Session, target: DetectorTarget,
    ) -> DetectorFinding | None:
        today = date.today()
        age = _account_age_days(db, target.account_id, today)
        bands = _sop_bands_for_account(age)

        campaigns = (
            db.query(Campaign)
            .filter(Campaign.platform == "google")
            .filter(Campaign.account_id == target.account_id)
            .filter(Campaign.status == "ACTIVE")
            .all()
        )

        totals: dict[str, Decimal] = {k: Decimal("0") for k in bands}
        per_campaign: dict[str, list[dict[str, Any]]] = {k: [] for k in bands}
        grand_total = Decimal("0")

        for camp in campaigns:
            bucket = _campaign_bucket(camp)
            if bucket not in bands:
                continue
            spend_30 = sum_metric_for_campaign(db, camp.id, "spend", 30, today)
            totals[bucket] += spend_30
            grand_total += spend_30
            per_campaign[bucket].append(
                {
                    "campaign_id": camp.id,
                    "name": camp.name,
                    "daily_budget": float(camp.daily_budget) if camp.daily_budget else 0,
                    "spend_30d": float(spend_30),
                },
            )

        if grand_total <= 0:
            return None

        current_pct: dict[str, float] = {
            k: float(totals[k] / grand_total * 100) for k in bands
        }
        deviations: dict[str, dict[str, float]] = {}
        needs_action = False
        for bucket, (lo, hi) in bands.items():
            cur = current_pct[bucket]
            if cur < lo - DEVIATION_TOLERANCE_PP or cur > hi + DEVIATION_TOLERANCE_PP:
                needs_action = True
                deviations[bucket] = {
                    "current_pct": cur,
                    "target_low": lo,
                    "target_high": hi,
                    "target_mid": (lo + hi) / 2,
                }

        if not needs_action:
            return None

        evidence: dict[str, Any] = {
            "account_age_days": age,
            "account_maturity": "new" if age is not None and age < 180 else "stable",
            "current_mix_pct": current_pct,
            "sop_bands": {k: list(v) for k, v in bands.items()},
            "deviations": deviations,
            "campaigns_by_bucket": per_campaign,
            "grand_total_30d_spend": float(grand_total),
        }
        return DetectorFinding(
            evidence=evidence,
            metrics_snapshot={"grand_total_spend_30d": float(grand_total)},
            action_kwargs={
                "account_id": target.account_id,
                "target_mid_pct": {k: (lo + hi) / 2 for k, (lo, hi) in bands.items()},
                "current_daily_budgets": {
                    camp["campaign_id"]: camp["daily_budget"]
                    for bucket in per_campaign.values()
                    for camp in bucket
                },
            },
        )

    def build_action(
        self, target: DetectorTarget, finding: DetectorFinding,
    ) -> dict[str, Any]:
        # Applier computes per-campaign new daily_budgets from current totals;
        # here we only pass the intent.
        return {
            "function": "rebalance_budget_mix",
            "kwargs": {
                "account_id": target.account_id,
                "target_mid_pct": finding.action_kwargs["target_mid_pct"],
            },
        }
