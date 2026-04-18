"""CTR_SPIKE_100 — yesterday's CTR >2x 30-day average.

Per SOP Part 7.1. Info — often invalid clicks or odd placement.
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

MIN_IMPRESSIONS_YESTERDAY = 200
SPIKE_FACTOR = 2.0


@register
class CtrSpike100Detector(Detector):
    rec_type = "CTR_SPIKE_100"

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
        yesterday = date.today() - timedelta(days=1)
        month_ago = yesterday - timedelta(days=29)

        yrow = (
            db.query(
                func.coalesce(func.sum(MetricsCache.clicks), 0),
                func.coalesce(func.sum(MetricsCache.impressions), 0),
            )
            .filter(MetricsCache.campaign_id == target.campaign_id)
            .filter(MetricsCache.ad_set_id.is_(None))
            .filter(MetricsCache.ad_id.is_(None))
            .filter(MetricsCache.date == yesterday)
            .one()
        )
        y_clicks, y_impr = int(yrow[0] or 0), int(yrow[1] or 0)
        if y_impr < MIN_IMPRESSIONS_YESTERDAY:
            return None
        y_ctr = y_clicks / y_impr

        mrow = (
            db.query(
                func.coalesce(func.sum(MetricsCache.clicks), 0),
                func.coalesce(func.sum(MetricsCache.impressions), 0),
            )
            .filter(MetricsCache.campaign_id == target.campaign_id)
            .filter(MetricsCache.ad_set_id.is_(None))
            .filter(MetricsCache.ad_id.is_(None))
            .filter(MetricsCache.date >= month_ago)
            .filter(MetricsCache.date < yesterday)
            .one()
        )
        m_clicks, m_impr = int(mrow[0] or 0), int(mrow[1] or 0)
        if m_impr < 500:
            return None
        m_ctr = m_clicks / m_impr
        if m_ctr <= 0:
            return None
        ratio = y_ctr / m_ctr
        if ratio < SPIKE_FACTOR:
            return None
        return DetectorFinding(
            evidence={
                "yesterday_ctr": y_ctr,
                "thirty_day_avg_ctr": m_ctr,
                "ratio": ratio,
                "spike_factor_threshold": SPIKE_FACTOR,
                "yesterday_clicks": y_clicks,
                "yesterday_impressions": y_impr,
                "campaign_name": target.context.get("campaign_name"),
            },
            metrics_snapshot=snapshot_metrics(db, target.campaign_id, today=yesterday),
        )
