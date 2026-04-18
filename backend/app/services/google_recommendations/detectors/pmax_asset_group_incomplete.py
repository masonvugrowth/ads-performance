"""PMAX_ASSET_GROUP_INCOMPLETE — PMax asset group below SOP minimums.

Per SOP Part 3.3. Counts images/logos/videos/headlines/descriptions per asset
group and flags anything under the minimum.
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import func
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

SOP_MIN = {
    "IMAGE": 2,      # landscape + square
    "LOGO": 1,
    "VIDEO": 1,
    "HEADLINE": 3,   # short headlines
    "DESCRIPTION": 2,
}


@register
class PmaxAssetGroupIncompleteDetector(Detector):
    rec_type = "PMAX_ASSET_GROUP_INCOMPLETE"

    def scope(self, db: Session, account_ids: list[str] | None = None) -> Iterable[DetectorTarget]:
        q = (
            db.query(GoogleAssetGroup, Campaign)
            .join(Campaign, GoogleAssetGroup.campaign_id == Campaign.id)
            .filter(GoogleAssetGroup.status == "ACTIVE")
            .filter(Campaign.platform == "google")
            .filter(Campaign.status == "ACTIVE")
        )
        if account_ids:
            q = q.filter(GoogleAssetGroup.account_id.in_(account_ids))
        for ag, camp in q.all():
            if classify_campaign(camp) != "PMAX":
                continue
            yield DetectorTarget(
                entity_level="asset_group",
                entity_id=ag.id,
                account_id=ag.account_id,
                campaign_id=camp.id,
                asset_group_id=ag.id,
                campaign_type="PMAX",
                context={
                    "campaign_name": camp.name,
                    "asset_group_name": ag.name,
                },
            )

    def evaluate(self, db: Session, target: DetectorTarget) -> DetectorFinding | None:
        counts_rows = (
            db.query(GoogleAsset.asset_type, func.count(GoogleAsset.id))
            .filter(GoogleAsset.asset_group_id == target.asset_group_id)
            .group_by(GoogleAsset.asset_type)
            .all()
        )
        counts = {row[0]: int(row[1]) for row in counts_rows}
        deficits: dict[str, dict[str, int]] = {}
        for asset_type, minimum in SOP_MIN.items():
            have = counts.get(asset_type, 0)
            if have < minimum:
                deficits[asset_type] = {"have": have, "min": minimum}
        if not deficits:
            return None
        return DetectorFinding(
            evidence={
                "asset_counts": counts,
                "deficits": deficits,
                "sop_minimums": SOP_MIN,
                "asset_group_name": target.context.get("asset_group_name"),
                "campaign_name": target.context.get("campaign_name"),
            },
            metrics_snapshot=snapshot_metrics(db, target.campaign_id) if target.campaign_id else {},
        )
