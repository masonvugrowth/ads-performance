"""PMAX_LEARNING_STUCK — PMax campaign has been in learning >4 weeks.

Heuristic (SOP Part 3.5): campaign age ≥28 days AND total conversions in the
last 30 days < 30 (the SOP lifecycle threshold for stable performance).
When triggered, auto-action is to loosen tCPA by +25% (see build_action).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.services.google_recommendations.base import (
    Detector,
    DetectorFinding,
    DetectorTarget,
)
from app.services.google_recommendations.registry import register
from app.services.google_recommendations.utils import (
    campaign_age_days,
    classify_campaign,
    snapshot_metrics,
    sum_metric_for_campaign,
)

LEARNING_PHASE_DAYS = 28
MIN_CONV_FOR_STABLE = 30
TCPA_LOOSEN_PCT = 25  # percent


@register
class PmaxLearningStuckDetector(Detector):
    rec_type = "PMAX_LEARNING_STUCK"

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
                    "start_date": str(camp.start_date) if camp.start_date else None,
                    "daily_budget": float(camp.daily_budget) if camp.daily_budget else None,
                    "raw_data": camp.raw_data or {},
                },
            )

    def evaluate(
        self, db: Session, target: DetectorTarget,
    ) -> DetectorFinding | None:
        age = None
        start = target.context.get("start_date")
        if start:
            age = (date.today() - date.fromisoformat(start)).days
        if age is None or age < LEARNING_PHASE_DAYS:
            return None

        conv_30 = float(sum_metric_for_campaign(db, target.campaign_id, "conversions", 30))
        if conv_30 >= MIN_CONV_FOR_STABLE:
            return None

        evidence: dict[str, Any] = {
            "campaign_age_days": age,
            "conversions_30d": conv_30,
            "min_conversions_for_stable": MIN_CONV_FOR_STABLE,
            "campaign_name": target.context.get("campaign_name"),
        }

        # Pull current tCPA (if any) from raw_data; fall back to CPA.
        raw = target.context.get("raw_data") or {}
        bidding = raw.get("bidding_strategy") or {}
        current_tcpa = bidding.get("target_cpa_micros")
        if current_tcpa:
            current_tcpa = float(current_tcpa) / 1_000_000
        else:
            # Derive from actual CPA over 30 days as fallback.
            spend_30 = float(sum_metric_for_campaign(db, target.campaign_id, "spend", 30))
            current_tcpa = (spend_30 / conv_30) if conv_30 > 0 else None

        new_tcpa = None
        if current_tcpa:
            new_tcpa = float(Decimal(str(current_tcpa)) * Decimal("1.25"))

        return DetectorFinding(
            evidence=evidence,
            metrics_snapshot=snapshot_metrics(db, target.campaign_id),
            action_kwargs={
                "campaign_id": target.campaign_id,
                "current_tcpa": current_tcpa,
                "new_tcpa": new_tcpa,
                "loosen_pct": TCPA_LOOSEN_PCT,
            },
        )

    def build_action(
        self, target: DetectorTarget, finding: DetectorFinding,
    ) -> dict[str, Any]:
        return {
            "function": "update_tcpa_target",
            "kwargs": {
                "campaign_id": target.campaign_id,
                "new_tcpa_micros": (
                    int(finding.action_kwargs["new_tcpa"] * 1_000_000)
                    if finding.action_kwargs.get("new_tcpa")
                    else None
                ),
                "loosen_pct": TCPA_LOOSEN_PCT,
            },
        }
