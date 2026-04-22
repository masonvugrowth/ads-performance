"""Microsoft Clarity Data Export API client.

Docs: https://learn.microsoft.com/en-us/clarity/setup-and-installation/clarity-data-export-api

Endpoint:
    GET https://www.clarity.ms/export-data/api/v1/project-live-insights
Auth:
    Authorization: Bearer <JWT from Clarity settings>  (scope: Data.Export)
Params:
    numOfDays: 1..3  (required)
    dimension1..3: URL | Browser | Device | OS | Country | ReferrerURL | Channel
Response:
    [ { metricName, information: [ { ...fields..., <dimension>: "value" } ] }, ... ]

We only use `dimension1=URL` because we need to attribute Clarity metrics back
to our `landing_pages.domain + slug`. Adding more dimensions would balloon
the response and complicate matching.

Metrics returned (per our observations on 2026-04-22):
    - Traffic           (sessionsCount? No — totalSessionCount, totalBotSessionCount,
                          distinctUserCount, pagesPerSessionPercentage)
    - EngagementTime    (totalTime, activeTime — seconds as strings)
    - ScrollDepth       (averageScrollDepth — % as string)
    - DeadClickCount    (subTotal, sessionsCount, pagesViews — counts as strings)
    - RageClickCount    (same structure)
    - ErrorClickCount   (same)
    - QuickbackClick    (same)
    - ExcessiveScroll   (same)
    - ScriptErrorCount  (same)

All numeric fields arrive as strings — we coerce to int/float during parsing.
"""
from __future__ import annotations

import logging
from typing import Any

import requests

from app.config import settings

logger = logging.getLogger(__name__)

CLARITY_BASE_URL = "https://www.clarity.ms/export-data/api/v1"
DEFAULT_TIMEOUT = 60  # seconds — the payload can be several MB


class ClarityAPIError(Exception):
    """Raised for non-2xx responses or malformed payloads."""


def fetch_project_live_insights(
    *,
    num_of_days: int = 1,
    dimension1: str = "URL",
    dimension2: str | None = None,
    dimension3: str | None = None,
    token: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    """Call Clarity's project-live-insights endpoint and return parsed JSON.

    Raises ClarityAPIError on HTTP errors or invalid JSON.
    """
    if num_of_days < 1 or num_of_days > 3:
        raise ValueError("num_of_days must be 1, 2, or 3 (Clarity API limit)")

    bearer = token or settings.CLARITY_API_TOKEN
    if not bearer:
        raise ClarityAPIError("CLARITY_API_TOKEN is not configured")

    params: dict[str, str] = {"numOfDays": str(num_of_days), "dimension1": dimension1}
    if dimension2:
        params["dimension2"] = dimension2
    if dimension3:
        params["dimension3"] = dimension3

    headers = {"Authorization": f"Bearer {bearer}"}
    url = f"{CLARITY_BASE_URL}/project-live-insights"

    logger.info("[clarity] GET %s params=%s", url, params)
    resp = requests.get(url, headers=headers, params=params, timeout=timeout)
    if resp.status_code != 200:
        raise ClarityAPIError(
            f"Clarity API returned {resp.status_code}: {resp.text[:500]}"
        )
    try:
        data = resp.json()
    except ValueError as e:  # json parse error
        raise ClarityAPIError(f"Clarity API returned non-JSON: {e}") from e
    if not isinstance(data, list):
        raise ClarityAPIError(f"Clarity API returned non-list: {type(data)}")
    logger.info("[clarity] received %d metric blocks", len(data))
    return data


def _to_int(v: Any) -> int:
    if v is None or v == "":
        return 0
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def reshape_by_url(data: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Transform Clarity's [metricBlock, ...] into { url: { metric: {...} } }.

    Output schema per URL (all numeric, 0 when absent):
        {
          "sessions": int, "bot_sessions": int, "distinct_users": int,
          "pages_per_session": float | None,
          "avg_scroll_depth": float | None,
          "total_time_sec": int, "active_time_sec": int,
          "dead_clicks": int, "rage_clicks": int, "error_clicks": int,
          "quickback_clicks": int, "excessive_scrolls": int, "script_errors": int,
          "raw": { metricName: item, ... },
        }
    """
    out: dict[str, dict[str, Any]] = {}

    def bucket(url: str) -> dict[str, Any]:
        if url not in out:
            out[url] = {
                "sessions": 0,
                "bot_sessions": 0,
                "distinct_users": 0,
                "pages_per_session": None,
                "avg_scroll_depth": None,
                "total_time_sec": 0,
                "active_time_sec": 0,
                "dead_clicks": 0,
                "rage_clicks": 0,
                "error_clicks": 0,
                "quickback_clicks": 0,
                "excessive_scrolls": 0,
                "script_errors": 0,
                "raw": {},
            }
        return out[url]

    click_metric_map = {
        "DeadClickCount": "dead_clicks",
        "RageClickCount": "rage_clicks",
        "ErrorClickCount": "error_clicks",
        "QuickbackClick": "quickback_clicks",
        "ExcessiveScroll": "excessive_scrolls",
        "ScriptErrorCount": "script_errors",
    }

    for block in data:
        metric = block.get("metricName")
        for item in block.get("information", []) or []:
            url = item.get("Url")
            if not url:
                continue
            b = bucket(url)
            b["raw"].setdefault(metric, []).append(item)

            if metric == "Traffic":
                b["sessions"] = _to_int(item.get("totalSessionCount"))
                b["bot_sessions"] = _to_int(item.get("totalBotSessionCount"))
                b["distinct_users"] = _to_int(item.get("distinctUserCount"))
                b["pages_per_session"] = _to_float(item.get("pagesPerSessionPercentage"))

            elif metric == "EngagementTime":
                b["total_time_sec"] = _to_int(item.get("totalTime"))
                b["active_time_sec"] = _to_int(item.get("activeTime"))

            elif metric == "ScrollDepth":
                b["avg_scroll_depth"] = _to_float(item.get("averageScrollDepth"))

            elif metric in click_metric_map:
                # `subTotal` is the count of events on that URL
                b[click_metric_map[metric]] = _to_int(item.get("subTotal"))

    return out
