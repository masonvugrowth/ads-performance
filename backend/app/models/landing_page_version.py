from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text

from app.models.base import Base, JSONType, TimestampMixin, UUIDType


class LandingPageVersion(TimestampMixin, Base):
    """INSERT-only content snapshot for a managed landing page.

    Follows the budget_allocations pattern: never UPDATE a row, always INSERT
    a new version. The landing_pages.current_version_id FK points at the
    currently-published row.

    `content` is a JSON blob containing:
      - hero:       { headline, subheadline, cta_label, image_url, video_url? }
      - trust_bar:  { items: [{score, source, count}, ...], badges: [...] }
      - one_thing:  { headline, vignette, media_url, quote }
      - rooms:      [{name, size_sqm, bed, view, price_from, price_currency,
                      price_includes, rating, photos: [...], book_url}]
      - location:   { map_embed_url, pins: [...], walk_times: [{minutes,place}],
                      paragraph, arrival_photo_url }
      - experience: [{title, description}]  # emotional bundles, 3-5
      - stories:    [{name, country, trip_type, quote, source, rating,
                      photo_url, date}]
      - offer:      { comparison: [{benefit, ota, direct}], perks: [...] }
      - faq:        [{q, a}]
      - final_cta:  { headline, urgency_line, cta_label, sub_cta_label,
                      sub_cta_href }
      - footer:     { contact: {...}, policies: [...], social: [...] }
      - theme:      { primary_color, dark, light, font_heading, font_body }
      - seo:        { title, description, og_image }
    """

    __tablename__ = "landing_page_versions"

    landing_page_id = Column(
        UUIDType,
        ForeignKey("landing_pages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_num = Column(Integer, nullable=False)
    content = Column(JSONType, nullable=False)
    created_by = Column(
        UUIDType,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    change_note = Column(Text, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
