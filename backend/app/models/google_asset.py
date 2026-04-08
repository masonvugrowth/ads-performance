from sqlalchemy import Column, ForeignKey, String, Text, UniqueConstraint

from app.models.base import Base, JSONType, TimestampMixin, UUIDType


class GoogleAsset(TimestampMixin, Base):
    __tablename__ = "google_assets"
    __table_args__ = (
        UniqueConstraint("asset_group_id", "platform_asset_id", name="uq_asset_group_asset"),
    )

    asset_group_id = Column(
        UUIDType,
        ForeignKey("google_asset_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id = Column(
        UUIDType,
        ForeignKey("ad_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform_asset_id = Column(String(100), nullable=False)
    asset_type = Column(String(30), nullable=False, index=True)
    # HEADLINE | DESCRIPTION | IMAGE | VIDEO | LOGO | CALL_TO_ACTION | BUSINESS_NAME
    text_content = Column(String(500), nullable=True)  # For headlines/descriptions
    image_url = Column(Text, nullable=True)  # For images/logos/videos
    performance_label = Column(String(30), nullable=True)  # BEST | GOOD | LOW | LEARNING | PENDING
    raw_data = Column(JSONType, nullable=True)
