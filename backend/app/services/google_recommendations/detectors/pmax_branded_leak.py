"""PMAX_BRANDED_LEAK — PMax ROAS abnormally high vs account AND branded Search impressions falling.

Per SOP Part 3.6 — the "brand leak" pattern: PMax is cannibalizing branded
queries so its ROAS looks artificially great while branded Search starves.

Fires per PMax campaign when BOTH conditions hold (last 7d vs prior 7d):
- PMax ROAS ≥ 2 × account avg ROAS
- branded Search campaign impressions dropped ≥30% in the same account
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.metrics import MetricsCache
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

PMAX_ROAS_MULTIPLIER = 2.0
BRANDED_IMPR_DROP_PCT = 30.0


def _sum_metric(db: Session, campaign_ids: list[str], metric: str, start: date, end: date) -> float:
    if not campaign_ids:
        return 0.0
    col = getattr(MetricsCache, metric)
    v = (
        db.query(func.coalesce(func.sum(col), 0))
        .filter(MetricsCache.campaign_id.in_(campaign_ids))
        .filter(MetricsCache.ad_set_id.is_(None))
        .filter(MetricsCache.ad_id.is_(None))
        .filter(MetricsCache.date >= start)
        .filter(MetricsCache.date <= end)
        .scalar()
    )
    return float(v or 0)


def _is_branded(camp: Campaign) -> bool:
    return bool(camp.name and "brand" in camp.name.lower())


@register
class PmaxBrandedLeakDetector(Detector):
    rec_type = "PMAX_BRANDED_LEAK"

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
            yield DetectorTarget(
                entity_level="campaign",
                entity_id=camp.id,
                account_id=camp.account_id,
                campaign_id=camp.id,
                campaign_type="PMAX",
                context={"campaign_name": camp.name},
            )

    def evaluate(self, db: Session, target: DetectorTarget) -> DetectorFinding | None:
        today = date.today()
        recent_start = today - timedelta(days=7)
        recent_end = today - timedelta(days=1)
        prior_start = today - timedelta(days=14)
        prior_end = today - timedelta(days=8)

        # 1) This campaign's recent ROAS.
        spend_c = _sum_metric(db, [target.campaign_id], "spend", recent_start, recent_end)
        rev_c = _sum_metric(db, [target.campaign_id], "revenue", recent_start, recent_end)
        if spend_c <= 0:
            return None
        roas_c = rev_c / spend_c

        # 2) Account-wide avg ROAS (all active Google campaigns) for baseline.
        all_google_ids = [
            r[0] for r in (
                db.query(Campaign.id)
                .filter(Campaign.account_id == target.account_id)
                .filter(Campaign.platform == "google")
                .filter(Campaign.status == "ACTIVE")
                .all()
            )
        ]
        spend_all = _sum_metric(db, all_google_ids, "spend", recent_start, recent_end)
        rev_all = _sum_metric(db, all_google_ids, "revenue", recent_start, recent_end)
        if spend_all <= 0:
            return None
        roas_all = rev_all / spend_all
        if roas_all <= 0:
            return None
        if roas_c < PMAX_ROAS_MULTIPLIER * roas_all:
            return None

        # 3) Branded Search campaigns in the same account — impression drop w/w.
        branded_ids: list[str] = []
        for camp in (
            db.query(Campaign)
            .filter(Campaign.account_id == target.account_id)
            .filter(Campaign.platform == "google")
            .filter(Campaign.status == "ACTIVE")
            .all()
        ):
            if classify_campaign(camp) == "SEARCH" and _is_branded(camp):
                branded_ids.append(camp.id)
        if not branded_ids:
            return None
        impr_recent = _sum_metric(db, branded_ids, "impressions", recent_start, recent_end)
        impr_prior = _sum_metric(db, branded_ids, "impressions", prior_start, prior_end)
        if impr_prior <= 0:
            return None
        drop_pct = (impr_prior - impr_recent) / impr_prior * 100
        if drop_pct < BRANDED_IMPR_DROP_PCT:
            return None

        return DetectorFinding(
            evidence={
                "pmax_roas_7d": roas_c,
                "account_avg_roas_7d": roas_all,
                "roas_multiplier": roas_c / roas_all if roas_all else None,
                "branded_impr_drop_pct": drop_pct,
                "branded_impr_recent": impr_recent,
                "branded_impr_prior": impr_prior,
                "campaign_name": target.context.get("campaign_name"),
            },
            metrics_snapshot=snapshot_metrics(db, target.campaign_id),
        )
