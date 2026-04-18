"""CONV_ADS_VS_PMS_DELTA — Ads-reported bookings vs PMS actuals differ >15% over 30d.

Per SOP Part 4.4. Reads reservations (booking source-of-truth) and compares
total against metrics_cache.conversions for Google campaigns on the account.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.metrics import MetricsCache
from app.models.reservation import Reservation
from app.services.google_recommendations.base import (
    Detector,
    DetectorFinding,
    DetectorTarget,
)
from app.services.google_recommendations.registry import register

DELTA_THRESHOLD_PCT = 15.0
MIN_SAMPLES = 10  # need at least 10 bookings either side to avoid noise


@register
class ConvAdsVsPmsDeltaDetector(Detector):
    rec_type = "CONV_ADS_VS_PMS_DELTA"

    def scope(self, db: Session, account_ids: list[str] | None = None) -> Iterable[DetectorTarget]:
        q = db.query(Campaign.account_id).filter(Campaign.platform == "google").distinct()
        if account_ids:
            q = q.filter(Campaign.account_id.in_(account_ids))
        for row in q.all():
            yield DetectorTarget(
                entity_level="account",
                entity_id=row[0],
                account_id=row[0],
                context={},
            )

    def evaluate(self, db: Session, target: DetectorTarget) -> DetectorFinding | None:
        today = date.today()
        start = today - timedelta(days=30)

        ads_conv = int(
            db.query(func.coalesce(func.sum(MetricsCache.conversions), 0))
            .join(Campaign, MetricsCache.campaign_id == Campaign.id)
            .filter(Campaign.platform == "google")
            .filter(Campaign.account_id == target.account_id)
            .filter(MetricsCache.ad_set_id.is_(None))
            .filter(MetricsCache.ad_id.is_(None))
            .filter(MetricsCache.date >= start)
            .scalar() or 0
        )

        # Reservations store a check_in_date or created_at — accept either column
        # name so this detector tolerates schema drift.
        res_col = None
        for candidate in ("created_at", "booking_date", "check_in_date"):
            if hasattr(Reservation, candidate):
                res_col = getattr(Reservation, candidate)
                break
        if res_col is None:
            return None
        pms_count = int(
            db.query(func.count(Reservation.id))
            .filter(Reservation.branch_id == target.account_id)
            .filter(res_col >= start)
            .scalar() or 0
        )

        if max(ads_conv, pms_count) < MIN_SAMPLES:
            return None
        denom = max(ads_conv, pms_count, 1)
        delta_pct = abs(ads_conv - pms_count) / denom * 100
        if delta_pct <= DELTA_THRESHOLD_PCT:
            return None

        return DetectorFinding(
            evidence={
                "ads_conversions_30d": ads_conv,
                "pms_reservations_30d": pms_count,
                "delta_pct": delta_pct,
                "threshold_pct": DELTA_THRESHOLD_PCT,
            },
            metrics_snapshot={"ads_conv_30d": ads_conv, "pms_count_30d": pms_count},
            warning_vars={"pct": int(delta_pct)},
        )
