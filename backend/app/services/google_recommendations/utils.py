"""Shared helpers for detectors.

Keep utilities narrow and stateless — anything that grows into business
logic belongs in its own detector file.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.metrics import MetricsCache

# Google Ads objective string → catalog campaign_type
OBJECTIVE_TO_CAMPAIGN_TYPE: dict[str, str] = {
    "PERFORMANCE_MAX": "PMAX",
    "SEARCH": "SEARCH",
    "DEMAND_GEN": "DEMAND_GEN",
    "DISCOVERY": "DEMAND_GEN",
    "DISPLAY": "DISPLAY",
    "VIDEO": "VIDEO",
    "SHOPPING": "SHOPPING",
}


def classify_campaign(camp: Campaign) -> str | None:
    """Return the SOP campaign_type (PMAX/SEARCH/DEMAND_GEN/…) or None."""
    if not camp.objective:
        return None
    return OBJECTIVE_TO_CAMPAIGN_TYPE.get(camp.objective.upper())


def campaign_age_days(camp: Campaign, today: date | None = None) -> int | None:
    """Return campaign age in days (from start_date) or None if unknown."""
    if not camp.start_date:
        return None
    today = today or date.today()
    delta = (today - camp.start_date).days
    return max(0, delta)


def sum_metric_for_campaign(
    db: Session,
    campaign_id: str,
    metric: str,
    days: int,
    today: date | None = None,
) -> Decimal:
    """Sum a campaign-level metric over the last N days. Returns 0 if none."""
    today = today or date.today()
    date_from = today - timedelta(days=days)
    col = getattr(MetricsCache, metric)
    result = (
        db.query(func.coalesce(func.sum(col), 0))
        .filter(MetricsCache.campaign_id == campaign_id)
        .filter(MetricsCache.ad_set_id.is_(None))
        .filter(MetricsCache.ad_id.is_(None))
        .filter(MetricsCache.date >= date_from)
        .filter(MetricsCache.date <= today)
        .scalar()
    )
    return Decimal(str(result or 0))


def daily_metric_series(
    db: Session,
    campaign_id: str,
    metric: str,
    days: int,
    today: date | None = None,
) -> dict[date, Decimal]:
    """Return {date: value} for the last N days at the campaign level."""
    today = today or date.today()
    date_from = today - timedelta(days=days - 1)
    col = getattr(MetricsCache, metric)
    rows = (
        db.query(MetricsCache.date, col)
        .filter(MetricsCache.campaign_id == campaign_id)
        .filter(MetricsCache.ad_set_id.is_(None))
        .filter(MetricsCache.ad_id.is_(None))
        .filter(MetricsCache.date >= date_from)
        .filter(MetricsCache.date <= today)
        .order_by(MetricsCache.date.asc())
        .all()
    )
    return {row[0]: Decimal(str(row[1] or 0)) for row in rows}


def snapshot_metrics(
    db: Session,
    campaign_id: str,
    today: date | None = None,
) -> dict[str, float]:
    """Produce a 7d & 30d spend/impr/clicks/conv/roas snapshot for persistence."""
    today = today or date.today()
    out: dict[str, float] = {}
    for window in (7, 30):
        suffix = f"_{window}d"
        for metric in ("spend", "impressions", "clicks", "conversions", "revenue"):
            val = sum_metric_for_campaign(db, campaign_id, metric, window, today)
            out[f"{metric}{suffix}"] = float(val)
        spend = Decimal(str(out[f"spend{suffix}"]))
        revenue = Decimal(str(out[f"revenue{suffix}"]))
        conversions = Decimal(str(out[f"conversions{suffix}"]))
        clicks = Decimal(str(out[f"clicks{suffix}"]))
        impressions = Decimal(str(out[f"impressions{suffix}"]))
        out[f"roas{suffix}"] = float(revenue / spend) if spend > 0 else 0.0
        out[f"cpa{suffix}"] = float(spend / conversions) if conversions > 0 else 0.0
        out[f"ctr{suffix}"] = float(clicks / impressions) if impressions > 0 else 0.0
    return out
