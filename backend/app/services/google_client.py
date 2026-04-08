"""Google Ads API client.

Fetches campaigns, ad groups, ads (RSA), asset groups (PMax),
and metrics from the Google Ads API using GAQL queries.
Uses the google-ads Python SDK.
"""

import logging
from datetime import date, timedelta
from typing import Any

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from app.config import settings

logger = logging.getLogger(__name__)

# Status normalization: Google -> internal convention
_STATUS_MAP = {
    "ENABLED": "ACTIVE",
    "PAUSED": "PAUSED",
    "REMOVED": "ARCHIVED",
}

# Asset field type -> simplified asset_type
_FIELD_TYPE_MAP = {
    "HEADLINE": "HEADLINE",
    "DESCRIPTION": "DESCRIPTION",
    "MARKETING_IMAGE": "IMAGE",
    "SQUARE_MARKETING_IMAGE": "IMAGE",
    "PORTRAIT_MARKETING_IMAGE": "IMAGE",
    "LANDSCAPE_LOGO": "LOGO",
    "SQUARE_LOGO": "LOGO",
    "LOGO": "LOGO",
    "YOUTUBE_VIDEO": "VIDEO",
    "CALL_TO_ACTION_SELECTION": "CALL_TO_ACTION",
    "BUSINESS_NAME": "BUSINESS_NAME",
    "LONG_HEADLINE": "HEADLINE",
}


def _get_client() -> GoogleAdsClient:
    """Create GoogleAdsClient from config settings."""
    credentials = {
        "developer_token": settings.GOOGLE_DEVELOPER_TOKEN,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "refresh_token": settings.GOOGLE_REFRESH_TOKEN,
        "login_customer_id": settings.GOOGLE_LOGIN_CUSTOMER_ID.replace("-", ""),
        "use_proto_plus": True,
    }
    return GoogleAdsClient.load_from_dict(credentials)


def _normalize_status(status_enum: Any) -> str:
    """Convert Google Ads status enum to internal convention."""
    name = str(status_enum).split(".")[-1] if not isinstance(status_enum, str) else status_enum
    return _STATUS_MAP.get(name, name)


def _micros_to_currency(micros: int | None) -> float | None:
    """Convert Google Ads micros (1,000,000 = 1 unit) to currency float."""
    if micros is None:
        return None
    return micros / 1_000_000


def _search_stream(client: GoogleAdsClient, customer_id: str, query: str) -> list[Any]:
    """Execute a GAQL query via SearchStream and collect all rows."""
    ga_service = client.get_service("GoogleAdsService")
    stream = ga_service.search_stream(customer_id=customer_id, query=query)
    rows = []
    for batch in stream:
        for row in batch.results:
            rows.append(row)
    return rows


def fetch_campaigns(customer_id: str) -> list[dict]:
    """Fetch all active/paused campaigns for a Google Ads account.

    Returns list of dicts compatible with the campaigns table schema.
    """
    customer_id = customer_id.replace("-", "")
    client = _get_client()

    query = """
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            campaign.advertising_channel_type,
            campaign_budget.amount_micros,
            campaign.start_date,
            campaign.end_date
        FROM campaign
        WHERE campaign.status != 'REMOVED'
    """

    try:
        rows = _search_stream(client, customer_id, query)
        results = []
        for row in rows:
            c = row.campaign
            campaign_type = str(c.advertising_channel_type).split(".")[-1]
            results.append({
                "platform_campaign_id": str(c.id),
                "name": c.name,
                "status": _normalize_status(c.status),
                "objective": campaign_type,  # PERFORMANCE_MAX, SEARCH, DISPLAY, etc.
                "daily_budget": _micros_to_currency(
                    row.campaign_budget.amount_micros if row.campaign_budget else None
                ),
                "lifetime_budget": None,  # Google uses daily budgets
                "start_date": c.start_date if c.start_date else None,
                "end_date": c.end_date if c.end_date else None,
                "raw_data": {
                    "campaign_id": str(c.id),
                    "campaign_type": campaign_type,
                    "budget_micros": row.campaign_budget.amount_micros if row.campaign_budget else None,
                },
            })
        logger.info("Fetched %d campaigns from Google account %s", len(results), customer_id)
        return results
    except GoogleAdsException as ex:
        logger.exception("Google Ads API error fetching campaigns for %s: %s", customer_id, ex.failure)
        raise
    except Exception:
        logger.exception("Failed to fetch campaigns from Google account %s", customer_id)
        raise


def fetch_ad_groups(customer_id: str) -> list[dict]:
    """Fetch ad groups (Search campaigns). Maps to ad_sets table."""
    customer_id = customer_id.replace("-", "")
    client = _get_client()

    query = """
        SELECT
            ad_group.id,
            ad_group.name,
            ad_group.status,
            ad_group.campaign,
            campaign.id
        FROM ad_group
        WHERE ad_group.status != 'REMOVED'
    """

    try:
        rows = _search_stream(client, customer_id, query)
        results = []
        for row in rows:
            ag = row.ad_group
            results.append({
                "platform_adset_id": str(ag.id),
                "campaign_id": str(row.campaign.id),
                "name": ag.name,
                "status": _normalize_status(ag.status),
                "optimization_goal": None,
                "billing_event": None,
                "daily_budget": None,
                "lifetime_budget": None,
                "targeting": None,
                "raw_data": {"ad_group_id": str(ag.id)},
            })
        logger.info("Fetched %d ad groups from Google account %s", len(results), customer_id)
        return results
    except GoogleAdsException as ex:
        logger.exception("Google Ads API error fetching ad groups for %s: %s", customer_id, ex.failure)
        raise
    except Exception:
        logger.exception("Failed to fetch ad groups from Google account %s", customer_id)
        raise


def fetch_ads(customer_id: str) -> list[dict]:
    """Fetch RSA ads (responsive search ads). Maps to ads table."""
    customer_id = customer_id.replace("-", "")
    client = _get_client()

    query = """
        SELECT
            ad_group_ad.ad.id,
            ad_group_ad.ad.name,
            ad_group_ad.ad.type,
            ad_group_ad.status,
            ad_group_ad.ad.responsive_search_ad.headlines,
            ad_group_ad.ad.responsive_search_ad.descriptions,
            ad_group.id,
            campaign.id
        FROM ad_group_ad
        WHERE ad_group_ad.status != 'REMOVED'
    """

    try:
        rows = _search_stream(client, customer_id, query)
        results = []
        for row in rows:
            ad = row.ad_group_ad.ad
            rsa = ad.responsive_search_ad

            headlines = [h.text for h in rsa.headlines] if rsa and rsa.headlines else []
            descriptions = [d.text for d in rsa.descriptions] if rsa and rsa.descriptions else []

            ad_type = str(ad.type_).split(".")[-1] if ad.type_ else "UNKNOWN"

            results.append({
                "platform_ad_id": str(ad.id),
                "platform_adset_id": str(row.ad_group.id),
                "platform_campaign_id": str(row.campaign.id),
                "name": ad.name or f"Ad {ad.id}",
                "status": _normalize_status(row.ad_group_ad.status),
                "creative_id": None,
                "raw_data": {
                    "ad_id": str(ad.id),
                    "ad_type": ad_type,
                    "headlines": headlines,
                    "descriptions": descriptions,
                },
            })
        logger.info("Fetched %d ads from Google account %s", len(results), customer_id)
        return results
    except GoogleAdsException as ex:
        logger.exception("Google Ads API error fetching ads for %s: %s", customer_id, ex.failure)
        raise
    except Exception:
        logger.exception("Failed to fetch ads from Google account %s", customer_id)
        raise


def fetch_asset_groups(customer_id: str) -> list[dict]:
    """Fetch PMax asset groups."""
    customer_id = customer_id.replace("-", "")
    client = _get_client()

    query = """
        SELECT
            asset_group.id,
            asset_group.name,
            asset_group.status,
            asset_group.campaign,
            campaign.id
        FROM asset_group
        WHERE asset_group.status != 'REMOVED'
    """

    try:
        rows = _search_stream(client, customer_id, query)
        results = []
        for row in rows:
            ag = row.asset_group
            # Get final_urls via a separate query or from listing signals
            results.append({
                "platform_asset_group_id": str(ag.id),
                "campaign_id": str(row.campaign.id),
                "name": ag.name,
                "status": _normalize_status(ag.status),
                "final_urls": [],
                "raw_data": {"asset_group_id": str(ag.id)},
            })
        logger.info("Fetched %d asset groups from Google account %s", len(results), customer_id)
        return results
    except GoogleAdsException as ex:
        logger.exception("Google Ads API error fetching asset groups for %s: %s", customer_id, ex.failure)
        raise
    except Exception:
        logger.exception("Failed to fetch asset groups from Google account %s", customer_id)
        raise


def fetch_asset_group_assets(customer_id: str) -> list[dict]:
    """Fetch assets linked to PMax asset groups."""
    customer_id = customer_id.replace("-", "")
    client = _get_client()

    query = """
        SELECT
            asset_group_asset.asset,
            asset_group_asset.asset_group,
            asset_group_asset.field_type,
            asset_group_asset.performance_label,
            asset.id,
            asset.name,
            asset.text_asset.text,
            asset.image_asset.full_size.url,
            asset.youtube_video_asset.youtube_video_id,
            asset_group.id
        FROM asset_group_asset
    """

    try:
        rows = _search_stream(client, customer_id, query)
        results = []
        for row in rows:
            asset = row.asset
            aga = row.asset_group_asset

            field_type = str(aga.field_type).split(".")[-1]
            asset_type = _FIELD_TYPE_MAP.get(field_type, field_type)

            perf_label = str(aga.performance_label).split(".")[-1] if aga.performance_label else None
            if perf_label == "UNSPECIFIED":
                perf_label = None

            # Determine content based on type
            text_content = None
            image_url = None
            if asset.text_asset and asset.text_asset.text:
                text_content = asset.text_asset.text
            if asset.image_asset and asset.image_asset.full_size and asset.image_asset.full_size.url:
                image_url = asset.image_asset.full_size.url
            if asset.youtube_video_asset and asset.youtube_video_asset.youtube_video_id:
                image_url = f"https://www.youtube.com/watch?v={asset.youtube_video_asset.youtube_video_id}"

            results.append({
                "platform_asset_id": str(asset.id),
                "asset_group_id": str(row.asset_group.id),
                "asset_type": asset_type,
                "text_content": text_content,
                "image_url": image_url,
                "performance_label": perf_label,
                "raw_data": {
                    "asset_id": str(asset.id),
                    "field_type": field_type,
                    "asset_name": asset.name,
                },
            })
        logger.info("Fetched %d asset group assets from Google account %s", len(results), customer_id)
        return results
    except GoogleAdsException as ex:
        logger.exception("Google Ads API error fetching assets for %s: %s", customer_id, ex.failure)
        raise
    except Exception:
        logger.exception("Failed to fetch assets from Google account %s", customer_id)
        raise


def _parse_metrics_rows(rows: list[Any], entity_id_field: str) -> list[dict]:
    """Parse metrics rows from GAQL response into normalized dicts."""
    results = []
    for row in rows:
        m = row.metrics
        seg = row.segments

        spend = _micros_to_currency(m.cost_micros) or 0
        impressions = m.impressions or 0
        clicks = m.clicks or 0
        conversions = m.conversions or 0
        revenue = m.conversions_value or 0

        # Get entity ID dynamically
        if entity_id_field == "campaign":
            entity_id = str(row.campaign.id)
        elif entity_id_field == "ad_group":
            entity_id = str(row.ad_group.id)
        elif entity_id_field == "ad_group_ad":
            entity_id = str(row.ad_group_ad.ad.id)
        else:
            entity_id = None

        result = {
            "entity_id": entity_id,
            "campaign_id": str(row.campaign.id),
            "date": seg.date,
            "spend": spend,
            "impressions": impressions,
            "clicks": clicks,
            "ctr": (clicks / impressions * 100) if impressions > 0 else 0,
            "conversions": int(conversions),
            "revenue": float(revenue),
            "roas": float(revenue) / spend if spend > 0 else 0,
            "cpa": spend / conversions if conversions > 0 else None,
            "cpc": spend / clicks if clicks > 0 else None,
            "frequency": None,  # Google doesn't have frequency like Meta
            "add_to_cart": 0,
            "checkouts": 0,
            "searches": 0,
            "leads": 0,
            "landing_page_views": 0,
        }

        # Add adset_id for ad-group and ad level
        if entity_id_field in ("ad_group", "ad_group_ad"):
            result["adset_id"] = str(row.ad_group.id)

        results.append(result)

    return results


def fetch_campaign_metrics(
    customer_id: str,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    """Fetch daily campaign-level metrics."""
    customer_id = customer_id.replace("-", "")
    client = _get_client()

    if date_from is None:
        date_from = date.today() - timedelta(days=7)
    if date_to is None:
        date_to = date.today()

    query = f"""
        SELECT
            campaign.id,
            segments.date,
            metrics.cost_micros,
            metrics.impressions,
            metrics.clicks,
            metrics.conversions,
            metrics.conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '{date_from.isoformat()}' AND '{date_to.isoformat()}'
            AND campaign.status != 'REMOVED'
    """

    try:
        rows = _search_stream(client, customer_id, query)
        results = _parse_metrics_rows(rows, "campaign")
        logger.info(
            "Fetched %d campaign metric rows from Google account %s (%s to %s)",
            len(results), customer_id, date_from, date_to,
        )
        return results
    except GoogleAdsException as ex:
        logger.exception("Google Ads API error fetching campaign metrics: %s", ex.failure)
        raise
    except Exception:
        logger.exception("Failed to fetch campaign metrics from Google account %s", customer_id)
        raise


def fetch_ad_group_metrics(
    customer_id: str,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    """Fetch daily ad-group-level metrics."""
    customer_id = customer_id.replace("-", "")
    client = _get_client()

    if date_from is None:
        date_from = date.today() - timedelta(days=7)
    if date_to is None:
        date_to = date.today()

    query = f"""
        SELECT
            ad_group.id,
            campaign.id,
            segments.date,
            metrics.cost_micros,
            metrics.impressions,
            metrics.clicks,
            metrics.conversions,
            metrics.conversions_value
        FROM ad_group
        WHERE segments.date BETWEEN '{date_from.isoformat()}' AND '{date_to.isoformat()}'
            AND ad_group.status != 'REMOVED'
    """

    try:
        rows = _search_stream(client, customer_id, query)
        results = _parse_metrics_rows(rows, "ad_group")
        logger.info("Fetched %d ad-group metric rows from Google account %s", len(results), customer_id)
        return results
    except GoogleAdsException as ex:
        logger.exception("Google Ads API error fetching ad group metrics: %s", ex.failure)
        raise
    except Exception:
        logger.exception("Failed to fetch ad group metrics from Google account %s", customer_id)
        raise


def fetch_ad_metrics(
    customer_id: str,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    """Fetch daily ad-level metrics."""
    customer_id = customer_id.replace("-", "")
    client = _get_client()

    if date_from is None:
        date_from = date.today() - timedelta(days=7)
    if date_to is None:
        date_to = date.today()

    query = f"""
        SELECT
            ad_group_ad.ad.id,
            ad_group.id,
            campaign.id,
            segments.date,
            metrics.cost_micros,
            metrics.impressions,
            metrics.clicks,
            metrics.conversions,
            metrics.conversions_value
        FROM ad_group_ad
        WHERE segments.date BETWEEN '{date_from.isoformat()}' AND '{date_to.isoformat()}'
            AND ad_group_ad.status != 'REMOVED'
    """

    try:
        rows = _search_stream(client, customer_id, query)
        results = _parse_metrics_rows(rows, "ad_group_ad")
        logger.info("Fetched %d ad metric rows from Google account %s", len(results), customer_id)
        return results
    except GoogleAdsException as ex:
        logger.exception("Google Ads API error fetching ad metrics: %s", ex.failure)
        raise
    except Exception:
        logger.exception("Failed to fetch ad metrics from Google account %s", customer_id)
        raise
