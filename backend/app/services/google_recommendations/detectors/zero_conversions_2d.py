"""ZERO_CONVERSIONS_2D — Two consecutive days with zero conversions + non-zero spend.

Per SOP Part 7: indicates broken conversion tag or landing page change. Urgent
manual check.
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


@register
class ZeroConversions2DDetector(Detector):
    rec_type = "ZERO_CONVERSIONS_2D"

    def scope(
        self, db: Session, account_ids: list[str] | None = None,
    ) -> Iterable[DetectorTarget]:
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

    def evaluate(
        self, db: Session, target: DetectorTarget,
    ) -> DetectorFinding | None:
        today = date.today()
        yesterday = today - timedelta(days=1)
        day_before = today - timedelta(days=2)

        spend_series = daily_metric_series(db, target.campaign_id, "spend", days=3, today=yesterday)
        conv_series = daily_metric_series(db, target.campaign_id, "conversions", days=3, today=yesterday)

        spend_y = float(spend_series.get(yesterday, 0))
        spend_d = float(spend_series.get(day_before, 0))
        conv_y = float(conv_series.get(yesterday, 0))
        conv_d = float(conv_series.get(day_before, 0))

        if spend_y <= 0 or spend_d <= 0:
            return None
        if conv_y > 0 or conv_d > 0:
            return None

        return DetectorFinding(
            evidence={
                "yesterday_date": str(yesterday),
                "day_before_date": str(day_before),
                "yesterday_spend": spend_y,
                "day_before_spend": spend_d,
                "yesterday_conversions": conv_y,
                "day_before_conversions": conv_d,
                "campaign_name": target.context.get("campaign_name"),
            },
            metrics_snapshot=snapshot_metrics(db, target.campaign_id, today=yesterday),
        )
