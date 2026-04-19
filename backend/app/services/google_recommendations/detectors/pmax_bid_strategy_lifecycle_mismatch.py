"""PMAX_BID_STRATEGY_LIFECYCLE_MISMATCH — bid strategy doesn't match campaign age.

Per SOP Part 3.5 lifecycle:
    week 1-2   → MAXIMIZE_CONVERSIONS (no tCPA)
    week 3-6   → MAXIMIZE_CONVERSIONS_WITH_TCPA at actual CPA + 25%
    month 2-3  → MAXIMIZE_CONVERSIONS_WITH_TCPA at actual CPA
    month 4+   → MAXIMIZE_CONVERSION_VALUE_WITH_TROAS at actual ROAS × 1.0

Auto-applicable: calls switch_bid_strategy with computed targets. Warning
surfaces that the learning phase will reset for 1–2 weeks.
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
    classify_campaign,
    snapshot_metrics,
    sum_metric_for_campaign,
)


def _recommended_strategy(
    age_days: int,
    actual_cpa: float | None,
    actual_roas: float | None,
) -> dict[str, Any] | None:
    """Return {strategy, target_cpa_micros, target_roas, bucket} or None."""
    if age_days < 14:
        return {
            "strategy": "MAXIMIZE_CONVERSIONS",
            "target_cpa_micros": None,
            "target_roas": None,
            "bucket": "week_1_2",
        }
    if age_days < 42:  # week 3-6
        if actual_cpa is None or actual_cpa <= 0:
            return None
        tcpa = float(Decimal(str(actual_cpa)) * Decimal("1.25"))
        return {
            "strategy": "MAXIMIZE_CONVERSIONS_WITH_TCPA",
            "target_cpa_micros": int(tcpa * 1_000_000),
            "target_roas": None,
            "bucket": "week_3_6",
        }
    if age_days < 90:  # month 2-3
        if actual_cpa is None or actual_cpa <= 0:
            return None
        return {
            "strategy": "MAXIMIZE_CONVERSIONS_WITH_TCPA",
            "target_cpa_micros": int(actual_cpa * 1_000_000),
            "target_roas": None,
            "bucket": "month_2_3",
        }
    # month 4+
    if actual_roas is None or actual_roas <= 0:
        return None
    return {
        "strategy": "MAXIMIZE_CONVERSION_VALUE_WITH_TROAS",
        "target_cpa_micros": None,
        "target_roas": round(float(actual_roas), 2),
        "bucket": "month_4_plus",
    }


@register
class PmaxBidStrategyLifecycleMismatchDetector(Detector):
    rec_type = "PMAX_BID_STRATEGY_LIFECYCLE_MISMATCH"

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
            # Prefer campaign.start_date when populated; otherwise fall back to
            # Campaign.created_at (first sync time). The fallback underestimates
            # age for campaigns older than the first sync — acceptable because
            # the detector is WARN-level and the operator can override.
            effective_start = camp.start_date
            if effective_start is None and camp.created_at is not None:
                effective_start = camp.created_at.date()
            if effective_start is None:
                continue
            yield DetectorTarget(
                entity_level="campaign",
                entity_id=camp.id,
                account_id=camp.account_id,
                campaign_id=camp.id,
                campaign_type="PMAX",
                context={
                    "campaign_name": camp.name,
                    "start_date": effective_start.isoformat(),
                    "start_date_is_fallback": camp.start_date is None,
                    "raw_data": camp.raw_data or {},
                },
            )

    def evaluate(self, db: Session, target: DetectorTarget) -> DetectorFinding | None:
        start_str = target.context.get("start_date")
        raw = target.context.get("raw_data") or {}
        current_strategy = raw.get("bidding_strategy_type")
        # If sync engine has never populated bidding_strategy_type, skip rather
        # than fire a false positive.
        if not current_strategy:
            return None

        age_days = (date.today() - date.fromisoformat(start_str)).days
        spend_30 = float(sum_metric_for_campaign(db, target.campaign_id, "spend", 30))
        conv_30 = float(sum_metric_for_campaign(db, target.campaign_id, "conversions", 30))
        rev_30 = float(sum_metric_for_campaign(db, target.campaign_id, "revenue", 30))
        actual_cpa = (spend_30 / conv_30) if conv_30 > 0 else None
        actual_roas = (rev_30 / spend_30) if spend_30 > 0 else None

        rec = _recommended_strategy(age_days, actual_cpa, actual_roas)
        if rec is None:
            return None

        # Decide whether current strategy is out of sync with the recommended bucket.
        # Normalize variants: MAXIMIZE_CONVERSIONS + tCPA hint vs pure MaxConversions.
        current_tcpa_micros = raw.get("target_cpa_micros")
        current_troas = raw.get("target_roas")
        if rec["bucket"] == "week_1_2":
            mismatched = not (
                current_strategy == "MAXIMIZE_CONVERSIONS" and not current_tcpa_micros
            )
        elif rec["bucket"] in ("week_3_6", "month_2_3"):
            mismatched = not (
                current_strategy == "MAXIMIZE_CONVERSIONS" and current_tcpa_micros
            )
        else:  # month_4_plus
            mismatched = not (
                current_strategy == "MAXIMIZE_CONVERSION_VALUE" and current_troas
            )
        if not mismatched:
            return None

        return DetectorFinding(
            evidence={
                "campaign_age_days": age_days,
                "lifecycle_bucket": rec["bucket"],
                "current_strategy": current_strategy,
                "current_target_cpa_micros": current_tcpa_micros,
                "current_target_roas": current_troas,
                "recommended_strategy": rec["strategy"],
                "recommended_target_cpa_micros": rec["target_cpa_micros"],
                "recommended_target_roas": rec["target_roas"],
                "actual_cpa_30d": actual_cpa,
                "actual_roas_30d": actual_roas,
                "campaign_name": target.context.get("campaign_name"),
            },
            metrics_snapshot=snapshot_metrics(db, target.campaign_id),
            action_kwargs={
                "campaign_id": target.campaign_id,
                "new_strategy": rec["strategy"],
                "target_cpa_micros": rec["target_cpa_micros"],
                "target_roas": rec["target_roas"],
            },
        )

    def build_action(
        self, target: DetectorTarget, finding: DetectorFinding,
    ) -> dict[str, Any]:
        return {
            "function": "switch_bid_strategy",
            "kwargs": {
                "campaign_id": target.campaign_id,
                "new_strategy": finding.action_kwargs.get("new_strategy"),
                "target_cpa_micros": finding.action_kwargs.get("target_cpa_micros"),
                "target_roas": finding.action_kwargs.get("target_roas"),
            },
        }
