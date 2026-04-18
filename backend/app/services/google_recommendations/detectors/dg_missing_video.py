"""DG_MISSING_VIDEO — Demand Gen / PMax campaigns with no video asset.

Per SOP Part 1.3: if no video is uploaded, Google auto-generates a poor-quality
video that hurts brand. Guidance-only detector — cannot auto-upload.
"""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.google_asset import GoogleAsset
from app.models.google_asset_group import GoogleAssetGroup
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
class DGMissingVideoDetector(Detector):
    rec_type = "DG_MISSING_VIDEO"

    def scope(
        self, db: Session, account_ids: list[str] | None = None,
    ) -> Iterable[DetectorTarget]:
        q = (
            db.query(GoogleAssetGroup, Campaign)
            .join(Campaign, GoogleAssetGroup.campaign_id == Campaign.id)
            .filter(Campaign.platform == "google")
            .filter(Campaign.status == "ACTIVE")
            .filter(GoogleAssetGroup.status == "ACTIVE")
        )
        if account_ids:
            q = q.filter(GoogleAssetGroup.account_id.in_(account_ids))
        for ag, camp in q.all():
            campaign_type = classify_campaign(camp)
            if campaign_type not in ("PMAX", "DEMAND_GEN"):
                continue
            yield DetectorTarget(
                entity_level="asset_group",
                entity_id=ag.id,
                account_id=ag.account_id,
                campaign_id=camp.id,
                asset_group_id=ag.id,
                campaign_type=campaign_type,
                context={"campaign_name": camp.name, "asset_group_name": ag.name},
            )

    def evaluate(
        self, db: Session, target: DetectorTarget,
    ) -> DetectorFinding | None:
        video_count = (
            db.query(GoogleAsset)
            .filter(GoogleAsset.asset_group_id == target.asset_group_id)
            .filter(GoogleAsset.asset_type == "VIDEO")
            .count()
        )
        if video_count >= 1:
            return None
        evidence: dict[str, Any] = {
            "video_count": video_count,
            "sop_minimum": 1,
            "asset_group_name": target.context.get("asset_group_name"),
            "campaign_name": target.context.get("campaign_name"),
        }
        return DetectorFinding(
            evidence=evidence,
            metrics_snapshot=snapshot_metrics(db, target.campaign_id) if target.campaign_id else {},
        )
