"""PMAX_COUNT_VS_SCALE — active PMax campaign count doesn't match hotel scale.

Per SOP Part 3.2. Small properties (≤30 rooms) run 1 PMax; mid (31-80) run
2-3; large (81+) run 4+. One rec per account when the count is off by more
than one in either direction. Guidance-only — splitting/consolidating
campaigns is structural and the operator should do it manually.

Scale lookup is hardcoded per ad_account name. Update here (not in a DB
table) — this is a stable, branch-level fact that almost never changes.
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from app.models.account import AdAccount
from app.models.campaign import Campaign
from app.services.google_recommendations.base import (
    Detector,
    DetectorFinding,
    DetectorTarget,
)
from app.services.google_recommendations.registry import register
from app.services.google_recommendations.utils import classify_campaign


# MEANDER branch room counts — edit this map when properties open/close/expand.
# Keys are case-insensitive substrings matched against AdAccount.account_name.
HOTEL_SCALE: dict[str, int] = {
    "meander saigon": 42,
    "meander taipei": 30,
    "meander 1948": 26,
    "meander osaka": 54,
    "oani": 18,
}


def _expected_pmax_count(rooms: int) -> tuple[int, int]:
    """Return (min, max) recommended number of PMax campaigns for a hotel size."""
    if rooms <= 30:
        return (1, 1)
    if rooms <= 80:
        return (2, 3)
    return (4, 6)


def _lookup_room_count(account_name: str | None) -> int | None:
    if not account_name:
        return None
    lower = account_name.lower()
    for key, count in HOTEL_SCALE.items():
        if key in lower:
            return count
    return None


@register
class PmaxCountVsScaleDetector(Detector):
    rec_type = "PMAX_COUNT_VS_SCALE"

    def scope(self, db: Session, account_ids: list[str] | None = None) -> Iterable[DetectorTarget]:
        q = db.query(AdAccount).filter(AdAccount.platform == "google").filter(AdAccount.is_active.is_(True))
        if account_ids:
            q = q.filter(AdAccount.id.in_(account_ids))
        for acct in q.all():
            rooms = _lookup_room_count(acct.account_name)
            if rooms is None:
                continue
            yield DetectorTarget(
                entity_level="account",
                entity_id=acct.id,
                account_id=acct.id,
                context={
                    "account_name": acct.account_name,
                    "rooms": rooms,
                },
            )

    def evaluate(self, db: Session, target: DetectorTarget) -> DetectorFinding | None:
        rooms = target.context["rooms"]
        min_n, max_n = _expected_pmax_count(rooms)
        pmax_count = 0
        for camp in (
            db.query(Campaign)
            .filter(Campaign.account_id == target.account_id)
            .filter(Campaign.platform == "google")
            .filter(Campaign.status == "ACTIVE")
            .all()
        ):
            if classify_campaign(camp) == "PMAX":
                pmax_count += 1
        if min_n <= pmax_count <= max_n:
            return None
        direction = "too_few" if pmax_count < min_n else "too_many"
        return DetectorFinding(
            evidence={
                "account_name": target.context.get("account_name"),
                "rooms": rooms,
                "active_pmax_count": pmax_count,
                "recommended_min": min_n,
                "recommended_max": max_n,
                "direction": direction,
            },
            metrics_snapshot={},
        )
