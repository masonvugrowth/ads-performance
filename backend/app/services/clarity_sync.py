"""Clarity sync: pull daily Data Export API results → landing_page_clarity_snapshots.

The Clarity API returns CUMULATIVE aggregates over the last N days (max 3).
It does NOT expose per-day breakdowns. To fill our per-day snapshot table
and survive a missed cron run, we call the API 3 times (numOfDays=1, 2, 3)
and SUBTRACT consecutive results to derive each day's deltas:

    day(-1) = cumulative_1d
    day(-2) = cumulative_2d  -  cumulative_1d
    day(-3) = cumulative_3d  -  cumulative_2d

For count metrics (sessions, rage_clicks, ...) subtraction is exact.
For weighted-average metrics (avg_scroll_depth, pages_per_session) we
weight by sessions — accurate when session counts are stable, slightly
off when they swing wildly, but fine for a trend dashboard.

Flow per day:
1. Call Clarity Data Export API for numOfDays=1..N with dimension1=URL.
2. Reshape each response into {url: {metrics...}}.
3. Compute per-day deltas via subtraction.
4. For each (url, day):
   a. Normalize → (host, slug, utm_source, utm_campaign, utm_content).
   b. Look up landing_pages row by (domain, slug); auto-create a
      DISCOVERED/external row if missing.
   c. Upsert a snapshot row keyed by (page, day, utm_source, utm_campaign, utm_content).

The aggregate row per (page, day) sums across all UTM variants (utm_*=NULL)
so the dashboard can show totals without JOIN.

Idempotent: re-running overwrites snapshots for the same (page, day, utm)
tuple.
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


SUM_KEYS = [
    "sessions", "bot_sessions", "distinct_users",
    "total_time_sec", "active_time_sec",
    "dead_clicks", "rage_clicks", "error_clicks",
    "quickback_clicks", "excessive_scrolls", "script_errors",
]
AVG_KEYS = ["pages_per_session", "avg_scroll_depth"]


def _delta(cum_cur: dict[str, Any], cum_prev: dict[str, Any]) -> dict[str, Any]:
    """Compute a single day's metrics from two consecutive cumulative buckets.

    For count fields: delta = cur - prev (clamped to 0 to handle late-arriving
    Clarity data where cumulative can briefly dip).

    For weighted-average fields: weighted by `sessions` (the closest proxy we
    have to event count). If the day has zero new sessions, return None —
    an average over no samples is undefined.
    """
    out: dict[str, Any] = {}
    for k in SUM_KEYS:
        out[k] = max(0, (cum_cur.get(k) or 0) - (cum_prev.get(k) or 0))

    day_sessions = out["sessions"]
    for k in AVG_KEYS:
        a_cur = cum_cur.get(k)
        a_prev = cum_prev.get(k)
        w_cur = cum_cur.get("sessions") or 0
        w_prev = cum_prev.get("sessions") or 0
        if a_cur is None:
            out[k] = None
            continue
        if w_prev == 0 or a_prev is None:
            # First day this URL appears — use raw current value
            out[k] = a_cur
            continue
        if w_cur - w_prev <= 0:
            # No new sessions on this day → average is undefined
            out[k] = None
            continue
        sum_cur = a_cur * w_cur
        sum_prev = a_prev * w_prev
        out[k] = (sum_cur - sum_prev) / (w_cur - w_prev)

    out["raw"] = {"from_subtract": True}
    return out


def run_clarity_sync(
    db: Session,
    *,
    target_date: date | None = None,
    days_back: int = 3,
    auto_create_pages: bool = True,
) -> dict[str, Any]:
    """Pull up to 3 days of Clarity data and upsert per-day snapshots.

    `days_back` (1-3): how many days to backfill. Default 3 (API maximum) —
    this keeps the snapshot table gap-free even if the cron misses a run.

    Returns a summary dict with per-day ingest counts.
    """
    if days_back < 1 or days_back > 3:
        raise ValueError("days_back must be in 1..3 (Clarity API limit)")

    today = datetime.now(timezone.utc).date()

    # Optimization: Clarity Data Export API has a strict daily quota (~10
    # requests/project/day). Skip cumulative pulls we don't need by checking
    # the DB first — if day(-N) already has snapshots, we don't need to refetch.
    existing_days = {
        row[0]
        for row in db.query(LandingPageClaritySnapshot.date)
        .filter(LandingPageClaritySnapshot.date >= today - timedelta(days=days_back))
        .distinct()
        .all()
    }
    missing_days = [
        n for n in range(1, days_back + 1)
        if (today - timedelta(days=n)) not in existing_days
    ]
    if not missing_days:
        logger.info("[clarity-sync] all %d day(s) already in DB — skipping API calls", days_back)
        return {
            "days_back": days_back,
            "per_day": {},
            "created_external": 0,
            "errors": 0,
            "skipped_reason": "all days already synced",
        }

    # To compute per-day deltas via subtraction we need BOTH the target day's
    # cumulative AND the prior day's cumulative. So if we need day(-N), we
    # need cumulative for numOfDays=N AND numOfDays=(N-1).
    needed_cumulative = set()
    for n in missing_days:
        needed_cumulative.add(n)
        if n > 1:
            needed_cumulative.add(n - 1)
    logger.info("[clarity-sync] missing days=%s, cumulative pulls needed=%s",
                missing_days, sorted(needed_cumulative))

    # Pull cumulative buckets for the needed numOfDays values
    cumulative: dict[int, dict[str, dict[str, Any]]] = {0: {}}
    for n in sorted(needed_cumulative):
        try:
            raw = fetch_project_live_insights(num_of_days=n, dimension1="URL")
            cumulative[n] = reshape_by_url(raw)
            logger.info("[clarity-sync] numOfDays=%d → %d URLs", n, len(cumulative[n]))
        except Exception as e:
            logger.exception("[clarity-sync] fetch numOfDays=%d failed", n)
            return {
                "days_back": days_back,
                "per_day": {},
                "created_external": 0,
                "errors": 1,
                "fetch_error": str(e),
                "partial_cumulative": sorted(cumulative.keys()),
            }

    summary: dict[str, Any] = {
        "days_back": days_back,
        "per_day": {},
        "created_external": 0,
        "errors": 0,
    }

    # Cache page lookups across all days
    per_page_cache: dict[str, Any] = {}

    # Loop only over missing days; each needs both cumulative[N] and cumulative[N-1]
    for n in missing_days:
        day_date = today - timedelta(days=n)
        cur_bucket = cumulative.get(n, {})
        prev_bucket = cumulative.get(n - 1, {})
        if n > 1 and not prev_bucket:
            # Couldn't fetch the baseline — skip this day
            logger.warning("[clarity-sync] day=%s: missing cumulative_%d baseline, skipping", day_date, n - 1)
            continue

        # Collect URLs observed in EITHER current or prev cumulative window
        all_urls = set(cur_bucket.keys()) | set(prev_bucket.keys())

        # Build per-URL delta metrics for this day
        day_by_url: dict[str, dict[str, Any]] = {}
        for url in all_urls:
            cur = cur_bucket.get(url, {})
            prev = prev_bucket.get(url, {})
            day_metrics = _delta(cur, prev)
            # Skip URLs with zero activity that day (noise reduction)
            if day_metrics["sessions"] == 0 and all(day_metrics.get(k, 0) == 0 for k in ("dead_clicks", "rage_clicks", "error_clicks", "quickback_clicks")):
                continue
            day_by_url[url] = day_metrics

        day_summary = {
            "date": day_date.isoformat(),
            "urls_ingested": 0,
            "pages_touched": 0,
        }

        # Dedupe URLs that normalize to same (host, slug, utm_*) tuple
        merged: dict[tuple[str, Any, Any, Any], dict[str, Any]] = {}
        for url, metrics in day_by_url.items():
            nu = normalize_url(url)
            if nu is None:
                continue

            key_host_slug = f"{nu.host}|{nu.slug}"
            page = per_page_cache.get(key_host_slug)
            if page is None:
                page = (
                    db.query(LandingPage)
                    .filter(LandingPage.domain == nu.host, LandingPage.slug == nu.slug)
                    .one_or_none()
                )
                if page is None:
                    if not auto_create_pages:
                        continue
                    page = get_or_create_external_page(
                        db,
                        raw_url=url,
                        title_fallback=f"{nu.host}/{nu.slug}".rstrip("/"),
                    )
                    if page is None:
                        continue
                    summary["created_external"] += 1
                per_page_cache[key_host_slug] = page

            key = (
                page.id,
                nu.utm.get("utm_source"),
                nu.utm.get("utm_campaign"),
                nu.utm.get("utm_content"),
            )
            if key not in merged:
                merged[key] = {"metrics": dict(metrics), "url_raw": url, "page_id": page.id}
            else:
                merged[key]["metrics"] = _merge(merged[key]["metrics"], metrics)

        # Upsert per-UTM rows
        per_page_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for (page_id, utm_s, utm_c, utm_ct), bundle in merged.items():
            try:
                _upsert_snapshot(
                    db,
                    landing_page_id=page_id,
                    target_date=day_date,
                    utm_source=utm_s,
                    utm_campaign=utm_c,
                    utm_content=utm_ct,
                    metrics=bundle["metrics"],
                    url_raw=bundle["url_raw"],
                )
                day_summary["urls_ingested"] += 1
                per_page_day[page_id].append(bundle["metrics"])
            except Exception:
                logger.exception("[clarity-sync] day=%s failed upsert page=%s utm=%s/%s/%s",
                                 day_date, page_id, utm_s, utm_c, utm_ct)
                summary["errors"] += 1

        # Aggregate row (utm_*=NULL) per page
        for page_id, rows in per_page_day.items():
            agg: dict[str, Any] = {}
            for m in rows:
                agg = _merge(agg, m) if agg else dict(m)
            try:
                _upsert_snapshot(
                    db,
                    landing_page_id=page_id,
                    target_date=day_date,
                    utm_source=None,
                    utm_campaign=None,
                    utm_content=None,
                    metrics=agg,
                    url_raw=None,
                )
                day_summary["pages_touched"] += 1
            except Exception:
                logger.exception("[clarity-sync] day=%s failed agg upsert page=%s", day_date, page_id)
                summary["errors"] += 1

        summary["per_day"][day_date.isoformat()] = day_summary
        logger.info("[clarity-sync] day=%s: %s", day_date, day_summary)

    db.commit()
    logger.info("[clarity-sync] done: %s", summary)
    return summary
