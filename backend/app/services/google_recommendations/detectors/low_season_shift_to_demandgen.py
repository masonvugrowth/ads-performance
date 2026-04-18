"""LOW_SEASON_SHIFT_TO_DEMANDGEN — during a low-season event, Demand Gen share is below floor.

Per SOP Part 6. Info-level nudge during Mar + Sep-Oct low seasons: shift
budget toward warm-up (Demand Gen) since conversion intent is thin.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.google_seasonality_event import GoogleSeasonalityEvent
from app.services.google_recommendations.base import (
    Detector,
    DetectorFinding,
    DetectorTarget,
)
from app.services.google_recommendations.registry import register
from app.services.google_recommendations.utils import (
    classify_campaign,
    sum_metric_for_campaign,
)

DEMAND_GEN_FLOOR_PCT = 15.0


def _event_active(event: GoogleSeasonalityEvent, today: date) -> bool:
    try:
        start = date(today.year, event.start_month, event.start_day)
        end_year = today.year if event.end_month >= event.start_month else today.year + 1
        end = date(end_year, event.end_month, event.end_day)
    except ValueError:
        return False
    return start <= today <= end


@register
class LowSeasonShiftToDemandGenDetector(Detector):
    rec_type = "LOW_SEASON_SHIFT_TO_DEMANDGEN"

    def scope(self, db: Session, account_ids: list[str] | None = None) -> Iterable[DetectorTarget]:
        today = date.today()
        low_events = [
            ev for ev in db.query(GoogleSeasonalityEvent).all()
            if ev.event_key.startswith("low_") and _event_active(ev, today)
        ]
        if not low_events:
            return
        q = db.query(Campaign.account_id).filter(Campaign.platform == "google").distinct()
        if account_ids:
            q = q.filter(Campaign.account_id.in_(account_ids))
        for row in q.all():
            yield DetectorTarget(
                entity_level="account",
                entity_id=f"{row[0]}:low_season",
                account_id=row[0],
                context={"event_keys": [ev.event_key for ev in low_events]},
            )

    def evaluate(self, db: Session, target: DetectorTarget) -> DetectorFinding | None:
        total = 0.0
        dg = 0.0
        for camp in (
            db.query(Campaign)
            .filter(Campaign.platform == "google")
            .filter(Campaign.account_id == target.account_id)
            .filter(Campaign.status == "ACTIVE")
            .all()
        ):
            spend_30 = float(sum_metric_for_campaign(db, camp.id, "spend", 30))
            total += spend_30
            if classify_campaign(camp) == "DEMAND_GEN":
                dg += spend_30
        if total <= 0:
            return None
        share_pct = dg / total * 100
        if share_pct >= DEMAND_GEN_FLOOR_PCT:
            return None
        return DetectorFinding(
            evidence={
                "demand_gen_share_pct": share_pct,
                "floor_pct": DEMAND_GEN_FLOOR_PCT,
                "total_spend_30d": total,
                "demand_gen_spend_30d": dg,
                "active_low_season_events": target.context.get("event_keys"),
            },
            metrics_snapshot={"total_spend_30d": total, "demand_gen_spend_30d": dg},
        )
