"""SPEND_VS_BUDGET_ANOMALY — yesterday's spend deviates from daily_budget by >20%.

Per SOP Part 7.1. Info/warning-level nudge; not auto-applicable (could be
intentional by ops).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

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

DEVIATION_PCT = 20.0


@register
class SpendVsBudgetAnomalyDetector(Detector):
    rec_type = "SPEND_VS_BUDGET_ANOMALY"

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
            yield DetectorTarget(
                entity_level="campaign",
                entity_id=camp.id,
                account_id=camp.account_id,
                campaign_id=camp.id,
                campaign_type=classify_campaign(camp),
                context={
                    "campaign_name": camp.name,
                    "daily_budget": float(camp.daily_budget or 0),
                },
            )

    def evaluate(self, db: Session, target: DetectorTarget) -> DetectorFinding | None:
        yesterday = date.today() - timedelta(days=1)
        spend_series = daily_metric_series(
            db, target.campaign_id, "spend", days=2, today=yesterday,
        )
        spend_y = float(spend_series.get(yesterday, 0))
        budget = float(target.context.get("daily_budget") or 0)
        if budget <= 0:
            return None
        pct_diff = (spend_y - budget) / budget * 100
        if abs(pct_diff) <= DEVIATION_PCT:
            return None
        return DetectorFinding(
            evidence={
                "yesterday_date": str(yesterday),
                "yesterday_spend": spend_y,
                "daily_budget": budget,
                "pct_diff": pct_diff,
                "threshold_pct": DEVIATION_PCT,
                "campaign_name": target.context.get("campaign_name"),
            },
            metrics_snapshot=snapshot_metrics(db, target.campaign_id, today=yesterday),
        )
