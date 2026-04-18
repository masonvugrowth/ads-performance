"""Pull real preview URLs for ad_materials from Meta API, deduped by ad_name.

A combo is defined by ad_name (multiple Meta ads may share the same name). We
only need to fetch the creative ONCE per unique ad_name, then update the
matching material.
"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount as FBAdAccount
from facebook_business.adobjects.adcreative import AdCreative
from sqlalchemy import text

from app.database import SessionLocal
from app.models.account import AdAccount
from app.models.ad_combo import AdCombo
from app.models.ad_material import AdMaterial

# Creative fields to request (cover image ads, video ads, link ads, carousels,
# and asset_feed_spec for dynamic creative)
CREATIVE_FIELDS = [
    'id',
    'image_url',
    'thumbnail_url',
    'video_id',
    'object_story_spec',
    'asset_feed_spec',
    'effective_object_story_id',
]


def extract_preview_url(creative: dict) -> str | None:
    """Pick the best available preview URL from a creative."""
    # 1. Direct image_url (single-image ads)
    if creative.get('image_url'):
        return creative['image_url']

    # 2. Video thumbnail
    if creative.get('thumbnail_url'):
        return creative['thumbnail_url']

    # 3. object_story_spec.link_data.picture (link ads)
    oss = creative.get('object_story_spec') or {}
    link_data = oss.get('link_data') or {}
    if link_data.get('picture'):
        return link_data['picture']
    # video_data.image_url (video with link)
    video_data = oss.get('video_data') or {}
    if video_data.get('image_url'):
        return video_data['image_url']

    # 4. asset_feed_spec — dynamic creative with multiple images/videos
    afs = creative.get('asset_feed_spec') or {}
    images = afs.get('images') or []
    if images and images[0].get('url'):
        return images[0]['url']
    videos = afs.get('videos') or []
    if videos and videos[0].get('thumbnail_url'):
        return videos[0]['thumbnail_url']

    # 5. Carousel (link_data.child_attachments)
    child_attachments = link_data.get('child_attachments') or []
    if child_attachments and child_attachments[0].get('picture'):
        return child_attachments[0]['picture']

    return None


def main():
    db = SessionLocal()
    accounts = db.query(AdAccount).filter(
        AdAccount.is_active.is_(True), AdAccount.platform == 'meta'
    ).all()

    # Map ad_name -> material (within each branch)
    # Multiple combos may share same ad_name but should all point to same material
    combos = db.query(AdCombo).filter(AdCombo.ad_name.isnot(None)).all()
    ad_name_to_materials: dict[tuple[str, str], set[str]] = {}
    for c in combos:
        key = (c.branch_id, c.ad_name)
        ad_name_to_materials.setdefault(key, set()).add(c.material_id)

    total_updated = 0

    for acc in accounts:
        if not acc.access_token_enc:
            continue

        acc_id = acc.account_id if acc.account_id.startswith('act_') else f'act_{acc.account_id}'
        print(f"\n{'='*60}\n{acc.account_name}")

        try:
            FacebookAdsApi.init(app_id='', app_secret='', access_token=acc.access_token_enc)
            fb = FBAdAccount(acc_id)

            # Fetch ads with their creative — dedupe by ad_name client-side
            ads = fb.get_ads(
                fields=['name', 'creative'],
                params={'limit': 500, 'filtering': [
                    {'field': 'ad.effective_status', 'operator': 'IN',
                     'value': ['ACTIVE', 'PAUSED', 'ARCHIVED']},
                ]},
            )

            seen_names: set[str] = set()
            per_branch = 0

            for ad in ads:
                ad_name = ad.get('name', '')
                if not ad_name or ad_name in seen_names:
                    continue
                seen_names.add(ad_name)

                material_ids = ad_name_to_materials.get((acc.id, ad_name))
                if not material_ids:
                    continue  # no combo in DB references this ad_name

                creative_ref = ad.get('creative')
                if not creative_ref:
                    continue
                creative_id = creative_ref.get('id') if isinstance(creative_ref, dict) else getattr(creative_ref, 'get_id_assured', lambda: None)()
                if not creative_id:
                    continue

                try:
                    creative = AdCreative(creative_id).api_get(fields=CREATIVE_FIELDS)
                    url = extract_preview_url(dict(creative))
                except Exception as e:
                    print(f"  {ad_name[:50]:50} | creative fetch failed: {e}")
                    continue

                if not url:
                    continue

                # Update all materials linked to this ad_name
                for mat_id in material_ids:
                    db.execute(
                        text("UPDATE ad_materials SET file_url = :u WHERE material_id = :m"),
                        {'u': url, 'm': mat_id},
                    )
                per_branch += 1
                print(f"  {ad_name[:55]:55} -> {url[:70]}")

            db.commit()
            print(f"  Updated {per_branch} unique ad_names")
            total_updated += per_branch

        except Exception as e:
            print(f"  ERROR: {e}")
            db.rollback()

    db.close()
    print(f"\n{'='*60}\nDONE! Total unique ad_names updated: {total_updated}")


if __name__ == '__main__':
    main()
