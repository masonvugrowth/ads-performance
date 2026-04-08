from sqlalchemy import Column, ForeignKey, String

from app.models.base import Base, JSONType, TimestampMixin, UUIDType


class GoogleAssetGroup(TimestampMixin, Base):
    __tablename__ = "google_asset_groups"

    campaign_id = Column(
        UUIDType,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id = Column(
        UUIDType,
        ForeignKey("ad_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform_asset_group_id = Column(String(100), nullable=False, unique=True)
    name = Column(String(500), nullable=False)
    status = Column(String(30), nullable=False, index=True)  # ACTIVE | PAUSED | ARCHIVED
    final_urls = Column(JSONType, nullable=True)  # List of landing page URLs
    raw_data = Column(JSONType, nullable=True)
