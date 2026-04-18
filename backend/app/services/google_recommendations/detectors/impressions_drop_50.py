"""IMPRESSIONS_DROP_50 — last 7 days impressions dropped ≥50% vs prior 7.

Per SOP Part 7.1. Critical — signals bid, budget, or disapproval issue.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.metrics import MetricsCache
from app.services.google_recommendations.base import (
    Detector,
    DetectorFinding,
    DetectorTarget,
)
from app.services.google_recommendations.registry import register
from app.services.google_recommendations.utils import (
    classify_campaign,
    snapshot_metrics,
)

DROP_PCT = 50.0
MIN_PRIOR_IMPRESSIONS = 500  # avoid false positives on tiny-traffic campaigns


def _sum_impressions(db: Session, campaign_id: str, start: date, end: date) -> int:
    return int(
        db.query(func.coalesce(func.sum(MetricsCache.impressions), 0))
        .filter(MetricsCache.campaign_id == campaign_id)
        .filter(MetricsCache.ad_set_id.is_(None))
        .filter(MetricsCache.ad_id.is_(None))
        .filter(MetricsCache.date >= start)
        .filter(MetricsCache.date <= end)
        .scalar() or 0
    )


@register
class ImpressionsDrop50Detector(Detector):
    rec_type = "IMPRESSIONS_DROP_50"

    def scope(self, db: Session, account_ids: list[str] | None = None) -> Iterable[DetectorTarget]:
        q = (
            db.query(Campaign)
            .filter(Campaign.platform == "google")
            .filter(Campaign.status == "ACTIVE")
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
                context={"campaign_name": camp.name},
            )

    def evaluate(self, db: Session, target: DetectorTarget) -> DetectorFinding | None:
        today = date.today()
        recent_start = today - timedelta(days=7)
        prior_start = today - timedelta(days=14)
        prior_end = today - timedelta(days=8)
        recent = _sum_impressions(db, target.campaign_id, recent_start, today - timedelta(days=1))
        prior = _sum_impressions(db, target.campaign_id, prior_start, prior_end)
        if prior < MIN_PRIOR_IMPRESSIONS:
            return None
        drop = (prior - recent) / prior * 100
        if drop < DROP_PCT:
            return None
        return DetectorFinding(
            evidence={
                "recent_7d_impressions": recent,
                "prior_7d_impressions": prior,
                "drop_pct": drop,
                "drop_threshold_pct": DROP_PCT,
                "campaign_name": target.context.get("campaign_name"),
            },
            metrics_snapshot=snapshot_metrics(db, target.campaign_id),
        )
