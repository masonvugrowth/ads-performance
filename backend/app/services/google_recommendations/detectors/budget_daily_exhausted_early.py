"""BUDGET_DAILY_EXHAUSTED_EARLY — PMax daily spend ≥90% of daily_budget on 3+ of last 7 days.

Per SOP Part 6.2. Heuristic: we don't have hourly spend from Google Ads API —
this detector flags campaigns whose DAILY spend repeatedly hits the cap,
indicating budget is too low for the current tCPA.

Auto-action: raise daily budget by 20%.
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
    daily_metric_series,
    snapshot_metrics,
)

WINDOW_DAYS = 7
HIT_THRESHOLD_PCT = 90.0
MIN_HIT_DAYS = 3
BUMP_PCT = 20.0


@register
class BudgetDailyExhaustedEarlyDetector(Detector):
    rec_type = "BUDGET_DAILY_EXHAUSTED_EARLY"

    def scope(self, db: Session, account_ids: list[str] | None = None) -> Iterable[DetectorTarget]:
        q = (
            db.query(Campaign)
            .filter(Campaign.platform == "google")
            .filter(Campaign.status == "ACTIVE")
            .filter(Campaign.daily_budget.isnot(None))
        )
        if account_ids:
            q = q.filter(Campaign.account_id.in_(account_ids))
        for camp in q.all():
            if classify_campaign(camp) != "PMAX":
                continue
            yield DetectorTarget(
                entity_level="campaign",
                entity_id=camp.id,
                account_id=camp.account_id,
                campaign_id=camp.id,
                campaign_type="PMAX",
                context={
                    "campaign_name": camp.name,
                    "daily_budget": float(camp.daily_budget),
                },
            )

    def evaluate(self, db: Session, target: DetectorTarget) -> DetectorFinding | None:
        budget = float(target.context.get("daily_budget") or 0)
        if budget <= 0:
            return None
        series = daily_metric_series(
            db, target.campaign_id, "spend",
            days=WINDOW_DAYS, today=date.today() - timedelta(days=1),
        )
        hit_days = [d for d, v in series.items() if float(v) >= budget * (HIT_THRESHOLD_PCT / 100)]
        if len(hit_days) < MIN_HIT_DAYS:
            return None
        new_daily = budget * (1 + BUMP_PCT / 100)
        return DetectorFinding(
            evidence={
                "daily_budget": budget,
                "hit_days_count": len(hit_days),
                "hit_days": [str(d) for d in hit_days],
                "hit_threshold_pct": HIT_THRESHOLD_PCT,
                "window_days": WINDOW_DAYS,
                "recommended_new_daily_budget": new_daily,
                "bump_pct": BUMP_PCT,
                "campaign_name": target.context.get("campaign_name"),
            },
            metrics_snapshot=snapshot_metrics(db, target.campaign_id),
            action_kwargs={
                "campaign_id": target.campaign_id,
                "new_daily_budget": new_daily,
            },
        )

    def build_action(self, target: DetectorTarget, finding: DetectorFinding) -> dict[str, Any]:
        return {
            "function": "update_campaign_budget",
            "kwargs": {
                "campaign_id": target.campaign_id,
                "new_daily_budget": finding.action_kwargs["new_daily_budget"],
            },
        }
