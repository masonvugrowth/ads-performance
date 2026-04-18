"""Service: refresh ad_materials.file_url from Meta AdCreative preview URLs.

Deduped by ad_name — only fetches the creative once per unique ad_name per branch.
"""
import logging
from typing import Optional

from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount as FBAdAccount
from facebook_business.adobjects.adcreative import AdCreative
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.account import AdAccount
from app.models.ad_combo import AdCombo

logger = logging.getLogger(__name__)

CREATIVE_FIELDS = [
    "id",
    "image_url",
    "thumbnail_url",
    "video_id",
    "object_story_spec",
    "asset_feed_spec",
    "effective_object_story_id",
]


def _extract_preview_url(creative: dict) -> Optional[str]:
    """Pick the best available preview URL from a Meta creative object."""
    if creative.get("image_url"):
        return creative["image_url"]
    if creative.get("thumbnail_url"):
        return creative["thumbnail_url"]

    oss = creative.get("object_story_spec") or {}
    link_data = oss.get("link_data") or {}
    if link_data.get("picture"):
        return link_data["picture"]
    video_data = oss.get("video_data") or {}
    if video_data.get("image_url"):
        return video_data["image_url"]

    afs = creative.get("asset_feed_spec") or {}
    images = afs.get("images") or []
    if images and images[0].get("url"):
        return images[0]["url"]
    videos = afs.get("videos") or []
    if videos and videos[0].get("thumbnail_url"):
        return videos[0]["thumbnail_url"]

    child_attachments = link_data.get("child_attachments") or []
    if child_attachments and child_attachments[0].get("picture"):
        return child_attachments[0]["picture"]

    return None


def sync_material_urls(db: Session) -> dict:
    """Refresh ad_materials.file_url from Meta AdCreative URLs.

    Runs on all active Meta ad_accounts. Deduplicates by (branch_id, ad_name).

    Returns summary dict: {accounts_processed, unique_ad_names_updated}
    """
    accounts = (
        db.query(AdAccount)
        .filter(AdAccount.is_active.is_(True), AdAccount.platform == "meta")
        .all()
    )

    combos = db.query(AdCombo).filter(AdCombo.ad_name.isnot(None)).all()
    ad_name_to_materials: dict[tuple[str, str], set[str]] = {}
    for c in combos:
        key = (c.branch_id, c.ad_name)
        ad_name_to_materials.setdefault(key, set()).add(c.material_id)

    total_updated = 0
    for acc in accounts:
        if not acc.access_token_enc:
            continue

        acc_id = acc.account_id if acc.account_id.startswith("act_") else f"act_{acc.account_id}"

        try:
            FacebookAdsApi.init(app_id="", app_secret="", access_token=acc.access_token_enc)
            fb = FBAdAccount(acc_id)

            ads = fb.get_ads(
                fields=["name", "creative"],
                params={"limit": 500, "filtering": [
                    {"field": "ad.effective_status", "operator": "IN",
                     "value": ["ACTIVE", "PAUSED", "ARCHIVED"]},
                ]},
            )

            seen_names: set[str] = set()
            for ad in ads:
                ad_name = ad.get("name", "")
                if not ad_name or ad_name in seen_names:
                    continue
                seen_names.add(ad_name)

                material_ids = ad_name_to_materials.get((acc.id, ad_name))
                if not material_ids:
                    continue

                creative_ref = ad.get("creative")
                if not creative_ref:
                    continue
                creative_id = (
                    creative_ref.get("id")
                    if isinstance(creative_ref, dict)
                    else getattr(creative_ref, "get_id_assured", lambda: None)()
                )
                if not creative_id:
                    continue

                try:
                    creative = AdCreative(creative_id).api_get(fields=CREATIVE_FIELDS)
                    url = _extract_preview_url(dict(creative))
                except Exception:
                    logger.exception("Failed to fetch creative %s", creative_id)
                    continue

                if not url:
                    continue

                # Skip manually-set URLs (designer input) — only overwrite 'auto' rows
                result = db.execute(
                    text(
                        "UPDATE ad_materials SET file_url = :u "
                        "WHERE material_id = ANY(:ids) AND url_source = 'auto'"
                    ),
                    {"u": url, "ids": list(material_ids)},
                )
                if result.rowcount > 0:
                    total_updated += 1

            db.commit()

        except Exception:
            logger.exception("Material URL sync failed for account %s", acc.account_name)
            db.rollback()

    return {"accounts_processed": len(accounts), "unique_ad_names_updated": total_updated}
