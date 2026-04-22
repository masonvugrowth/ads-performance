"""Public landing-page router — unauthenticated endpoints used by the Next.js
SSR renderer at `/lp/[slug]` and lightweight client-side event beacons.

Endpoints:

    GET /api/public/lp/{domain}/{slug}
        → Returns the currently-PUBLISHED version's content JSON for the
          matching managed landing page. Used by Next.js to SSR the page.
          Responds with 404 if the page is not published (draft/archived).

    POST /api/public/lp/{page_id}/event
        → Lightweight beacon the public page fires for custom events
          (page_view, cta_click, etc.). We DO NOT double-track things that
          Clarity already tracks (scroll depth, rage clicks, etc.) — this is
          only for conversion-funnel events Clarity can't see.

These routes are intentionally open (no auth). CORS is handled globally.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.landing_page import LandingPage, STATUS_PUBLISHED
from app.models.landing_page_version import LandingPageVersion

router = APIRouter()


def _api(data=None, error=None):
    return {
        "success": error is None,
        "data": data,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/public/lp/{domain}/{slug:path}")
def get_published_content(
    domain: str,
    slug: str,
    db: Session = Depends(get_db),
):
    """Return the PUBLISHED content for a managed landing page.

    `slug:path` allows a slug with slashes (rare but supported).
    """
    slug = slug.strip("/")
    page = (
        db.query(LandingPage)
        .filter(
            LandingPage.domain == domain.lower(),
            LandingPage.slug == slug,
            LandingPage.is_active.is_(True),
        )
        .one_or_none()
    )
    if page is None:
        raise HTTPException(status_code=404, detail="landing page not found")
    if page.status != STATUS_PUBLISHED or page.current_version_id is None:
        raise HTTPException(status_code=404, detail="landing page not published")

    version = (
        db.query(LandingPageVersion)
        .filter(LandingPageVersion.id == page.current_version_id)
        .one_or_none()
    )
    if version is None:
        raise HTTPException(status_code=404, detail="version missing")

    return _api({
        "page": {
            "id": page.id,
            "title": page.title,
            "domain": page.domain,
            "slug": page.slug,
            "language": page.language,
            "ta": page.ta,
            "clarity_project_id": page.clarity_project_id,
            "published_at": page.published_at.isoformat() if page.published_at else None,
        },
        "version": {
            "id": version.id,
            "version_num": version.version_num,
            "content": version.content,
        },
    })


class EventReq(BaseModel):
    event_type: str  # page_view | cta_click | book_direct_click | scroll_milestone
    event_label: str | None = None
    utm_source: str | None = None
    utm_campaign: str | None = None
    utm_content: str | None = None
    raw: dict | None = None


@router.post("/public/lp/{page_id}/event")
def record_event(
    page_id: str,
    body: EventReq,
    db: Session = Depends(get_db),
):
    """Fire-and-forget event beacon from the public page.

    For now we log-only (so the page stays fast). If/when conversion events
    matter enough to persist, add a landing_page_events table in a follow-up
    migration — for Phase 1, Clarity + MetricsCache cover all playbook asks.
    """
    page = db.query(LandingPage).filter(LandingPage.id == page_id).one_or_none()
    if page is None:
        raise HTTPException(status_code=404, detail="landing page not found")

    import logging

    logging.getLogger("landing_page_events").info(
        "[lp-event] page=%s type=%s label=%s utm=(%s/%s/%s)",
        page_id,
        body.event_type,
        body.event_label,
        body.utm_source,
        body.utm_campaign,
        body.utm_content,
    )
    return _api({"accepted": True})
