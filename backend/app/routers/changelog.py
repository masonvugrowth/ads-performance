"""Change log endpoints — unified feed for the Country Dashboard Activity Log.

Auto entries are immutable (written by rule_engine / launch_service via the
changelog helper). Manual entries can be PATCHed by their author or an admin,
and soft-deleted — never hard-deleted.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.permissions import is_admin, scoped_account_ids
from app.database import get_db
from app.dependencies.auth import get_current_user, require_section
from app.models.account import AdAccount
from app.models.ad import Ad
from app.models.ad_set import AdSet
from app.models.campaign import Campaign
from app.models.change_log_entry import (
    ALL_CATEGORIES,
    MANUAL_ALLOWED_CATEGORIES,
    ChangeLogEntry,
)
from app.models.user import User
from app.services.changelog import (
    capture_baseline_snapshot,
    log_change,
    resolve_entity_context,
)

router = APIRouter()


def _api_response(data=None, error=None, status_code: int = 200):
    return {
        "success": error is None,
        "data": data,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _default_date_range() -> tuple[date, date]:
    today = date.today()
    return today - timedelta(days=6), today


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _serialize_entry(
    entry: ChangeLogEntry,
    *,
    campaign_name: str | None = None,
    ad_set_name: str | None = None,
    ad_name: str | None = None,
    account_name: str | None = None,
    author_name: str | None = None,
) -> dict:
    return {
        "id": str(entry.id),
        "occurred_at": entry.occurred_at.isoformat() if entry.occurred_at else None,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "category": entry.category,
        "source": entry.source,
        "triggered_by": entry.triggered_by,
        "title": entry.title,
        "description": entry.description,
        "country": entry.country,
        "branch": entry.branch,
        "platform": entry.platform,
        "account_id": str(entry.account_id) if entry.account_id else None,
        "account_name": account_name,
        "campaign_id": str(entry.campaign_id) if entry.campaign_id else None,
        "campaign_name": campaign_name,
        "ad_set_id": str(entry.ad_set_id) if entry.ad_set_id else None,
        "ad_set_name": ad_set_name,
        "ad_id": str(entry.ad_id) if entry.ad_id else None,
        "ad_name": ad_name,
        "before_value": entry.before_value,
        "after_value": entry.after_value,
        "metrics_snapshot": entry.metrics_snapshot,
        "source_url": entry.source_url,
        "author_user_id": str(entry.author_user_id) if entry.author_user_id else None,
        "author_name": author_name,
        "action_log_id": str(entry.action_log_id) if entry.action_log_id else None,
        "rule_id": str(entry.rule_id) if entry.rule_id else None,
    }


def _bulk_serialize(db: Session, entries: list[ChangeLogEntry]) -> list[dict]:
    """Resolve related entity names in a single round-trip each to avoid N+1."""
    campaign_ids = {e.campaign_id for e in entries if e.campaign_id}
    ad_set_ids = {e.ad_set_id for e in entries if e.ad_set_id}
    ad_ids = {e.ad_id for e in entries if e.ad_id}
    account_ids = {e.account_id for e in entries if e.account_id}
    user_ids = {e.author_user_id for e in entries if e.author_user_id}

    camp_names = {
        c.id: c.name for c in db.query(Campaign).filter(Campaign.id.in_(campaign_ids)).all()
    } if campaign_ids else {}
    adset_names = {
        a.id: a.name for a in db.query(AdSet).filter(AdSet.id.in_(ad_set_ids)).all()
    } if ad_set_ids else {}
    ad_names = {
        a.id: a.name for a in db.query(Ad).filter(Ad.id.in_(ad_ids)).all()
    } if ad_ids else {}
    account_names = {
        a.id: a.account_name for a in db.query(AdAccount).filter(AdAccount.id.in_(account_ids)).all()
    } if account_ids else {}
    user_names = {
        u.id: u.full_name for u in db.query(User).filter(User.id.in_(user_ids)).all()
    } if user_ids else {}

    return [
        _serialize_entry(
            e,
            campaign_name=camp_names.get(e.campaign_id),
            ad_set_name=adset_names.get(e.ad_set_id),
            ad_name=ad_names.get(e.ad_id),
            account_name=account_names.get(e.account_id),
            author_name=user_names.get(e.author_user_id),
        )
        for e in entries
    ]


# ---------------------------------------------------------------------------
# GET — list for the Activity Log feed
# ---------------------------------------------------------------------------


@router.get("/dashboard/country/changelog")
def list_changelog(
    country: str | None = Query(None),
    branches: str | None = Query(None, description="Comma-separated branch names"),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    category: list[str] = Query(default_factory=list),
    source: str | None = Query(None, description="auto | manual"),
    platform: str | None = Query(None),
    campaign_id: str | None = Query(None),
    ad_set_id: str | None = Query(None),
    ad_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_section("analytics")),
    db: Session = Depends(get_db),
):
    try:
        # Resolve branch scoping via the shared analytics helper.
        branch_list = (
            [b.strip() for b in branches.split(",") if b.strip()] if branches else None
        )
        ok, scoped_ids, scope_err = scoped_account_ids(
            db,
            current_user,
            "analytics",
            requested_branches=branch_list,
        )
        if not ok:
            return _api_response(error=scope_err)

        q = db.query(ChangeLogEntry).filter(ChangeLogEntry.is_deleted.is_(False))

        # Date range
        d_from, d_to = _default_date_range()
        if date_from:
            try:
                d_from = date.fromisoformat(date_from)
            except ValueError:
                return _api_response(error=f"Invalid date_from: {date_from}")
        if date_to:
            try:
                d_to = date.fromisoformat(date_to)
            except ValueError:
                return _api_response(error=f"Invalid date_to: {date_to}")
        start_dt = datetime.combine(d_from, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(d_to, datetime.max.time(), tzinfo=timezone.utc)
        q = q.filter(
            ChangeLogEntry.occurred_at >= start_dt,
            ChangeLogEntry.occurred_at <= end_dt,
        )

        # Country filter: accept explicit country or fall through to 'ALL'
        if country:
            code = country.upper()
            q = q.filter(
                (ChangeLogEntry.country == code) | (ChangeLogEntry.country == "ALL")
            )

        # Branch scoping — admin + no request => no filter
        if scoped_ids is not None:
            if branch_list:
                q = q.filter(
                    (ChangeLogEntry.branch.in_(branch_list))
                    | (ChangeLogEntry.account_id.in_(scoped_ids or ["__no_match__"]))
                )
            else:
                # Non-admin: restrict to entries tied to an allowed account OR
                # tied to an allowed branch name. Entries with NULL account
                # AND NULL branch (pure external factors) are shown only when
                # country matches — visible to everyone with analytics access.
                q = q.filter(
                    ChangeLogEntry.account_id.in_(scoped_ids or ["__no_match__"])
                    | ChangeLogEntry.branch.isnot(None)
                )

        # Other filters
        if category:
            valid = [c for c in category if c in ALL_CATEGORIES]
            if valid:
                q = q.filter(ChangeLogEntry.category.in_(valid))
        if source in ("auto", "manual"):
            q = q.filter(ChangeLogEntry.source == source)
        if platform:
            q = q.filter(ChangeLogEntry.platform == platform)
        if campaign_id:
            q = q.filter(ChangeLogEntry.campaign_id == campaign_id)
        if ad_set_id:
            q = q.filter(ChangeLogEntry.ad_set_id == ad_set_id)
        if ad_id:
            q = q.filter(ChangeLogEntry.ad_id == ad_id)

        total = q.count()
        rows = (
            q.order_by(ChangeLogEntry.occurred_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        items = _bulk_serialize(db, rows)

        return _api_response(
            data={
                "items": items,
                "total": total,
                "limit": limit,
                "offset": offset,
                "period": {"from": d_from.isoformat(), "to": d_to.isoformat()},
            }
        )
    except Exception as e:
        return _api_response(error=str(e))


# ---------------------------------------------------------------------------
# Manual entry CRUD
# ---------------------------------------------------------------------------


class ManualEntryCreate(BaseModel):
    category: str
    title: str
    description: str | None = None
    occurred_at: str | None = None  # ISO datetime; default = now
    country: str | None = None
    branch: str | None = None
    platform: str | None = None
    campaign_id: str | None = None
    ad_set_id: str | None = None
    ad_id: str | None = None
    source_url: str | None = None
    capture_baseline: bool = True


class ManualEntryPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    occurred_at: str | None = None
    country: str | None = None
    branch: str | None = None
    platform: str | None = None
    source_url: str | None = None
    category: str | None = None


def _parse_occurred_at(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        # Accept plain ISO or with 'Z'
        if val.endswith("Z"):
            val = val[:-1] + "+00:00"
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


@router.post("/changelog/manual")
def create_manual_entry(
    body: ManualEntryCreate,
    current_user: User = Depends(require_section("analytics", "edit")),
    db: Session = Depends(get_db),
):
    try:
        if body.category not in MANUAL_ALLOWED_CATEGORIES:
            return _api_response(
                error=f"Category '{body.category}' is not allowed for manual entries."
            )
        if not body.title or not body.title.strip():
            return _api_response(error="title is required")

        # Permission check: non-admin users can only log against branches they
        # have analytics-edit access to.
        if body.branch:
            ok, _scoped, err = scoped_account_ids(
                db,
                current_user,
                "analytics",
                requested_branches=[body.branch],
                min_level="edit",
            )
            if not ok:
                return _api_response(error=err)

        occurred_at = _parse_occurred_at(body.occurred_at) or datetime.now(timezone.utc)

        # Optional baseline capture
        snapshot = None
        if body.capture_baseline:
            snapshot = capture_baseline_snapshot(
                db,
                ad_id=body.ad_id,
                ad_set_id=body.ad_set_id,
                campaign_id=body.campaign_id,
                days=7,
            )

        entry = log_change(
            db,
            category=body.category,
            title=body.title,
            source="manual",
            triggered_by="manual",
            occurred_at=occurred_at,
            description=body.description,
            country=body.country.upper() if body.country else None,
            branch=body.branch,
            platform=body.platform,
            ad_id=body.ad_id,
            ad_set_id=body.ad_set_id,
            campaign_id=body.campaign_id,
            metrics_snapshot=snapshot,
            source_url=body.source_url,
            author_user_id=str(current_user.id),
        )
        if entry is None:
            return _api_response(error="Failed to create change log entry")
        db.commit()
        db.refresh(entry)
        return _api_response(data=_bulk_serialize(db, [entry])[0])
    except Exception as e:
        db.rollback()
        return _api_response(error=str(e))


@router.patch("/changelog/manual/{entry_id}")
def update_manual_entry(
    entry_id: str,
    body: ManualEntryPatch,
    current_user: User = Depends(require_section("analytics", "edit")),
    db: Session = Depends(get_db),
):
    try:
        entry = (
            db.query(ChangeLogEntry)
            .filter(ChangeLogEntry.id == entry_id, ChangeLogEntry.is_deleted.is_(False))
            .first()
        )
        if not entry:
            return _api_response(error="Entry not found")
        if entry.source != "manual":
            return _api_response(error="Auto entries are immutable")
        if not is_admin(current_user) and str(entry.author_user_id) != str(current_user.id):
            return _api_response(error="Only the author or an admin can edit this entry")

        updates = body.model_dump(exclude_unset=True)
        if "category" in updates:
            if updates["category"] not in MANUAL_ALLOWED_CATEGORIES:
                return _api_response(
                    error=f"Category '{updates['category']}' is not allowed for manual entries."
                )
            entry.category = updates["category"]
        if "title" in updates and updates["title"] is not None:
            entry.title = updates["title"][:200]
        if "description" in updates:
            entry.description = updates["description"]
        if "occurred_at" in updates and updates["occurred_at"]:
            parsed = _parse_occurred_at(updates["occurred_at"])
            if parsed:
                entry.occurred_at = parsed
        if "country" in updates:
            entry.country = updates["country"].upper() if updates["country"] else None
        if "branch" in updates:
            entry.branch = updates["branch"]
        if "platform" in updates:
            entry.platform = updates["platform"]
        if "source_url" in updates:
            entry.source_url = updates["source_url"]

        db.commit()
        db.refresh(entry)
        return _api_response(data=_bulk_serialize(db, [entry])[0])
    except Exception as e:
        db.rollback()
        return _api_response(error=str(e))


@router.delete("/changelog/manual/{entry_id}")
def delete_manual_entry(
    entry_id: str,
    current_user: User = Depends(require_section("analytics", "edit")),
    db: Session = Depends(get_db),
):
    try:
        entry = db.query(ChangeLogEntry).filter(ChangeLogEntry.id == entry_id).first()
        if not entry:
            return _api_response(error="Entry not found")
        if entry.is_deleted:
            return _api_response(data={"id": entry_id, "is_deleted": True})
        if entry.source != "manual":
            return _api_response(error="Auto entries are immutable")
        if not is_admin(current_user) and str(entry.author_user_id) != str(current_user.id):
            return _api_response(error="Only the author or an admin can delete this entry")

        entry.is_deleted = True
        entry.deleted_at = datetime.now(timezone.utc)
        entry.deleted_by = str(current_user.id)
        db.commit()
        return _api_response(data={"id": entry_id, "is_deleted": True})
    except Exception as e:
        db.rollback()
        return _api_response(error=str(e))


# ---------------------------------------------------------------------------
# Helper endpoints
# ---------------------------------------------------------------------------


@router.get("/changelog/categories")
def list_categories(
    current_user: User = Depends(get_current_user),
):
    """Return the canonical category lists for the frontend dropdowns."""
    return _api_response(
        data={
            "all": sorted(ALL_CATEGORIES),
            "manual_allowed": sorted(MANUAL_ALLOWED_CATEGORIES),
        }
    )


@router.post("/changelog/resolve-context")
def resolve_context(
    body: dict,
    current_user: User = Depends(require_section("analytics")),
    db: Session = Depends(get_db),
):
    """Preview the auto-resolved country/branch/platform for a given set of FK
    IDs — used by the manual entry form to prefill the country dropdown once a
    campaign is picked."""
    try:
        ctx = resolve_entity_context(
            db,
            ad_id=body.get("ad_id"),
            ad_set_id=body.get("ad_set_id"),
            campaign_id=body.get("campaign_id"),
            account_id=body.get("account_id"),
        )
        return _api_response(data=ctx)
    except Exception as e:
        return _api_response(error=str(e))
