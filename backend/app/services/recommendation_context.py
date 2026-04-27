"""Batch-load entity context for recommendation API responses.

The list endpoints would otherwise emit one SELECT per recommendation per
related entity (account / campaign / ad_set / ad / asset_group). This helper
collects all referenced ids up-front, runs four bulk queries, and returns a
per-recommendation context dict the routers can splice into the response.

The context is presentation-only — used by the frontend to render the
"Settings" panel on each recommendation card (campaign name, daily budget,
country targeting, currency). It never affects detector or applier logic.
"""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.account import AdAccount
from app.models.ad import Ad
from app.models.ad_set import AdSet
from app.models.campaign import Campaign
from app.models.google_asset_group import GoogleAssetGroup


def _ids(items: Iterable[Any], attr: str) -> list[str]:
    seen: set[str] = set()
    for it in items:
        v = getattr(it, attr, None)
        if v and v not in seen:
            seen.add(v)
    return list(seen)


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _targeting_summary(targeting: Any) -> dict[str, Any] | None:
    """Pluck a few human-readable bits out of Meta's targeting JSON.

    Meta's full targeting payload is huge; the UI only needs a one-line
    "Solo travellers, 25-45" style summary, so we surface the small handful
    of fields that actually fit on a card.
    """
    if not isinstance(targeting, dict):
        return None
    out: dict[str, Any] = {}
    age_min = targeting.get("age_min")
    age_max = targeting.get("age_max")
    if age_min or age_max:
        out["age_range"] = f"{age_min or 13}-{age_max or 65}+"
    genders = targeting.get("genders")
    if isinstance(genders, list) and genders:
        # Meta gender codes: 1 = male, 2 = female. [] / [1,2] both mean all.
        if set(genders) == {1, 2} or len(genders) == 0:
            out["gender"] = "All"
        elif genders == [1]:
            out["gender"] = "Male"
        elif genders == [2]:
            out["gender"] = "Female"
    geo = targeting.get("geo_locations") or {}
    if isinstance(geo, dict):
        countries = geo.get("countries")
        if isinstance(countries, list) and countries:
            out["countries"] = countries[:6]
        regions = geo.get("regions")
        if isinstance(regions, list) and regions:
            out["regions"] = [r.get("name") for r in regions if isinstance(r, dict)][:4]
        cities = geo.get("cities")
        if isinstance(cities, list) and cities:
            out["cities"] = [c.get("name") for c in cities if isinstance(c, dict)][:4]
    return out or None


def build_context_map(
    db: Session,
    recs: list,
    *,
    include_asset_groups: bool = False,
) -> dict[str, dict[str, Any]]:
    """Return {rec.id: context_dict} for the given recommendation rows.

    Works for both Meta and Google recommendations because both expose
    `account_id` / `campaign_id` / `ad_id` and one of `ad_set_id` (Meta) or
    `ad_group_id` (Google). Pass include_asset_groups=True for Google.
    """
    if not recs:
        return {}

    account_ids = _ids(recs, "account_id")
    campaign_ids = _ids(recs, "campaign_id")
    ad_ids = _ids(recs, "ad_id")
    # Meta uses ad_set_id, Google reuses the ad_sets table via ad_group_id.
    set_ids = _ids(recs, "ad_set_id") + _ids(recs, "ad_group_id")
    asset_group_ids = _ids(recs, "asset_group_id") if include_asset_groups else []

    accounts = (
        {a.id: a for a in db.query(AdAccount).filter(AdAccount.id.in_(account_ids)).all()}
        if account_ids else {}
    )
    campaigns = (
        {c.id: c for c in db.query(Campaign).filter(Campaign.id.in_(campaign_ids)).all()}
        if campaign_ids else {}
    )
    ad_sets = (
        {s.id: s for s in db.query(AdSet).filter(AdSet.id.in_(set_ids)).all()}
        if set_ids else {}
    )
    ads = (
        {a.id: a for a in db.query(Ad).filter(Ad.id.in_(ad_ids)).all()}
        if ad_ids else {}
    )
    asset_groups = (
        {g.id: g for g in db.query(GoogleAssetGroup).filter(GoogleAssetGroup.id.in_(asset_group_ids)).all()}
        if asset_group_ids else {}
    )

    out: dict[str, dict[str, Any]] = {}
    for r in recs:
        ctx: dict[str, Any] = {}
        acct = accounts.get(getattr(r, "account_id", None))
        if acct is not None:
            ctx["account_name"] = acct.account_name
            ctx["currency"] = acct.currency

        camp = campaigns.get(getattr(r, "campaign_id", None))
        if camp is not None:
            ctx["campaign_name"] = camp.name
            ctx["campaign_status"] = camp.status
            ctx["campaign_objective"] = camp.objective
            ctx["campaign_daily_budget"] = _to_float(camp.daily_budget)
            ctx["campaign_lifetime_budget"] = _to_float(camp.lifetime_budget)

        # Meta ad_set or Google ad_group both live on ad_sets table.
        set_id = getattr(r, "ad_set_id", None) or getattr(r, "ad_group_id", None)
        s = ad_sets.get(set_id)
        if s is not None:
            label = "ad_set" if getattr(r, "ad_set_id", None) else "ad_group"
            ctx[f"{label}_name"] = s.name
            ctx[f"{label}_status"] = s.status
            ctx[f"{label}_daily_budget"] = _to_float(s.daily_budget)
            if s.country and s.country.upper() != "UNKNOWN":
                ctx[f"{label}_country"] = s.country
            t = _targeting_summary(s.targeting)
            if t:
                ctx["targeting"] = t

        ad = ads.get(getattr(r, "ad_id", None))
        if ad is not None:
            ctx["ad_name"] = ad.name
            ctx["ad_status"] = ad.status

        if include_asset_groups:
            ag = asset_groups.get(getattr(r, "asset_group_id", None))
            if ag is not None:
                ctx["asset_group_name"] = ag.name
                ctx["asset_group_status"] = ag.status

        out[r.id] = ctx
    return out
