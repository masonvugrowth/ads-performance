"""DG_CTR_BELOW_BENCHMARK — Demand Gen CTR below 0.5% over 14 days.

Per SOP Part 1.5. Info-only nudge to A/B test creative.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
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

CTR_BENCHMARK = 0.005  # 0.5%


@register
class DgCtrBelowBenchmarkDetector(Detector):
    rec_type = "DG_CTR_BELOW_BENCHMARK"

    def scope(self, db: Session, account_ids: list[str] | None = None) -> Iterable[DetectorTarget]:
        q = (
            db.query(Campaign)
            .filter(Campaign.platform == "google")
            .filter(Campaign.status == "ACTIVE")
        )
        if account_ids:
            q = q.filter(Campaign.account_id.in_(account_ids))
        for camp in q.all():
            if classify_campaign(camp) != "DEMAND_GEN":
                continue
            yield DetectorTarget(
                entity_level="campaign",
                entity_id=camp.id,
                account_id=camp.account_id,
                campaign_id=camp.id,
                campaign_type="DEMAND_GEN",
                context={"campaign_name": camp.name},
            )

    def evaluate(self, db: Session, target: DetectorTarget) -> DetectorFinding | None:
        cutoff = date.today() - timedelta(days=14)
        row = (
            db.query(
                func.coalesce(func.sum(MetricsCache.clicks), 0),
                func.coalesce(func.sum(MetricsCache.impressions), 0),
            )
            .filter(MetricsCache.campaign_id == target.campaign_id)
            .filter(MetricsCache.ad_set_id.is_(None))
            .filter(MetricsCache.ad_id.is_(None))
            .filter(MetricsCache.date >= cutoff)
            .one()
        )
        clicks = int(row[0] or 0)
        impressions = int(row[1] or 0)
        if impressions < 500:
            return None  # not enough data
        ctr = clicks / impressions
        if ctr >= CTR_BENCHMARK:
            return None
        return DetectorFinding(
            evidence={
                "ctr_14d": ctr,
                "ctr_benchmark": CTR_BENCHMARK,
                "clicks_14d": clicks,
                "impressions_14d": impressions,
                "campaign_name": target.context.get("campaign_name"),
            },
            metrics_snapshot=snapshot_metrics(db, target.campaign_id),
        )
