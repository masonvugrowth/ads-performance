"""Export API endpoints with API key authentication."""

import calendar
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.api_key import ApiKey
from app.models.booking_match import BookingMatch
from app.models.budget import BudgetPlan
from app.models.metrics import MetricsCache
from app.services.export_auth import create_api_key, validate_api_key

router = APIRouter()


def _api_response(data=None, error=None):
    return {
        "success": error is None,
        "data": data,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


class KeyCreate(BaseModel):
    name: str
    created_by: str | None = None


@router.post("/export/keys")
def create_key(body: KeyCreate, db: Session = Depends(get_db)):
    """Create a new API key. Returns plaintext ONCE."""
    try:
        api_key, plaintext = create_api_key(db, body.name, body.created_by)
        db.commit()
        return _api_response(data={
            "id": str(api_key.id),
            "name": api_key.name,
            "key": plaintext,  # Shown once, never again
            "key_prefix": api_key.key_prefix,
            "created_at": api_key.created_at.isoformat() if api_key.created_at else None,
        })
    except Exception as e:
        db.rollback()
        return _api_response(error=str(e))


@router.get("/export/keys")
def list_keys(db: Session = Depends(get_db)):
    """List API keys (no plaintext shown)."""
    try:
        keys = db.query(ApiKey).filter(ApiKey.is_active.is_(True)).all()
        return _api_response(data=[
            {
                "id": str(k.id),
                "name": k.name,
                "key_prefix": k.key_prefix,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "daily_request_count": k.daily_request_count,
                "created_at": k.created_at.isoformat() if k.created_at else None,
            }
            for k in keys
        ])
    except Exception as e:
        return _api_response(error=str(e))


@router.delete("/export/keys/{key_id}")
def deactivate_key(key_id: str, db: Session = Depends(get_db)):
    """Deactivate an API key (soft delete)."""
    try:
        api_key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
        if not api_key:
            return _api_response(error="API key not found")
        api_key.is_active = False
        db.commit()
        return _api_response(data={"id": key_id, "deactivated": True})
    except Exception as e:
        db.rollback()
        return _api_response(error=str(e))


@router.get("/export/budget/monthly")
def export_budget_monthly(
    month: str = Query(None, description="YYYY-MM format"),
    api_key: ApiKey = Depends(validate_api_key),
    db: Session = Depends(get_db),
):
    """Export monthly budget data. Requires API key."""
    try:
        if month:
            month_date = date.fromisoformat(f"{month}-01")
        else:
            today = date.today()
            month_date = date(today.year, today.month, 1)

        plans = (
            db.query(BudgetPlan)
            .filter(BudgetPlan.month == month_date, BudgetPlan.is_active.is_(True))
            .all()
        )

        return _api_response(data={
            "month": month_date.isoformat(),
            "plans": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "branch": p.branch,
                    "channel": p.channel,
                    "total_budget": float(p.total_budget),
                    "currency": p.currency,
                }
                for p in plans
            ],
        })
    except Exception as e:
        return _api_response(error=str(e))


@router.get("/export/spend/daily")
def export_spend_daily(
    date_from: str = Query(...),
    date_to: str = Query(...),
    platform: str = Query(None),
    api_key: ApiKey = Depends(validate_api_key),
    db: Session = Depends(get_db),
):
    """Export daily spend breakdown. Requires API key."""
    try:
        q = db.query(
            MetricsCache.date,
            MetricsCache.platform,
            func.sum(MetricsCache.spend).label("spend"),
            func.sum(MetricsCache.impressions).label("impressions"),
            func.sum(MetricsCache.clicks).label("clicks"),
            func.sum(MetricsCache.conversions).label("conversions"),
            func.sum(MetricsCache.revenue).label("revenue"),
        ).filter(
            MetricsCache.date >= date.fromisoformat(date_from),
            MetricsCache.date <= date.fromisoformat(date_to),
        )

        if platform:
            q = q.filter(MetricsCache.platform == platform)

        rows = q.group_by(MetricsCache.date, MetricsCache.platform).order_by(MetricsCache.date).all()

        return _api_response(data=[
            {
                "date": row.date.isoformat(),
                "platform": row.platform,
                "spend": float(row.spend or 0),
                "impressions": int(row.impressions or 0),
                "clicks": int(row.clicks or 0),
                "conversions": int(row.conversions or 0),
                "revenue": float(row.revenue or 0),
            }
            for row in rows
        ])
    except Exception as e:
        return _api_response(error=str(e))


def _resolve_booking_date_range(date_from: str | None, date_to: str | None) -> tuple[date, date]:
    if date_to:
        dt = date.fromisoformat(date_to)
    else:
        dt = date.today()
    if date_from:
        df = date.fromisoformat(date_from)
    else:
        df = dt - timedelta(days=29)
    if df > dt:
        raise ValueError("date_from must be <= date_to")
    return df, dt


@router.get("/export/booking-matches")
def export_booking_matches(
    date_from: str = Query(None, description="ISO date YYYY-MM-DD; defaults to 30 days before date_to"),
    date_to: str = Query(None, description="ISO date YYYY-MM-DD; defaults to today"),
    branch: str = Query(None, description="Canonical branch key: Saigon|Taipei|1948|Osaka|Oani"),
    channel: str = Query(None, description="Ads channel: meta|google"),
    match_result: str = Query(None),
    limit: int = Query(500, le=2000),
    offset: int = Query(0, ge=0),
    api_key: ApiKey = Depends(validate_api_key),
    db: Session = Depends(get_db),
):
    """Export Booking from Ads rows for external systems. Requires X-API-Key.

    Returns the same shape as the internal /api/booking-matches endpoint plus
    rate_plans, so downstream BI tools can break down matched revenue by rate plan.
    """
    try:
        df, dt = _resolve_booking_date_range(date_from, date_to)

        q = db.query(BookingMatch).filter(
            BookingMatch.match_date >= df,
            BookingMatch.match_date <= dt,
        )
        if branch:
            q = q.filter(BookingMatch.branch == branch)
        if channel:
            q = q.filter(BookingMatch.ads_channel == channel)
        if match_result:
            q = q.filter(BookingMatch.match_result == match_result)

        total = q.count()
        rows = (
            q.order_by(BookingMatch.match_date.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        items = [
            {
                "id": str(m.id),
                "match_date": m.match_date.isoformat() if m.match_date else None,
                "ads_revenue": float(m.ads_revenue or 0),
                "ads_bookings": m.ads_bookings,
                "ads_country": m.ads_country,
                "ads_channel": m.ads_channel,
                "campaign_name": m.campaign_name,
                "campaign_id": str(m.campaign_id) if m.campaign_id else None,
                "reservation_numbers": m.reservation_numbers,
                "guest_names": m.guest_names,
                "guest_emails": m.guest_emails,
                "reservation_statuses": m.reservation_statuses,
                "room_types": m.room_types,
                "rate_plans": m.rate_plans,
                "reservation_sources": m.reservation_sources,
                "matched_country": m.matched_country,
                "branch": m.branch,
                "match_result": m.match_result,
                "matched_at": m.matched_at.isoformat() if m.matched_at else None,
            }
            for m in rows
        ]

        return _api_response(data={
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "period": {"from": df.isoformat(), "to": dt.isoformat()},
        })
    except Exception as e:
        return _api_response(error=str(e))


@router.get("/export/booking-matches/summary")
def export_booking_matches_summary(
    date_from: str = Query(None),
    date_to: str = Query(None),
    branch: str = Query(None),
    api_key: ApiKey = Depends(validate_api_key),
    db: Session = Depends(get_db),
):
    """KPI roll-up for Booking from Ads. Requires X-API-Key."""
    try:
        df, dt = _resolve_booking_date_range(date_from, date_to)

        base = db.query(BookingMatch).filter(
            BookingMatch.match_date >= df,
            BookingMatch.match_date <= dt,
        )
        if branch:
            base = base.filter(BookingMatch.branch == branch)

        total_matches = base.count()
        total_revenue = float(base.with_entities(func.sum(BookingMatch.ads_revenue)).scalar() or 0)
        total_bookings = int(base.with_entities(func.sum(BookingMatch.ads_bookings)).scalar() or 0)

        by_channel = [
            {
                "channel": r.ads_channel or "unknown",
                "matches": int(r.matches or 0),
                "revenue": float(r.revenue or 0),
                "bookings": int(r.bookings or 0),
            }
            for r in base.with_entities(
                BookingMatch.ads_channel,
                func.count(BookingMatch.id).label("matches"),
                func.sum(BookingMatch.ads_revenue).label("revenue"),
                func.sum(BookingMatch.ads_bookings).label("bookings"),
            ).group_by(BookingMatch.ads_channel).all()
        ]

        by_branch = [
            {
                "branch": r.branch or "unknown",
                "matches": int(r.matches or 0),
                "revenue": float(r.revenue or 0),
                "bookings": int(r.bookings or 0),
            }
            for r in base.with_entities(
                BookingMatch.branch,
                func.count(BookingMatch.id).label("matches"),
                func.sum(BookingMatch.ads_revenue).label("revenue"),
                func.sum(BookingMatch.ads_bookings).label("bookings"),
            ).group_by(BookingMatch.branch).all()
        ]

        return _api_response(data={
            "total_matches": total_matches,
            "total_revenue": total_revenue,
            "total_bookings": total_bookings,
            "by_channel": by_channel,
            "by_branch": by_branch,
            "period": {"from": df.isoformat(), "to": dt.isoformat()},
        })
    except Exception as e:
        return _api_response(error=str(e))
