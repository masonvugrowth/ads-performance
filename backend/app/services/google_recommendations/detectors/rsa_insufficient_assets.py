"""RSA_INSUFFICIENT_ASSETS — RSA has <8 headlines or <3 descriptions.

Per SOP Part 2.5. Manual guidance — the detector doesn't write back to the ad.
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from app.models.ad import Ad
from app.models.campaign import Campaign
from app.services.google_recommendations.base import (
    Detector,
    DetectorFinding,
    DetectorTarget,
)
from app.services.google_recommendations.registry import register
from app.services.google_recommendations.utils import classify_campaign

MIN_HEADLINES = 8
MIN_DESCRIPTIONS = 3


@register
class RsaInsufficientAssetsDetector(Detector):
    rec_type = "RSA_INSUFFICIENT_ASSETS"

    def scope(self, db: Session, account_ids: list[str] | None = None) -> Iterable[DetectorTarget]:
        q = (
            db.query(Ad, Campaign)
            .join(Campaign, Ad.campaign_id == Campaign.id)
            .filter(Campaign.platform == "google")
            .filter(Ad.status == "ACTIVE")
            .filter(Campaign.status == "ACTIVE")
        )
        if account_ids:
            q = q.filter(Ad.account_id.in_(account_ids))
        for ad, camp in q.all():
            if classify_campaign(camp) != "SEARCH":
                continue
            raw = ad.raw_data or {}
            if raw.get("ad_type") != "RESPONSIVE_SEARCH_AD":
                # Still emit if ad_type is unknown but headlines exist —
                # google_client stores `ad_type` as the enum name.
                if not raw.get("headlines"):
                    continue
            yield DetectorTarget(
                entity_level="ad",
                entity_id=ad.id,
                account_id=ad.account_id,
                campaign_id=camp.id,
                ad_group_id=ad.ad_set_id,
                ad_id=ad.id,
                campaign_type="SEARCH",
                context={
                    "ad_name": ad.name,
                    "headlines": raw.get("headlines") or [],
                    "descriptions": raw.get("descriptions") or [],
                },
            )

    def evaluate(self, db: Session, target: DetectorTarget) -> DetectorFinding | None:
        headlines = target.context.get("headlines") or []
        descriptions = target.context.get("descriptions") or []
        if len(headlines) >= MIN_HEADLINES and len(descriptions) >= MIN_DESCRIPTIONS:
            return None
        return DetectorFinding(
            evidence={
                "headline_count": len(headlines),
                "description_count": len(descriptions),
                "min_headlines": MIN_HEADLINES,
                "min_descriptions": MIN_DESCRIPTIONS,
                "ad_name": target.context.get("ad_name"),
            },
            metrics_snapshot={},
        )
