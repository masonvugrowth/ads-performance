"""PMAX_MISSING_BRAND_EXCLUSION — PMax campaign has no Brand Exclusion list.

Per SOP Part 2.4 / Part 3.6. Without a Brand Exclusion list, PMax will
cannibalize branded Search traffic and ROAS will look artificially inflated.
The fix is operator-driven (pick the right brand terms and attach the
asset set in Google Ads UI) so this is guidance-only.

Depends on google_sync_engine persisting has_brand_exclusion in Campaign.raw_data.
"""

from __future__ import annotations

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
    snapshot_metrics,
)


@register
class PmaxMissingBrandExclusionDetector(Detector):
    rec_type = "PMAX_MISSING_BRAND_EXCLUSION"

    def scope(self, db: Session, account_ids: list[str] | None = None) -> Iterable[DetectorTarget]:
        q = (
            db.query(Campaign)
            .filter(Campaign.platform == "google")
            .filter(Campaign.status == "ACTIVE")
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
                    "raw_data": camp.raw_data or {},
                },
            )

    def evaluate(self, db: Session, target: DetectorTarget) -> DetectorFinding | None:
        raw = target.context.get("raw_data") or {}
        # Treat missing key as "unknown" — only fire when sync engine explicitly
        # reports the campaign has no brand exclusion list attached.
        if "has_brand_exclusion" not in raw:
            return None
        if raw.get("has_brand_exclusion"):
            return None
        return DetectorFinding(
            evidence={
                "has_brand_exclusion": False,
                "campaign_name": target.context.get("campaign_name"),
            },
            metrics_snapshot=snapshot_metrics(db, target.campaign_id) if target.campaign_id else {},
        )
