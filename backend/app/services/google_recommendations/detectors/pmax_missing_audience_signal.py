"""PMAX_MISSING_AUDIENCE_SIGNAL — PMax asset group has no audience signal.

Per SOP Part 3.4. PMax learns faster when each asset group is seeded with at
least one audience signal (Customer Match, remarketing list, custom-intent,
lookalike, or search theme). Guidance-only — attaching a signal requires
choosing the right audience, which is a judgment call.
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from app.models.campaign import Campaign
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
class PmaxMissingAudienceSignalDetector(Detector):
    rec_type = "PMAX_MISSING_AUDIENCE_SIGNAL"

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
                    "raw_data": ag.raw_data or {},
                },
            )

    def evaluate(self, db: Session, target: DetectorTarget) -> DetectorFinding | None:
        raw = target.context.get("raw_data") or {}
        signals = raw.get("audience_signals")
        # If the sync engine has never populated the signals key, skip rather
        # than fire a false positive — the absence means "unknown", not "zero".
        if signals is None:
            return None
        if len(signals) > 0:
            return None
        return DetectorFinding(
            evidence={
                "signal_count": 0,
                "asset_group_name": target.context.get("asset_group_name"),
                "campaign_name": target.context.get("campaign_name"),
            },
            metrics_snapshot=snapshot_metrics(db, target.campaign_id) if target.campaign_id else {},
        )
