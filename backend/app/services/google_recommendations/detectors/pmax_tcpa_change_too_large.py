"""PMAX_TCPA_CHANGE_TOO_LARGE — recent tCPA change >20% resets learning.

Per SOP Part 3.5 hard rule. Reads action_logs for the last 48 hours and
compares before/after tCPA values stored in action_params.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.action_log import ActionLog
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

WINDOW_HOURS = 48
PCT_LIMIT = 20.0


@register
class PmaxTcpaChangeTooLargeDetector(Detector):
    rec_type = "PMAX_TCPA_CHANGE_TOO_LARGE"

    def scope(self, db: Session, account_ids: list[str] | None = None) -> Iterable[DetectorTarget]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)
        q = (
            db.query(ActionLog, Campaign)
            .join(Campaign, ActionLog.campaign_id == Campaign.id)
            .filter(ActionLog.action == "update_tcpa_target")
            .filter(ActionLog.executed_at >= cutoff)
            .filter(Campaign.platform == "google")
        )
        if account_ids:
            q = q.filter(Campaign.account_id.in_(account_ids))
        for log, camp in q.all():
            if classify_campaign(camp) != "PMAX":
                continue
            yield DetectorTarget(
                entity_level="campaign",
                entity_id=camp.id,
                account_id=camp.account_id,
                campaign_id=camp.id,
                campaign_type="PMAX",
                context={
                    "log_id": log.id,
                    "action_params": log.action_params or {},
                    "campaign_name": camp.name,
                    "executed_at": log.executed_at.isoformat() if log.executed_at else None,
                },
            )

    def evaluate(self, db: Session, target: DetectorTarget) -> DetectorFinding | None:
        params = target.context.get("action_params") or {}
        # Accept either an explicit loosen_pct or a before/after pair.
        loosen_pct = params.get("loosen_pct")
        if loosen_pct is None:
            prev = params.get("previous_tcpa")
            new = params.get("new_tcpa") or (
                params.get("new_tcpa_micros", 0) / 1_000_000 if params.get("new_tcpa_micros") else None
            )
            if not prev or not new or prev == 0:
                return None
            loosen_pct = abs(float(new) - float(prev)) / float(prev) * 100
        else:
            loosen_pct = abs(float(loosen_pct))
        if loosen_pct <= PCT_LIMIT:
            return None
        return DetectorFinding(
            evidence={
                "change_pct": loosen_pct,
                "pct_limit": PCT_LIMIT,
                "campaign_name": target.context.get("campaign_name"),
                "executed_at": target.context.get("executed_at"),
            },
            metrics_snapshot=snapshot_metrics(db, target.campaign_id),
        )
