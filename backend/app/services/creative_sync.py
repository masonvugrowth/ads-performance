"""Sync creative library (materials, copies, combos) from Meta ads.

Idempotent: only inserts rows that don't already exist, keyed by:
  - AdMaterial: (branch_id, description=ad_name)
  - AdCopy:     (branch_id, headline)
  - AdCombo:    (branch_id, ad_name)

Called from sync_engine.sync_meta_account after the Ad table has been upserted.
"""
import logging

from facebook_business.adobjects.adaccount import AdAccount as FBAdAccount
from facebook_business.api import FacebookAdsApi
from sqlalchemy.orm import Session

from app.models.account import AdAccount
from app.models.ad_combo import AdCombo
from app.models.ad_copy import AdCopy
from app.models.ad_material import AdMaterial
from app.services.creative_service import (
    next_combo_id, next_copy_id, next_material_id,
)
from app.services.parse_utils import parse_campaign_metadata

logger = logging.getLogger(__name__)


def _detect_ta(name: str) -> str:
    """Extract TA using the canonical whitelist (parse_utils.TA_WHITELIST).

    Returns 'Unknown' when no whitelist token is present, matching the
    platform-wide parsing contract (see .claude/rules/parsing-rules.md).
    """
    return parse_campaign_metadata(name)["ta"]


def _detect_material_type(ad_name: str) -> str:
    n = (ad_name or "").lower()
    if "[video]" in n:
        return "video"
    if "[carousel]" in n:
        return "carousel"
    return "image"


def _detect_language(text: str) -> str:
    sample = (text or "")[:50]
    if any(0x3040 <= ord(c) <= 0x30FF for c in sample):
        return "ja"
    if any(ord(c) > 0x4E00 for c in sample):
        return "zh"
    return "en"


def sync_creative_library_for_account(db: Session, account: AdAccount) -> dict:
    """Upsert AdMaterial / AdCopy / AdCombo rows from Meta ad creatives for one account."""
    summary = {"materials_created": 0, "copies_created": 0, "combos_created": 0, "errors": []}

    if not account.access_token_enc:
        return summary

    acc_id = account.account_id if account.account_id.startswith("act_") else f"act_{account.account_id}"

    try:
        FacebookAdsApi.init(app_id="", app_secret="", access_token=account.access_token_enc)
        fb = FBAdAccount(acc_id)
        ads = fb.get_ads(
            fields=["name", "status", "creative{title,body,call_to_action_type,thumbnail_url}", "campaign{name}"],
            params={
                "limit": 200,
                "filtering": [{"field": "ad.effective_status", "operator": "IN",
                               "value": ["ACTIVE", "PAUSED"]}],
            },
        )
    except Exception as e:
        logger.exception("Creative sync: failed to fetch ads for %s", account.account_id)
        summary["errors"].append(f"Failed to fetch Meta ads: {e}")
        return summary

    # Preload existing per-branch for O(1) lookups
    existing_materials = {
        m.description: m
        for m in db.query(AdMaterial).filter(AdMaterial.branch_id == account.id).all()
        if m.description
    }
    existing_copies = {
        c.headline: c
        for c in db.query(AdCopy).filter(AdCopy.branch_id == account.id).all()
    }
    existing_combos = {
        c.ad_name: c
        for c in db.query(AdCombo).filter(AdCombo.branch_id == account.id).all()
        if c.ad_name
    }

    seen_ad_names: set[str] = set()

    for ad in ads:
        ad_name = (ad.get("name") or "").strip()
        if not ad_name or ad_name in seen_ad_names:
            continue
        seen_ad_names.add(ad_name)

        creative = ad.get("creative") or {}
        campaign = ad.get("campaign") or {}
        campaign_name = campaign.get("name", "")

        title = (creative.get("title") or "").strip()
        body = (creative.get("body") or "").strip()
        cta = creative.get("call_to_action_type") or None
        thumb = creative.get("thumbnail_url") or None

        ta = _detect_ta(f"{campaign_name} {ad_name}")
        mat_type = _detect_material_type(ad_name)

        # ── Material (keyed by description=ad_name) ──
        material = existing_materials.get(ad_name)
        if not material:
            if not thumb:
                # Material requires file_url (NOT NULL). Skip this ad — no combo either.
                continue
            try:
                mid = next_material_id(db)
                material = AdMaterial(
                    material_id=mid,
                    branch_id=account.id,
                    material_type=mat_type,
                    file_url=thumb,
                    description=ad_name,
                    target_audience=ta,
                    url_source="auto",
                )
                db.add(material)
                db.flush()
                existing_materials[ad_name] = material
                summary["materials_created"] += 1
            except Exception as e:
                db.rollback()
                logger.exception("Creative sync: failed to create material for %s", ad_name)
                summary["errors"].append(f"material {ad_name[:40]}: {e}")
                continue

        # ── Copy (keyed by headline) ──
        headline = (title or ad_name)[:500]
        copy = existing_copies.get(headline)
        if not copy:
            try:
                copy_body = body or f"[No body text — ad: {ad_name}]"
                cid = next_copy_id(db)
                copy = AdCopy(
                    copy_id=cid,
                    branch_id=account.id,
                    target_audience=ta,
                    headline=headline,
                    body_text=copy_body,
                    cta=cta[:200] if cta else None,
                    language=_detect_language(title + body),
                )
                db.add(copy)
                db.flush()
                existing_copies[headline] = copy
                summary["copies_created"] += 1
            except Exception as e:
                db.rollback()
                logger.exception("Creative sync: failed to create copy for %s", ad_name)
                summary["errors"].append(f"copy {ad_name[:40]}: {e}")
                continue

        # ── Combo (keyed by ad_name) ──
        if ad_name not in existing_combos:
            try:
                cb_id = next_combo_id(db)
                combo = AdCombo(
                    combo_id=cb_id,
                    branch_id=account.id,
                    ad_name=ad_name,
                    copy_id=copy.copy_id,
                    material_id=material.material_id,
                    target_audience=ta,
                    verdict="TEST",
                    verdict_source="auto",
                )
                db.add(combo)
                db.flush()
                existing_combos[ad_name] = combo
                summary["combos_created"] += 1
            except Exception as e:
                db.rollback()
                logger.exception("Creative sync: failed to create combo for %s", ad_name)
                summary["errors"].append(f"combo {ad_name[:40]}: {e}")
                continue

    db.commit()
    return summary
