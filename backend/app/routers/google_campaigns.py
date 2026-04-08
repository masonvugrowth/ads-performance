"""Google Ads API endpoints.

Provides Google-specific views for PMax asset groups, Search RSA ads,
and a manual Google-only sync trigger.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import AdAccount
from app.models.ad import Ad
from app.models.ad_set import AdSet
from app.models.campaign import Campaign
from app.models.google_asset import GoogleAsset
from app.models.google_asset_group import GoogleAssetGroup
from app.models.metrics import MetricsCache

router = APIRouter()


def _ok(data):
    return {
        "success": True,
        "data": data,
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _err(msg: str, status: int = 400):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status,
        content={
            "success": False,
            "data": None,
            "error": msg,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


# ── Google Campaigns ────────────────────────────────────────


@router.get("/google/campaigns")
def list_google_campaigns(
    campaign_type: str | None = Query(None, description="Filter: PERFORMANCE_MAX, SEARCH, DISPLAY"),
    status: str | None = Query(None),
    account_id: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    """List all Google Ads campaigns."""
    try:
        q = db.query(Campaign).filter(Campaign.platform == "google")
        if campaign_type:
            q = q.filter(Campaign.objective == campaign_type)
        if status:
            q = q.filter(Campaign.status == status)
        if account_id:
            q = q.filter(Campaign.account_id == account_id)

        total = q.count()
        campaigns = q.order_by(Campaign.name).offset(offset).limit(limit).all()

        return _ok({
            "campaigns": [
                {
                    "id": c.id,
                    "account_id": c.account_id,
                    "name": c.name,
                    "status": c.status,
                    "campaign_type": c.objective,
                    "daily_budget": float(c.daily_budget) if c.daily_budget else None,
                    "ta": c.ta,
                    "funnel_stage": c.funnel_stage,
                    "start_date": c.start_date.isoformat() if c.start_date else None,
                    "end_date": c.end_date.isoformat() if c.end_date else None,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in campaigns
            ],
            "total": total,
        })
    except Exception as e:
        return _err(str(e), 500)


@router.get("/google/campaigns/{campaign_id}")
def get_google_campaign(campaign_id: str, db: Session = Depends(get_db)):
    """Get Google campaign detail."""
    try:
        campaign = (
            db.query(Campaign)
            .filter(Campaign.id == campaign_id, Campaign.platform == "google")
            .first()
        )
        if not campaign:
            return _err("Campaign not found", 404)

        return _ok({
            "id": campaign.id,
            "account_id": campaign.account_id,
            "name": campaign.name,
            "status": campaign.status,
            "campaign_type": campaign.objective,
            "daily_budget": float(campaign.daily_budget) if campaign.daily_budget else None,
            "ta": campaign.ta,
            "funnel_stage": campaign.funnel_stage,
            "start_date": campaign.start_date.isoformat() if campaign.start_date else None,
            "end_date": campaign.end_date.isoformat() if campaign.end_date else None,
            "raw_data": campaign.raw_data,
        })
    except Exception as e:
        return _err(str(e), 500)


@router.get("/google/campaigns/{campaign_id}/ad-groups")
def get_campaign_ad_groups(campaign_id: str, db: Session = Depends(get_db)):
    """Get ad groups for a Google Search campaign."""
    try:
        ad_groups = (
            db.query(AdSet)
            .filter(AdSet.campaign_id == campaign_id, AdSet.platform == "google")
            .order_by(AdSet.name)
            .all()
        )
        return _ok({
            "ad_groups": [
                {
                    "id": ag.id,
                    "name": ag.name,
                    "status": ag.status,
                    "country": ag.country,
                }
                for ag in ad_groups
            ],
            "total": len(ad_groups),
        })
    except Exception as e:
        return _err(str(e), 500)


@router.get("/google/campaigns/{campaign_id}/metrics")
def get_campaign_metrics(
    campaign_id: str,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Get metrics for a Google campaign."""
    try:
        q = db.query(MetricsCache).filter(
            MetricsCache.campaign_id == campaign_id,
            MetricsCache.platform == "google",
            MetricsCache.ad_set_id.is_(None),
            MetricsCache.ad_id.is_(None),
        )
        if date_from:
            q = q.filter(MetricsCache.date >= date_from)
        if date_to:
            q = q.filter(MetricsCache.date <= date_to)

        metrics = q.order_by(MetricsCache.date).all()
        return _ok({
            "metrics": [
                {
                    "date": m.date.isoformat(),
                    "spend": float(m.spend) if m.spend else 0,
                    "impressions": m.impressions,
                    "clicks": m.clicks,
                    "ctr": float(m.ctr) if m.ctr else 0,
                    "conversions": m.conversions,
                    "revenue": float(m.revenue) if m.revenue else 0,
                    "roas": float(m.roas) if m.roas else 0,
                    "cpa": float(m.cpa) if m.cpa else None,
                    "cpc": float(m.cpc) if m.cpc else None,
                }
                for m in metrics
            ],
        })
    except Exception as e:
        return _err(str(e), 500)


# ── PMax Asset Groups ───────────────────────────────────────


@router.get("/google/asset-groups")
def list_asset_groups(
    campaign_id: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    """List all PMax asset groups."""
    try:
        q = db.query(GoogleAssetGroup)
        if campaign_id:
            q = q.filter(GoogleAssetGroup.campaign_id == campaign_id)
        if status:
            q = q.filter(GoogleAssetGroup.status == status)

        total = q.count()
        groups = q.order_by(GoogleAssetGroup.name).offset(offset).limit(limit).all()

        # Count assets per group
        result = []
        for g in groups:
            asset_count = (
                db.query(GoogleAsset)
                .filter(GoogleAsset.asset_group_id == g.id)
                .count()
            )
            campaign = db.query(Campaign).filter(Campaign.id == g.campaign_id).first()
            result.append({
                "id": g.id,
                "campaign_id": g.campaign_id,
                "campaign_name": campaign.name if campaign else None,
                "name": g.name,
                "status": g.status,
                "final_urls": g.final_urls,
                "asset_count": asset_count,
            })

        return _ok({"asset_groups": result, "total": total})
    except Exception as e:
        return _err(str(e), 500)


@router.get("/google/asset-groups/{group_id}")
def get_asset_group(group_id: str, db: Session = Depends(get_db)):
    """Get asset group detail with all assets."""
    try:
        group = db.query(GoogleAssetGroup).filter(GoogleAssetGroup.id == group_id).first()
        if not group:
            return _err("Asset group not found", 404)

        assets = (
            db.query(GoogleAsset)
            .filter(GoogleAsset.asset_group_id == group_id)
            .order_by(GoogleAsset.asset_type)
            .all()
        )
        campaign = db.query(Campaign).filter(Campaign.id == group.campaign_id).first()

        return _ok({
            "id": group.id,
            "campaign_id": group.campaign_id,
            "campaign_name": campaign.name if campaign else None,
            "name": group.name,
            "status": group.status,
            "final_urls": group.final_urls,
            "assets": [
                {
                    "id": a.id,
                    "asset_type": a.asset_type,
                    "text_content": a.text_content,
                    "image_url": a.image_url,
                    "performance_label": a.performance_label,
                }
                for a in assets
            ],
        })
    except Exception as e:
        return _err(str(e), 500)


@router.get("/google/asset-groups/{group_id}/assets")
def list_assets(group_id: str, db: Session = Depends(get_db)):
    """List assets for an asset group."""
    try:
        assets = (
            db.query(GoogleAsset)
            .filter(GoogleAsset.asset_group_id == group_id)
            .order_by(GoogleAsset.asset_type)
            .all()
        )
        return _ok({
            "assets": [
                {
                    "id": a.id,
                    "asset_type": a.asset_type,
                    "text_content": a.text_content,
                    "image_url": a.image_url,
                    "performance_label": a.performance_label,
                    "raw_data": a.raw_data,
                }
                for a in assets
            ],
            "total": len(assets),
        })
    except Exception as e:
        return _err(str(e), 500)


# ── Google Ads (RSA) ────────────────────────────────────────


@router.get("/google/ads/{ad_id}")
def get_google_ad(ad_id: str, db: Session = Depends(get_db)):
    """Get a single Google ad detail (RSA with headlines/descriptions)."""
    try:
        ad = (
            db.query(Ad)
            .filter(Ad.id == ad_id, Ad.platform == "google")
            .first()
        )
        if not ad:
            return _err("Ad not found", 404)

        raw = ad.raw_data or {}
        return _ok({
            "id": ad.id,
            "name": ad.name,
            "status": ad.status,
            "ad_type": raw.get("ad_type", "UNKNOWN"),
            "headlines": raw.get("headlines", []),
            "descriptions": raw.get("descriptions", []),
            "campaign_id": ad.campaign_id,
            "ad_set_id": ad.ad_set_id,
            "raw_data": ad.raw_data,
        })
    except Exception as e:
        return _err(str(e), 500)


# ── Google Sync Trigger ─────────────────────────────────────


@router.post("/google/sync")
def trigger_google_sync(
    account_id: str | None = Query(None, description="Sync specific account only"),
    db: Session = Depends(get_db),
):
    """Trigger a manual Google Ads sync."""
    try:
        from app.services.google_sync_engine import sync_google_account

        q = db.query(AdAccount).filter(
            AdAccount.platform == "google",
            AdAccount.is_active.is_(True),
        )
        if account_id:
            q = q.filter(AdAccount.id == account_id)

        accounts = q.all()
        if not accounts:
            return _err("No active Google Ads accounts found", 404)

        results = []
        for account in accounts:
            result = sync_google_account(db, account)
            results.append({
                "account_id": str(account.id),
                "account_name": account.account_name,
                **result,
            })

        return _ok({"sync_results": results})
    except Exception as e:
        return _err(str(e), 500)


# ── Google Dashboard Summary ────────────────────────────────


@router.get("/google/dashboard")
def google_dashboard(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Get Google Ads dashboard KPIs."""
    try:
        from sqlalchemy import func

        q = db.query(
            func.sum(MetricsCache.spend).label("total_spend"),
            func.sum(MetricsCache.impressions).label("total_impressions"),
            func.sum(MetricsCache.clicks).label("total_clicks"),
            func.sum(MetricsCache.conversions).label("total_conversions"),
            func.sum(MetricsCache.revenue).label("total_revenue"),
        ).filter(
            MetricsCache.platform == "google",
            MetricsCache.ad_set_id.is_(None),
            MetricsCache.ad_id.is_(None),
        )
        if date_from:
            q = q.filter(MetricsCache.date >= date_from)
        if date_to:
            q = q.filter(MetricsCache.date <= date_to)

        row = q.first()

        total_spend = float(row.total_spend or 0)
        total_impressions = int(row.total_impressions or 0)
        total_clicks = int(row.total_clicks or 0)
        total_conversions = int(row.total_conversions or 0)
        total_revenue = float(row.total_revenue or 0)

        # Campaign counts by type
        pmax_count = (
            db.query(Campaign)
            .filter(Campaign.platform == "google", Campaign.objective == "PERFORMANCE_MAX")
            .count()
        )
        search_count = (
            db.query(Campaign)
            .filter(Campaign.platform == "google", Campaign.objective == "SEARCH")
            .count()
        )
        total_campaigns = (
            db.query(Campaign).filter(Campaign.platform == "google").count()
        )

        return _ok({
            "kpis": {
                "total_spend": total_spend,
                "total_impressions": total_impressions,
                "total_clicks": total_clicks,
                "total_conversions": total_conversions,
                "total_revenue": total_revenue,
                "roas": total_revenue / total_spend if total_spend > 0 else 0,
                "ctr": (total_clicks / total_impressions * 100) if total_impressions > 0 else 0,
                "cpa": total_spend / total_conversions if total_conversions > 0 else None,
            },
            "campaign_counts": {
                "total": total_campaigns,
                "performance_max": pmax_count,
                "search": search_count,
                "other": total_campaigns - pmax_count - search_count,
            },
        })
    except Exception as e:
        return _err(str(e), 500)
