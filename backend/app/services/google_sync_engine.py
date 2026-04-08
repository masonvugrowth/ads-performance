"""Google Ads sync engine: orchestrates fetching and upserting Google Ads data.

Follows the same pattern as sync_meta_account in sync_engine.py.
Platform separation: this file has NO imports from meta_client.py.
"""

import logging
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.account import AdAccount
from app.models.ad import Ad
from app.models.ad_set import AdSet
from app.models.campaign import Campaign
from app.models.google_asset_group import GoogleAssetGroup
from app.models.google_asset import GoogleAsset
from app.models.metrics import MetricsCache
from app.services.google_client import (
    fetch_ad_group_metrics,
    fetch_ad_groups,
    fetch_ad_metrics,
    fetch_ads,
    fetch_asset_group_assets,
    fetch_asset_groups,
    fetch_campaign_metrics,
    fetch_campaigns,
)
from app.services.parse_utils import parse_adset_metadata, parse_campaign_metadata

logger = logging.getLogger(__name__)


def _upsert_google_metrics(
    db: Session,
    campaign_id: str,
    insight: dict,
    insight_date: date,
    ad_set_id: str | None = None,
    ad_id: str | None = None,
) -> None:
    """Upsert a single metrics row for Google Ads."""
    q = db.query(MetricsCache).filter(
        MetricsCache.campaign_id == campaign_id,
        MetricsCache.date == insight_date,
    )
    if ad_id:
        q = q.filter(MetricsCache.ad_id == ad_id)
    elif ad_set_id:
        q = q.filter(MetricsCache.ad_set_id == ad_set_id, MetricsCache.ad_id.is_(None))
    else:
        q = q.filter(MetricsCache.ad_set_id.is_(None), MetricsCache.ad_id.is_(None))

    existing = q.first()
    now = datetime.now(timezone.utc)

    metric_fields = {
        "spend": insight["spend"],
        "impressions": insight["impressions"],
        "clicks": insight["clicks"],
        "ctr": insight["ctr"],
        "conversions": insight["conversions"],
        "revenue": insight["revenue"],
        "roas": insight["roas"],
        "cpa": insight["cpa"],
        "cpc": insight["cpc"],
        "frequency": insight.get("frequency"),
        "add_to_cart": insight.get("add_to_cart", 0),
        "checkouts": insight.get("checkouts", 0),
        "searches": insight.get("searches", 0),
        "leads": insight.get("leads", 0),
        "landing_page_views": insight.get("landing_page_views", 0),
        "computed_at": now,
    }

    if existing:
        for k, v in metric_fields.items():
            setattr(existing, k, v)
        existing.updated_at = now
    else:
        metric = MetricsCache(
            campaign_id=campaign_id,
            ad_set_id=ad_set_id,
            ad_id=ad_id,
            platform="google",
            date=insight_date,
            **metric_fields,
        )
        db.add(metric)


def sync_google_account(db: Session, account: AdAccount) -> dict:
    """Sync campaigns, ad groups, ads, asset groups, assets, and metrics
    for a single Google Ads account.

    Returns summary dict matching sync_meta_account format.
    """
    customer_id = account.account_id.replace("-", "")
    summary = {
        "campaigns_synced": 0,
        "adsets_synced": 0,
        "ads_synced": 0,
        "asset_groups_synced": 0,
        "assets_synced": 0,
        "metrics_synced": 0,
        "errors": [],
    }

    if not account.access_token_enc:
        summary["errors"].append("No refresh token configured for this account")
        return summary

    # --- 1. Fetch and upsert campaigns ---
    try:
        raw_campaigns = fetch_campaigns(customer_id)
    except Exception as e:
        summary["errors"].append(f"Failed to fetch campaigns: {e}")
        return summary

    for raw in raw_campaigns:
        parsed = parse_campaign_metadata(raw["name"])

        existing = (
            db.query(Campaign)
            .filter(Campaign.platform_campaign_id == raw["platform_campaign_id"])
            .first()
        )
        if existing:
            existing.name = raw["name"]
            existing.status = raw["status"]
            existing.objective = raw["objective"]
            existing.daily_budget = raw["daily_budget"]
            existing.lifetime_budget = raw["lifetime_budget"]
            existing.ta = parsed["ta"]
            existing.funnel_stage = parsed["funnel_stage"]
            existing.raw_data = raw["raw_data"]
            existing.updated_at = datetime.now(timezone.utc)
        else:
            campaign = Campaign(
                account_id=account.id,
                platform="google",
                platform_campaign_id=raw["platform_campaign_id"],
                name=raw["name"],
                status=raw["status"],
                objective=raw["objective"],
                daily_budget=raw["daily_budget"],
                lifetime_budget=raw["lifetime_budget"],
                ta=parsed["ta"],
                funnel_stage=parsed["funnel_stage"],
                start_date=raw.get("start_date"),
                end_date=raw.get("end_date"),
                raw_data=raw["raw_data"],
            )
            db.add(campaign)
        summary["campaigns_synced"] += 1

    db.flush()

    # --- 2. Fetch and upsert ad groups (Search campaigns) ---
    try:
        raw_ad_groups = fetch_ad_groups(customer_id)
    except Exception as e:
        summary["errors"].append(f"Failed to fetch ad groups: {e}")
        raw_ad_groups = []

    for raw in raw_ad_groups:
        campaign = (
            db.query(Campaign)
            .filter(Campaign.platform_campaign_id == raw["campaign_id"])
            .first()
        )
        if not campaign:
            logger.warning(
                "Campaign %s not found for ad group %s, skipping",
                raw["campaign_id"], raw["platform_adset_id"],
            )
            continue

        parsed = parse_adset_metadata(raw["name"])

        existing = (
            db.query(AdSet)
            .filter(AdSet.platform_adset_id == raw["platform_adset_id"])
            .first()
        )
        if existing:
            existing.name = raw["name"]
            existing.status = raw["status"]
            existing.country = parsed["country"]
            existing.raw_data = raw["raw_data"]
            existing.updated_at = datetime.now(timezone.utc)
        else:
            adset = AdSet(
                campaign_id=campaign.id,
                account_id=account.id,
                platform="google",
                platform_adset_id=raw["platform_adset_id"],
                name=raw["name"],
                status=raw["status"],
                country=parsed["country"],
                raw_data=raw["raw_data"],
            )
            db.add(adset)
        summary["adsets_synced"] += 1

    db.flush()

    # --- 3. Fetch and upsert RSA ads ---
    try:
        raw_ads = fetch_ads(customer_id)
    except Exception as e:
        summary["errors"].append(f"Failed to fetch ads: {e}")
        raw_ads = []

    for raw in raw_ads:
        adset = (
            db.query(AdSet)
            .filter(AdSet.platform_adset_id == raw["platform_adset_id"])
            .first()
        )
        campaign = (
            db.query(Campaign)
            .filter(Campaign.platform_campaign_id == raw["platform_campaign_id"])
            .first()
        )
        if not adset or not campaign:
            logger.warning(
                "Ad set or campaign not found for ad %s, skipping",
                raw["platform_ad_id"],
            )
            continue

        existing = (
            db.query(Ad)
            .filter(Ad.platform_ad_id == raw["platform_ad_id"])
            .first()
        )
        if existing:
            existing.name = raw["name"]
            existing.status = raw["status"]
            existing.raw_data = raw["raw_data"]
            existing.updated_at = datetime.now(timezone.utc)
        else:
            ad = Ad(
                ad_set_id=adset.id,
                campaign_id=campaign.id,
                account_id=account.id,
                platform="google",
                platform_ad_id=raw["platform_ad_id"],
                name=raw["name"],
                status=raw["status"],
                creative_id=None,
                raw_data=raw["raw_data"],
            )
            db.add(ad)
        summary["ads_synced"] += 1

    db.flush()

    # --- 4. Fetch and upsert PMax asset groups ---
    try:
        raw_asset_groups = fetch_asset_groups(customer_id)
    except Exception as e:
        summary["errors"].append(f"Failed to fetch asset groups: {e}")
        raw_asset_groups = []

    for raw in raw_asset_groups:
        campaign = (
            db.query(Campaign)
            .filter(Campaign.platform_campaign_id == raw["campaign_id"])
            .first()
        )
        if not campaign:
            logger.warning(
                "Campaign %s not found for asset group %s, skipping",
                raw["campaign_id"], raw["platform_asset_group_id"],
            )
            continue

        existing = (
            db.query(GoogleAssetGroup)
            .filter(GoogleAssetGroup.platform_asset_group_id == raw["platform_asset_group_id"])
            .first()
        )
        if existing:
            existing.name = raw["name"]
            existing.status = raw["status"]
            existing.final_urls = raw["final_urls"]
            existing.raw_data = raw["raw_data"]
            existing.updated_at = datetime.now(timezone.utc)
        else:
            asset_group = GoogleAssetGroup(
                campaign_id=campaign.id,
                account_id=account.id,
                platform_asset_group_id=raw["platform_asset_group_id"],
                name=raw["name"],
                status=raw["status"],
                final_urls=raw["final_urls"],
                raw_data=raw["raw_data"],
            )
            db.add(asset_group)
        summary["asset_groups_synced"] += 1

    db.flush()

    # --- 5. Fetch and upsert assets ---
    try:
        raw_assets = fetch_asset_group_assets(customer_id)
    except Exception as e:
        summary["errors"].append(f"Failed to fetch assets: {e}")
        raw_assets = []

    for raw in raw_assets:
        asset_group = (
            db.query(GoogleAssetGroup)
            .filter(GoogleAssetGroup.platform_asset_group_id == raw["asset_group_id"])
            .first()
        )
        if not asset_group:
            logger.warning(
                "Asset group %s not found for asset %s, skipping",
                raw["asset_group_id"], raw["platform_asset_id"],
            )
            continue

        existing = (
            db.query(GoogleAsset)
            .filter(
                GoogleAsset.asset_group_id == asset_group.id,
                GoogleAsset.platform_asset_id == raw["platform_asset_id"],
            )
            .first()
        )
        if existing:
            existing.asset_type = raw["asset_type"]
            existing.text_content = raw["text_content"]
            existing.image_url = raw["image_url"]
            existing.performance_label = raw["performance_label"]
            existing.raw_data = raw["raw_data"]
            existing.updated_at = datetime.now(timezone.utc)
        else:
            asset = GoogleAsset(
                asset_group_id=asset_group.id,
                account_id=asset_group.account_id,
                platform_asset_id=raw["platform_asset_id"],
                asset_type=raw["asset_type"],
                text_content=raw["text_content"],
                image_url=raw["image_url"],
                performance_label=raw["performance_label"],
                raw_data=raw["raw_data"],
            )
            db.add(asset)
        summary["assets_synced"] += 1

    db.flush()

    # --- 6. Fetch and upsert campaign-level metrics ---
    try:
        raw_metrics = fetch_campaign_metrics(customer_id)
    except Exception as e:
        summary["errors"].append(f"Failed to fetch campaign metrics: {e}")
        raw_metrics = []

    for insight in raw_metrics:
        campaign = (
            db.query(Campaign)
            .filter(Campaign.platform_campaign_id == insight["campaign_id"])
            .first()
        )
        if not campaign:
            continue

        insight_date = (
            date.fromisoformat(insight["date"])
            if isinstance(insight["date"], str)
            else insight["date"]
        )
        _upsert_google_metrics(db, campaign.id, insight, insight_date)
        summary["metrics_synced"] += 1

    # --- 7. Fetch and upsert ad-group-level metrics ---
    try:
        ag_metrics = fetch_ad_group_metrics(customer_id)
    except Exception as e:
        summary["errors"].append(f"Failed to fetch ad group metrics: {e}")
        ag_metrics = []

    for insight in ag_metrics:
        adset = (
            db.query(AdSet)
            .filter(AdSet.platform_adset_id == insight["entity_id"])
            .first()
        )
        if not adset:
            continue

        insight_date = (
            date.fromisoformat(insight["date"])
            if isinstance(insight["date"], str)
            else insight["date"]
        )
        _upsert_google_metrics(
            db, adset.campaign_id, insight, insight_date, ad_set_id=adset.id,
        )
        summary["metrics_synced"] += 1

    # --- 8. Fetch and upsert ad-level metrics ---
    try:
        ad_metrics_data = fetch_ad_metrics(customer_id)
    except Exception as e:
        summary["errors"].append(f"Failed to fetch ad metrics: {e}")
        ad_metrics_data = []

    for insight in ad_metrics_data:
        ad_obj = (
            db.query(Ad)
            .filter(Ad.platform_ad_id == insight["entity_id"])
            .first()
        )
        if not ad_obj:
            continue

        insight_date = (
            date.fromisoformat(insight["date"])
            if isinstance(insight["date"], str)
            else insight["date"]
        )
        _upsert_google_metrics(
            db, ad_obj.campaign_id, insight, insight_date,
            ad_set_id=ad_obj.ad_set_id, ad_id=ad_obj.id,
        )
        summary["metrics_synced"] += 1

    db.commit()
    logger.info(
        "Google sync complete for account %s: %d campaigns, %d ad groups, "
        "%d ads, %d asset groups, %d assets, %d metrics rows",
        account.account_id,
        summary["campaigns_synced"],
        summary["adsets_synced"],
        summary["ads_synced"],
        summary["asset_groups_synced"],
        summary["assets_synced"],
        summary["metrics_synced"],
    )
    return summary
