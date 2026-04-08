"""Tests for Google Ads router endpoints."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models.base import Base
from app.models.account import AdAccount
from app.models.campaign import Campaign
from app.models.google_asset_group import GoogleAssetGroup
from app.models.google_asset import GoogleAsset

# Test DB setup
TEST_DB_URL = "sqlite:///./test_platform.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _create_account(db):
    account = AdAccount(
        id=str(uuid.uuid4()),
        platform="google",
        account_id=f"goog_{uuid.uuid4().hex[:8]}",
        account_name="Test Google Account",
        currency="USD",
        is_active=True,
    )
    db.add(account)
    db.commit()
    return account


def _create_campaign(db, account_id, objective="SEARCH", name="Test Search Campaign"):
    campaign = Campaign(
        id=str(uuid.uuid4()),
        account_id=account_id,
        platform="google",
        platform_campaign_id=f"camp_{uuid.uuid4().hex[:8]}",
        name=name,
        status="ACTIVE",
        objective=objective,
        daily_budget=50.00,
        ta="Solo",
        funnel_stage="TOF",
    )
    db.add(campaign)
    db.commit()
    return campaign


def _create_asset_group(db, campaign_id, account_id):
    group = GoogleAssetGroup(
        id=str(uuid.uuid4()),
        campaign_id=campaign_id,
        account_id=account_id,
        platform_asset_group_id=f"ag_{uuid.uuid4().hex[:8]}",
        name="Test Asset Group",
        status="ACTIVE",
        final_urls=["https://example.com"],
    )
    db.add(group)
    db.commit()
    return group


def _create_asset(db, asset_group_id, account_id, asset_type="HEADLINE", text="Test Headline"):
    asset = GoogleAsset(
        id=str(uuid.uuid4()),
        asset_group_id=asset_group_id,
        account_id=account_id,
        platform_asset_id=f"asset_{uuid.uuid4().hex[:8]}",
        asset_type=asset_type,
        text_content=text,
        performance_label="GOOD",
    )
    db.add(asset)
    db.commit()
    return asset


class TestListGoogleCampaigns:
    def test_empty(self):
        resp = client.get("/api/google/campaigns")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["campaigns"] == []
        assert data["data"]["total"] == 0

    def test_with_campaigns(self):
        db = TestSession()
        account = _create_account(db)
        _create_campaign(db, account.id, "SEARCH", "Search Camp 1")
        _create_campaign(db, account.id, "PERFORMANCE_MAX", "PMax Camp 1")
        db.close()

        resp = client.get("/api/google/campaigns")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] == 2

    def test_filter_by_type(self):
        db = TestSession()
        account = _create_account(db)
        _create_campaign(db, account.id, "SEARCH", "Search Only")
        _create_campaign(db, account.id, "PERFORMANCE_MAX", "PMax Only")
        db.close()

        resp = client.get("/api/google/campaigns?campaign_type=SEARCH")
        data = resp.json()
        assert data["data"]["total"] == 1
        assert data["data"]["campaigns"][0]["campaign_type"] == "SEARCH"


class TestAssetGroups:
    def test_list_asset_groups(self):
        db = TestSession()
        account = _create_account(db)
        campaign = _create_campaign(db, account.id, "PERFORMANCE_MAX", "PMax Camp")
        _create_asset_group(db, campaign.id, account.id)
        db.close()

        resp = client.get("/api/google/asset-groups")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] == 1
        assert data["data"]["asset_groups"][0]["name"] == "Test Asset Group"

    def test_get_asset_group_with_assets(self):
        db = TestSession()
        account = _create_account(db)
        campaign = _create_campaign(db, account.id, "PERFORMANCE_MAX", "PMax")
        group = _create_asset_group(db, campaign.id, account.id)
        _create_asset(db, group.id, account.id, "HEADLINE", "Book Now")
        _create_asset(db, group.id, account.id, "DESCRIPTION", "Best hotel in town")
        group_id = group.id
        db.close()

        resp = client.get(f"/api/google/asset-groups/{group_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["name"] == "Test Asset Group"
        assert len(data["data"]["assets"]) == 2

    def test_asset_group_not_found(self):
        resp = client.get("/api/google/asset-groups/nonexistent")
        assert resp.status_code == 404


class TestGoogleDashboard:
    def test_empty_dashboard(self):
        resp = client.get("/api/google/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["kpis"]["total_spend"] == 0
        assert data["data"]["campaign_counts"]["total"] == 0

    def test_campaign_counts(self):
        db = TestSession()
        account = _create_account(db)
        _create_campaign(db, account.id, "SEARCH", "Search 1")
        _create_campaign(db, account.id, "SEARCH", "Search 2")
        _create_campaign(db, account.id, "PERFORMANCE_MAX", "PMax 1")
        db.close()

        resp = client.get("/api/google/dashboard")
        data = resp.json()
        assert data["data"]["campaign_counts"]["search"] == 2
        assert data["data"]["campaign_counts"]["performance_max"] == 1
        assert data["data"]["campaign_counts"]["total"] == 3
