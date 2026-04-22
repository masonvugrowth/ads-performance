"""Clarity sync: pull daily Data Export API results → landing_page_clarity_snapshots.

Flow:
1. Call Clarity Data Export API (numOfDays=1, dimension1=URL).
2. Reshape payload into {url: {metrics...}}.
3. For each URL:
   a. Normalize → (host, slug, utm_source, utm_campaign, utm_content).
   b. Look up landing_pages row by (domain, slug); if missing and the URL
      domain matches a staymeander subdomain, auto-create a DISCOVERED/external
      landing page (so first-seen LPs still get tracked).
   c. Upsert a snapshot row: per-UTM-breakdown AND aggregate (NULL UTMs).

The aggregate row sums across all UTM variants so the dashboard can show
total landing-page numbers without JOIN.

Idempotent: re-running for the same day overwrites the previous snapshot
for that date/landing_page/UTM triple.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.landing_page import LandingPage
from app.models.landing_page_clarity import LandingPageClaritySnapshot
from app.services.clarity_client import fetch_project_live_insights, reshape_by_url
from app.services.landing_page_service import get_or_create_external_page
from app.services.landing_page_url_normalizer import normalize_url

logger = logging.getLogger(__name__)


def _upsert_snapshot(
    db: Session,
    *,
    landing_page_id: str,
    target_date: date,
    utm_source: str | None,
    utm_campaign: str | None,
    utm_content: str | None,
    metrics: dict[str, Any],
    url_raw: str | None,
) -> None:
    """Upsert a single snapshot row. Unique key: (page, date, utm_source, utm_campaign, utm_content)."""
    row = (
        db.query(LandingPageClaritySnapshot)
        .filter(
            LandingPageClaritySnapshot.landing_page_id == landing_page_id,
            LandingPageClaritySnapshot.date == target_date,
            # NULL-safe equality — SQLAlchemy treats `== None` as IS NULL
            LandingPageClaritySnapshot.utm_source == utm_source if utm_source is not None
            else LandingPageClaritySnapshot.utm_source.is_(None),
            LandingPageClaritySnapshot.utm_campaign == utm_campaign if utm_campaign is not None
            else LandingPageClaritySnapshot.utm_campaign.is_(None),
            LandingPageClaritySnapshot.utm_content == utm_content if utm_content is not None
            else LandingPageClaritySnapshot.utm_content.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        row = LandingPageClaritySnapshot(
            landing_page_id=landing_page_id,
            date=target_date,
            utm_source=utm_source,
            utm_campaign=utm_campaign,
            utm_content=utm_content,
        )
        db.add(row)

    row.url_raw = url_raw
    row.sessions = metrics.get("sessions", 0)
    row.bot_sessions = metrics.get("bot_sessions", 0)
    row.distinct_users = metrics.get("distinct_users", 0)
    row.pages_per_session = metrics.get("pages_per_session")
    row.avg_scroll_depth = metrics.get("avg_scroll_depth")
    row.total_time_sec = metrics.get("total_time_sec", 0)
    row.active_time_sec = metrics.get("active_time_sec", 0)
    row.dead_clicks = metrics.get("dead_clicks", 0)
    row.rage_clicks = metrics.get("rage_clicks", 0)
    row.error_clicks = metrics.get("error_clicks", 0)
    row.quickback_clicks = metrics.get("quickback_clicks", 0)
    row.excessive_scrolls = metrics.get("excessive_scrolls", 0)
    row.script_errors = metrics.get("script_errors", 0)
    row.raw_data = metrics.get("raw")


def _merge(base: dict[str, Any], add: dict[str, Any]) -> dict[str, Any]:
    """Sum-merge two metrics dicts. Used to aggregate UTM breakdowns → page total."""
    sum_keys = [
        "sessions", "bot_sessions", "distinct_users",
        "total_time_sec", "active_time_sec",
        "dead_clicks", "rage_clicks", "error_clicks",
        "quickback_clicks", "excessive_scrolls", "script_errors",
    ]
    out = dict(base)
    for k in sum_keys:
        out[k] = base.get(k, 0) + add.get(k, 0)
    # For ratios/percents we take the weighted average by sessions (close enough for
    # a dashboard signal — precise per-session stats come from the UTM rows).
    for k in ("pages_per_session", "avg_scroll_depth"):
        a = base.get(k)
        b = add.get(k)
        wa = base.get("sessions", 0) or 0
        wb = add.get("sessions", 0) or 0
        if a is None and b is None:
            out[k] = None
        elif a is None:
            out[k] = b
        elif b is None:
            out[k] = a
        elif wa + wb == 0:
            out[k] = (a + b) / 2
        else:
            out[k] = (a * wa + b * wb) / (wa + wb)
    out["raw"] = {"agg": True}
    return out


def run_clarity_sync(
    db: Session,
    *,
    target_date: date | None = None,
    auto_create_pages: bool = True,
) -> dict[str, Any]:
    """Pull yesterday's Clarity data and upsert snapshots.

    Returns a summary dict: pages_touched, urls_ingested, created_external,
    errors.
    """
    if target_date is None:
        # numOfDays=1 returns data for "today so far" in Clarity. For a stable
        # daily snapshot we run the cron at 01:00 UTC and write to yesterday.
        target_date = (datetime.now(timezone.utc).date() - timedelta(days=1))

    logger.info("[clarity-sync] target_date=%s", target_date)
    raw = fetch_project_live_insights(num_of_days=1, dimension1="URL")
    by_url = reshape_by_url(raw)
    logger.info("[clarity-sync] %d unique URLs reshaped", len(by_url))

    summary = {
        "target_date": target_date.isoformat(),
        "urls_ingested": 0,
        "pages_touched": 0,
        "created_external": 0,
        "errors": 0,
    }

    # Multiple raw URLs from Clarity can normalize to the SAME (host, slug,
    # utm_source, utm_campaign, utm_content) tuple (they differ only in
    # fbclid/gclid, which we strip). We must merge metrics within each tuple
    # BEFORE upserting, otherwise the unique constraint blows up on INSERT.
    #
    # Key: (page_id, utm_source, utm_campaign, utm_content)
    # Value: merged metrics dict + one representative url_raw
    merged: dict[tuple[str, Any, Any, Any], dict[str, Any]] = {}
    per_page_page_obj: dict[str, Any] = {}

    for url, metrics in by_url.items():
        n = normalize_url(url)
        if n is None:
            continue

        # Find or create landing_pages row
        page = per_page_page_obj.get(f"{n.host}|{n.slug}")
        if page is None:
            page = (
                db.query(LandingPage)
                .filter(LandingPage.domain == n.host, LandingPage.slug == n.slug)
                .one_or_none()
            )
            if page is None:
                if not auto_create_pages:
                    continue
                page = get_or_create_external_page(
                    db,
                    raw_url=url,
                    title_fallback=f"{n.host}/{n.slug}".rstrip("/"),
                )
                if page is None:
                    continue
                summary["created_external"] += 1
            per_page_page_obj[f"{n.host}|{n.slug}"] = page

        key = (
            page.id,
            n.utm.get("utm_source"),
            n.utm.get("utm_campaign"),
            n.utm.get("utm_content"),
        )
        if key not in merged:
            merged[key] = {"metrics": dict(metrics), "url_raw": url, "page_id": page.id}
        else:
            merged[key]["metrics"] = _merge(merged[key]["metrics"], metrics)

    # Now upsert one row per normalized tuple
    per_page: dict[str, list[tuple[Any, dict[str, Any]]]] = defaultdict(list)
    for (page_id, utm_s, utm_c, utm_ct), bundle in merged.items():
        try:
            _upsert_snapshot(
                db,
                landing_page_id=page_id,
                target_date=target_date,
                utm_source=utm_s,
                utm_campaign=utm_c,
                utm_content=utm_ct,
                metrics=bundle["metrics"],
                url_raw=bundle["url_raw"],
            )
            summary["urls_ingested"] += 1
            per_page[page_id].append(
                ({"utm_source": utm_s, "utm_campaign": utm_c, "utm_content": utm_ct}, bundle["metrics"])
            )
        except Exception:
            logger.exception("[clarity-sync] failed upsert page=%s utm=%s/%s/%s", page_id, utm_s, utm_c, utm_ct)
            summary["errors"] += 1

    # Aggregate row per page: sum all UTM breakdowns into utm_source=NULL row
    for page_id, rows in per_page.items():
        agg: dict[str, Any] = {}
        for _utm, m in rows:
            agg = _merge(agg, m) if agg else dict(m)
        try:
            _upsert_snapshot(
                db,
                landing_page_id=page_id,
                target_date=target_date,
                utm_source=None,
                utm_campaign=None,
                utm_content=None,
                metrics=agg,
                url_raw=None,
            )
            summary["pages_touched"] += 1
        except Exception:
            logger.exception("[clarity-sync] failed agg upsert page=%s", page_id)
            summary["errors"] += 1

    db.commit()
    logger.info("[clarity-sync] done: %s", summary)
    return summary
