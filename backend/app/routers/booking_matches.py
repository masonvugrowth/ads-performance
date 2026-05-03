"""Booking matches dashboard endpoints."""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from sqlalchemy import or_

from app.core.permissions import accessible_branches, is_admin
from app.database import get_db
from app.dependencies.auth import get_current_user, require_section
from app.models.account import AdAccount
from app.models.ad import Ad
from app.models.ad_country_metric import AdCountryMetric
from app.models.booking_match import BookingMatch
from app.models.campaign import Campaign
from app.models.reservation import Reservation
from app.models.user import User
from app.routers.accounts import BRANCH_ACCOUNT_MAP, branch_name_patterns
from app.services.booking_match_service import (
    AMOUNT_TOLERANCE,
    country_iso_matches_reservation,
    normalize_branch,
    run_matching,
)
from app.services.reservation_sync import (
    extract_rate_plan_from_room_type,
    sync_reservations,
)

router = APIRouter()


def _api_response(data=None, error=None):
    return {
        "success": error is None,
        "data": data,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _default_date_range() -> tuple[date, date]:
    today = date.today()
    return today - timedelta(days=29), today


def _apply_branch_scope(q, column, user, db, requested_branch: str | None):
    """Restrict a query to the user's accessible branches for analytics.

    Returns (ok, query, error). When ok=False, caller should return _api_response(error=err).
    When admin: no scope applied beyond the explicit `requested_branch` filter.
    """
    if requested_branch:
        # Explicit branch from client — validate against permissions
        if not is_admin(user):
            allowed = accessible_branches(db, user, "analytics") or []
            if requested_branch not in allowed and requested_branch not in BRANCH_ACCOUNT_MAP:
                return False, q, f"No view access to branch '{requested_branch}'"
            if requested_branch in BRANCH_ACCOUNT_MAP and requested_branch not in allowed:
                return False, q, f"No view access to branch '{requested_branch}'"
        patterns = BRANCH_ACCOUNT_MAP.get(requested_branch, [requested_branch])
        q = q.filter(or_(*[column.ilike(f"%{p}%") for p in patterns]))
        return True, q, None

    if is_admin(user):
        return True, q, None

    allowed = accessible_branches(db, user, "analytics") or []
    if not allowed:
        # Force empty result
        q = q.filter(column == "__no_match__")
        return True, q, None
    patterns = branch_name_patterns(allowed)
    q = q.filter(or_(*[column.ilike(f"%{p}%") for p in patterns]))
    return True, q, None


def _serialize_match(m: BookingMatch) -> dict:
    return {
        "id": m.id,
        "match_date": m.match_date.isoformat() if m.match_date else None,
        "ads_revenue": float(m.ads_revenue or 0),
        "ads_bookings": m.ads_bookings,
        "ads_country": m.ads_country,
        "ads_channel": m.ads_channel,
        "campaign_name": m.campaign_name,
        "campaign_id": m.campaign_id,
        "ad_id": m.ad_id,
        "ad_name": m.ad_name,
        "purchase_kind": m.purchase_kind,
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


@router.get("/booking-matches")
def list_booking_matches(
    date_from: str = Query(None),
    date_to: str = Query(None),
    branch: str = Query(None),
    channel: str = Query(None),
    match_result: str = Query(None),
    purchase_kind: str = Query(None, description="website | offline"),
    limit: int = Query(200, le=1000),
    offset: int = Query(0),
    current_user: User = Depends(require_section("analytics")),
    db: Session = Depends(get_db),
):
    """List booking matches with filters, sorted by date desc (like the Sheet)."""
    try:
        if not date_from or not date_to:
            df, dt = _default_date_range()
            date_from = date_from or df.isoformat()
            date_to = date_to or dt.isoformat()

        df = date.fromisoformat(date_from)
        dt = date.fromisoformat(date_to)

        q = db.query(BookingMatch).filter(
            BookingMatch.match_date >= df,
            BookingMatch.match_date <= dt,
        )
        ok, q, err = _apply_branch_scope(q, BookingMatch.branch, current_user, db, branch)
        if not ok:
            return _api_response(error=err)
        if channel:
            q = q.filter(BookingMatch.ads_channel == channel)
        if match_result:
            q = q.filter(BookingMatch.match_result == match_result)
        if purchase_kind:
            q = q.filter(BookingMatch.purchase_kind == purchase_kind)

        total = q.count()
        rows = q.order_by(BookingMatch.match_date.desc()).offset(offset).limit(limit).all()

        return _api_response(data={
            "items": [_serialize_match(m) for m in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
            "period": {"from": date_from, "to": date_to},
        })
    except Exception as e:
        return _api_response(error=str(e))


@router.get("/booking-matches/summary")
def booking_matches_summary(
    date_from: str = Query(None),
    date_to: str = Query(None),
    branch: str = Query(None),
    current_user: User = Depends(require_section("analytics")),
    db: Session = Depends(get_db),
):
    """KPI summary for the dashboard."""
    try:
        if not date_from or not date_to:
            df, dt = _default_date_range()
            date_from = date_from or df.isoformat()
            date_to = date_to or dt.isoformat()

        df = date.fromisoformat(date_from)
        dt = date.fromisoformat(date_to)

        base = db.query(BookingMatch).filter(
            BookingMatch.match_date >= df,
            BookingMatch.match_date <= dt,
        )
        ok, base, err = _apply_branch_scope(base, BookingMatch.branch, current_user, db, branch)
        if not ok:
            return _api_response(error=err)

        # Total KPIs
        total_matches = base.count()
        total_revenue = float(base.with_entities(func.sum(BookingMatch.ads_revenue)).scalar() or 0)
        total_bookings = int(base.with_entities(func.sum(BookingMatch.ads_bookings)).scalar() or 0)

        # By channel
        by_channel_rows = (
            base.with_entities(
                BookingMatch.ads_channel,
                func.count(BookingMatch.id).label("matches"),
                func.sum(BookingMatch.ads_revenue).label("revenue"),
                func.sum(BookingMatch.ads_bookings).label("bookings"),
            )
            .group_by(BookingMatch.ads_channel)
            .all()
        )
        by_channel = [
            {
                "channel": r.ads_channel or "unknown",
                "matches": int(r.matches or 0),
                "revenue": float(r.revenue or 0),
                "bookings": int(r.bookings or 0),
            }
            for r in by_channel_rows
        ]

        # By branch
        by_branch_rows = (
            base.with_entities(
                BookingMatch.branch,
                func.count(BookingMatch.id).label("matches"),
                func.sum(BookingMatch.ads_revenue).label("revenue"),
                func.sum(BookingMatch.ads_bookings).label("bookings"),
            )
            .group_by(BookingMatch.branch)
            .all()
        )
        by_branch = [
            {
                "branch": r.branch or "unknown",
                "matches": int(r.matches or 0),
                "revenue": float(r.revenue or 0),
                "bookings": int(r.bookings or 0),
            }
            for r in by_branch_rows
        ]

        # By result
        by_result_rows = (
            base.with_entities(
                BookingMatch.match_result,
                func.count(BookingMatch.id).label("count"),
            )
            .group_by(BookingMatch.match_result)
            .all()
        )
        by_result = [
            {"result": r.match_result, "count": int(r.count or 0)}
            for r in by_result_rows
        ]

        return _api_response(data={
            "total_matches": total_matches,
            "total_revenue": total_revenue,
            "total_bookings": total_bookings,
            "by_channel": by_channel,
            "by_branch": by_branch,
            "by_result": by_result,
            "period": {"from": date_from, "to": date_to},
        })
    except Exception as e:
        return _api_response(error=str(e))


@router.get("/booking-matches/ads-revenue-debug")
def ads_revenue_debug(
    date_from: str = Query(None),
    date_to: str = Query(None),
    current_user: User = Depends(require_section("analytics")),
    db: Session = Depends(get_db),
):
    """Why is matching empty? Reports counts of ad_country_metrics in window
    grouped by platform + branch + whether revenue_website / revenue_offline
    are populated. Helps tell apart 'no ads sync ran' vs 'ads sync ran but
    purchase events not attributed' vs 'no overlap with reservations'."""
    try:
        if not date_from or not date_to:
            df, dt = _default_date_range()
            date_from = date_from or df.isoformat()
            date_to = date_to or dt.isoformat()
        df = date.fromisoformat(date_from)
        dt = date.fromisoformat(date_to)

        base = (
            db.query(
                AdCountryMetric.platform.label("platform"),
                AdAccount.account_name.label("account_name"),
                func.count(AdCountryMetric.id).label("rows"),
                func.sum(AdCountryMetric.revenue_website).label("rev_web"),
                func.sum(AdCountryMetric.revenue_offline).label("rev_off"),
                func.sum(AdCountryMetric.spend).label("spend"),
                func.count(AdCountryMetric.id)
                    .filter(AdCountryMetric.revenue_website > 0)
                    .label("rows_rev_web_pos"),
                func.count(AdCountryMetric.id)
                    .filter(AdCountryMetric.revenue_offline > 0)
                    .label("rows_rev_off_pos"),
            )
            .join(Campaign, Campaign.id == AdCountryMetric.campaign_id)
            .join(AdAccount, AdAccount.id == Campaign.account_id)
            .filter(AdCountryMetric.date >= df, AdCountryMetric.date <= dt)
            .group_by(AdCountryMetric.platform, AdAccount.account_name)
        )
        rows = base.all()

        items = [
            {
                "platform": r.platform,
                "account_name": r.account_name,
                "rows": int(r.rows or 0),
                "rows_rev_website_pos": int(r.rows_rev_web_pos or 0),
                "rows_rev_offline_pos": int(r.rows_rev_off_pos or 0),
                "sum_revenue_website": float(r.rev_web or 0),
                "sum_revenue_offline": float(r.rev_off or 0),
                "sum_spend": float(r.spend or 0),
            }
            for r in rows
        ]
        items.sort(key=lambda x: (x["platform"], x["account_name"]))

        # Distinct dates in window with any row at all
        dates_with_rows = (
            db.query(AdCountryMetric.date)
            .filter(AdCountryMetric.date >= df, AdCountryMetric.date <= dt)
            .distinct()
            .order_by(AdCountryMetric.date.desc())
            .limit(5)
            .all()
        )

        # Whole-table state — useful when window is empty: tells us if the
        # table is empty altogether vs only stale.
        global_total = db.query(func.count(AdCountryMetric.id)).scalar() or 0
        global_min = db.query(func.min(AdCountryMetric.date)).scalar()
        global_max = db.query(func.max(AdCountryMetric.date)).scalar()
        global_rev_rows = (
            db.query(func.count(AdCountryMetric.id))
            .filter(
                (AdCountryMetric.revenue_website > 0)
                | (AdCountryMetric.revenue_offline > 0)
            )
            .scalar() or 0
        )
        latest_dates_overall = (
            db.query(AdCountryMetric.date)
            .distinct()
            .order_by(AdCountryMetric.date.desc())
            .limit(5)
            .all()
        )

        return _api_response(data={
            "period": {"from": date_from, "to": date_to},
            "by_platform_account": items,
            "total_rows_in_window": sum(x["rows"] for x in items),
            "total_rows_with_any_revenue": sum(
                x["rows_rev_website_pos"] + x["rows_rev_offline_pos"] for x in items
            ),
            "latest_dates_with_rows": [d.date.isoformat() for d in dates_with_rows],
            "table_state": {
                "total_rows_all_time": int(global_total),
                "rows_with_revenue_all_time": int(global_rev_rows),
                "min_date": global_min.isoformat() if global_min else None,
                "max_date": global_max.isoformat() if global_max else None,
                "latest_dates_overall": [d.date.isoformat() for d in latest_dates_overall],
            },
        })
    except Exception as e:
        return _api_response(error=str(e))


@router.post("/booking-matches/cloudbeds-sync")
def cloudbeds_sync_one_branch(
    branch: str = Query("Saigon"),
    days_back: int = Query(30, ge=1, le=365),
    rerun_match: bool = Query(True, description="Re-run booking matching after sync"),
    current_user: User = Depends(require_section("analytics", "edit")),
    db: Session = Depends(get_db),
):
    """One-shot Cloudbeds sync for a single branch + optional re-match.

    Pulls reservations created in the last `days_back` days from Cloudbeds
    for the given branch (must have CB_API_KEY_<BRANCH> + CB_PROPERTY_ID
    configured), upserts into reservations, then optionally re-runs the
    matching pass over the same window.
    """
    try:
        from app.services.cloudbeds_sync import sync_branch as cb_sync_branch
        date_to = date.today()
        date_from = date_to - timedelta(days=days_back)
        sync_summary = cb_sync_branch(db, branch, date_from, date_to)
        match_summary = None
        if rerun_match:
            match_summary = run_matching(db, date_from, date_to)
        return _api_response(data={
            "cloudbeds_sync": sync_summary,
            "matching": match_summary,
        })
    except ValueError as e:
        return _api_response(error=str(e))
    except Exception as e:
        return _api_response(error=str(e))


@router.post("/booking-matches/cloudbeds-ping")
def cloudbeds_ping(
    branch: str = Query("Saigon"),
    days_back: int = Query(7, ge=1, le=90),
    current_user: User = Depends(require_section("analytics", "edit")),
    db: Session = Depends(get_db),
):
    """Diagnostic: probe Cloudbeds API for a branch via the logged-in session.

    Convenience wrapper around services.cloudbeds_client.probe — same payload
    as the internal-secret-protected endpoint but reachable from the browser
    while logged in. Returns which auth flavour worked + a sample reservation.
    """
    try:
        from app.services.cloudbeds_client import probe
        date_to = date.today()
        date_from = date_to - timedelta(days=days_back)
        return _api_response(data=probe(branch, date_from, date_to))
    except ValueError as e:
        return _api_response(error=str(e))
    except Exception as e:
        return _api_response(error=str(e))


@router.post("/booking-matches/run")
def trigger_match_run(
    date_from: str = Query(None),
    date_to: str = Query(None),
    skip_sync: bool = Query(False, description="Skip PMS sync, only re-run matching"),
    current_user: User = Depends(require_section("analytics", "edit")),
    db: Session = Depends(get_db),
):
    """Manual trigger: pull reservations from PMS, then run matching."""
    try:
        if not date_from or not date_to:
            df, dt = _default_date_range()
            date_from = date_from or df.isoformat()
            date_to = date_to or dt.isoformat()

        df = date.fromisoformat(date_from)
        dt = date.fromisoformat(date_to)

        sync_summary = None
        if not skip_sync:
            sync_summary = sync_reservations(db, df, dt)

        match_summary = run_matching(db, df, dt)

        return _api_response(data={
            "sync": sync_summary,
            "matching": match_summary,
        })
    except Exception as e:
        return _api_response(error=str(e))


@router.get("/booking-matches/reservations")
def list_reservations(
    date_from: str = Query(None),
    date_to: str = Query(None),
    branch: str = Query(None),
    source: str = Query(None),
    limit: int = Query(200, le=1000),
    offset: int = Query(0),
    current_user: User = Depends(require_section("analytics")),
    db: Session = Depends(get_db),
):
    """Raw reservations list for debugging."""
    try:
        if not date_from or not date_to:
            df, dt = _default_date_range()
            date_from = date_from or df.isoformat()
            date_to = date_to or dt.isoformat()

        df = date.fromisoformat(date_from)
        dt = date.fromisoformat(date_to)

        q = db.query(Reservation).filter(
            Reservation.reservation_date >= df,
            Reservation.reservation_date <= dt,
        )
        ok, q, err = _apply_branch_scope(q, Reservation.branch, current_user, db, branch)
        if not ok:
            return _api_response(error=err)
        if source:
            q = q.filter(Reservation.source == source)

        total = q.count()
        rows = q.order_by(Reservation.reservation_date.desc()).offset(offset).limit(limit).all()

        items = [
            {
                "id": r.id,
                "reservation_number": r.reservation_number,
                "reservation_date": r.reservation_date.isoformat() if r.reservation_date else None,
                "check_in_date": r.check_in_date.isoformat() if r.check_in_date else None,
                "check_out_date": r.check_out_date.isoformat() if r.check_out_date else None,
                "grand_total": float(r.grand_total) if r.grand_total is not None else None,
                "country": r.country,
                "name": r.name,
                "email": r.email,
                "status": r.status,
                "source": r.source,
                "room_type": r.room_type,
                "rate_plan_name": r.rate_plan_name,
                "branch": r.branch,
                "nights": r.nights,
                "adults": r.adults,
            }
            for r in rows
        ]

        return _api_response(data={
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        })
    except Exception as e:
        return _api_response(error=str(e))


@router.get("/booking-matches/diagnose")
def diagnose_reservation(
    reservation_number: str = Query(..., description="PMS reservation number"),
    current_user: User = Depends(require_section("analytics")),
    db: Session = Depends(get_db),
):
    """Explain why a specific reservation did or didn't match any ads row.

    Returns the reservation, the matched BookingMatch (if any), and every
    campaign-level ads row on the same day+branch with the revenue delta so
    we can see whether it's a revenue mismatch, a missing ads row, or a
    branch-normalisation issue.
    """
    try:
        r = (
            db.query(Reservation)
            .filter(Reservation.reservation_number == reservation_number)
            .first()
        )
        if not r:
            return _api_response(error=f"Reservation {reservation_number} not found")

        branch_key = normalize_branch(r.branch)
        grand_total = float(r.grand_total) if r.grand_total is not None else None

        # Existing match (if any) — search the ", "-joined reservation_numbers column.
        existing_match = (
            db.query(BookingMatch)
            .filter(BookingMatch.reservation_numbers.ilike(f"%{reservation_number}%"))
            .order_by(BookingMatch.match_date.desc())
            .first()
        )

        # Candidate ads rows — same date + same branch, from ad_country_metrics
        # (ad×country for Meta, campaign×country for Google).
        ads_candidates: list[dict] = []
        if branch_key and r.reservation_date:
            patterns = BRANCH_ACCOUNT_MAP.get(branch_key, [branch_key])
            rows = (
                db.query(
                    AdCountryMetric.platform.label("platform"),
                    AdCountryMetric.country.label("country"),
                    AdCountryMetric.revenue_website.label("revenue_website"),
                    AdCountryMetric.revenue_offline.label("revenue_offline"),
                    AdCountryMetric.conversions_website.label("conversions_website"),
                    AdCountryMetric.conversions_offline.label("conversions_offline"),
                    Campaign.name.label("campaign_name"),
                    AdAccount.account_name.label("account_name"),
                    Ad.name.label("ad_name"),
                )
                .join(Campaign, Campaign.id == AdCountryMetric.campaign_id)
                .join(AdAccount, AdAccount.id == Campaign.account_id)
                .outerjoin(Ad, Ad.id == AdCountryMetric.ad_id)
                .filter(
                    AdCountryMetric.date == r.reservation_date,
                    or_(*[AdAccount.account_name.ilike(f"%{p}%") for p in patterns]),
                )
                .all()
            )
            for row in rows:
                rev_web = float(row.revenue_website or 0)
                rev_off = float(row.revenue_offline or 0)
                if rev_web <= 0 and rev_off <= 0:
                    continue
                country_match = country_iso_matches_reservation(row.country, r.country)
                entries = []
                if rev_web > 0:
                    entries.append(("website", rev_web, int(row.conversions_website or 0)))
                if rev_off > 0:
                    entries.append(("offline", rev_off, int(row.conversions_offline or 0)))
                for kind, rev, bk in entries:
                    delta = (rev - grand_total) if grand_total is not None else None
                    ads_candidates.append({
                        "platform": row.platform,
                        "country": row.country,
                        "country_matches_reservation": country_match,
                        "campaign_name": row.campaign_name,
                        "ad_name": row.ad_name,
                        "account_name": row.account_name,
                        "purchase_kind": kind,
                        "ads_revenue": rev,
                        "ads_bookings": bk,
                        "revenue_delta_vs_grand_total": delta,
                        "within_tolerance": (
                            delta is not None and abs(delta) < AMOUNT_TOLERANCE
                        ),
                    })

        reservation_kind = "website" if (r.source or "").strip().lower() == "website/booking engine" else "offline"
        reasons: list[str] = []
        if not branch_key:
            reasons.append(f"branch '{r.branch}' could not be normalised to a hotel key")
        if grand_total is None:
            reasons.append("reservation.grand_total is NULL")
        if not r.reservation_date:
            reasons.append("reservation.reservation_date is NULL")

        same_kind = [c for c in ads_candidates if c["purchase_kind"] == reservation_kind]
        if not ads_candidates and branch_key and r.reservation_date:
            reasons.append(
                f"no ad×country rows for branch {branch_key} on {r.reservation_date}"
            )
        elif ads_candidates and not same_kind:
            reasons.append(
                f"no ads revenue of kind '{reservation_kind}' on this date/branch — "
                f"candidates only have {sorted({c['purchase_kind'] for c in ads_candidates})}"
            )
        elif same_kind:
            matching_country = [c for c in same_kind if c["country_matches_reservation"]]
            if grand_total is not None and matching_country and not any(
                c["within_tolerance"] for c in matching_country
            ):
                reasons.append(
                    f"ads revenue does not equal grand_total within ±{AMOUNT_TOLERANCE} "
                    f"on any same-kind + same-country row"
                )
            if not matching_country:
                reasons.append(
                    f"no same-kind row where ads country matches reservation.country "
                    f"({r.country!r})"
                )

        return _api_response(data={
            "reservation": {
                "id": r.id,
                "reservation_number": r.reservation_number,
                "reservation_date": r.reservation_date.isoformat() if r.reservation_date else None,
                "check_in_date": r.check_in_date.isoformat() if r.check_in_date else None,
                "grand_total": grand_total,
                "country": r.country,
                "status": r.status,
                "source": r.source,
                "room_type": r.room_type,
                "rate_plan_name": r.rate_plan_name or extract_rate_plan_from_room_type(r.room_type),
                "branch": r.branch,
                "branch_key": branch_key,
            },
            "existing_match": _serialize_match(existing_match) if existing_match else None,
            "ads_candidates": ads_candidates,
            "likely_reasons": reasons,
            "amount_tolerance": AMOUNT_TOLERANCE,
        })
    except Exception as e:
        return _api_response(error=str(e))
