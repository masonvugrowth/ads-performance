"""Google Ads API write operations: pause, enable, adjust budget.

Uses the Google Ads mutate API via the google-ads Python SDK.
Google uses customer_id (not access_token) — credentials from global .env.
"""

import logging

from google.ads.googleads.errors import GoogleAdsException

from app.services.google_client import _get_client

logger = logging.getLogger(__name__)


def pause_campaign(customer_id: str, platform_campaign_id: str) -> bool:
    """Set a Google Ads campaign status to PAUSED."""
    customer_id = customer_id.replace("-", "")
    client = _get_client()
    try:
        campaign_service = client.get_service("CampaignService")
        campaign_operation = client.get_type("CampaignOperation")
        campaign = campaign_operation.update
        campaign.resource_name = campaign_service.campaign_path(customer_id, platform_campaign_id)
        campaign.status = client.enums.CampaignStatusEnum.PAUSED
        client.copy_from(
            campaign_operation.update_mask,
            client.get_type("FieldMask")(paths=["status"]),
        )
        campaign_service.mutate_campaigns(
            customer_id=customer_id, operations=[campaign_operation]
        )
        logger.info("Paused Google campaign %s", platform_campaign_id)
        return True
    except GoogleAdsException as ex:
        logger.exception("Google Ads API error pausing campaign %s: %s", platform_campaign_id, ex.failure)
        raise
    except Exception:
        logger.exception("Failed to pause Google campaign %s", platform_campaign_id)
        raise


def enable_campaign(customer_id: str, platform_campaign_id: str) -> bool:
    """Set a Google Ads campaign status to ENABLED."""
    customer_id = customer_id.replace("-", "")
    client = _get_client()
    try:
        campaign_service = client.get_service("CampaignService")
        campaign_operation = client.get_type("CampaignOperation")
        campaign = campaign_operation.update
        campaign.resource_name = campaign_service.campaign_path(customer_id, platform_campaign_id)
        campaign.status = client.enums.CampaignStatusEnum.ENABLED
        client.copy_from(
            campaign_operation.update_mask,
            client.get_type("FieldMask")(paths=["status"]),
        )
        campaign_service.mutate_campaigns(
            customer_id=customer_id, operations=[campaign_operation]
        )
        logger.info("Enabled Google campaign %s", platform_campaign_id)
        return True
    except GoogleAdsException as ex:
        logger.exception("Google Ads API error enabling campaign %s: %s", platform_campaign_id, ex.failure)
        raise
    except Exception:
        logger.exception("Failed to enable Google campaign %s", platform_campaign_id)
        raise


def pause_ad_group(customer_id: str, platform_ad_group_id: str) -> bool:
    """Set a Google Ads ad group status to PAUSED."""
    customer_id = customer_id.replace("-", "")
    client = _get_client()
    try:
        ad_group_service = client.get_service("AdGroupService")
        operation = client.get_type("AdGroupOperation")
        ad_group = operation.update
        ad_group.resource_name = ad_group_service.ad_group_path(customer_id, platform_ad_group_id)
        ad_group.status = client.enums.AdGroupStatusEnum.PAUSED
        client.copy_from(
            operation.update_mask,
            client.get_type("FieldMask")(paths=["status"]),
        )
        ad_group_service.mutate_ad_groups(
            customer_id=customer_id, operations=[operation]
        )
        logger.info("Paused Google ad group %s", platform_ad_group_id)
        return True
    except GoogleAdsException as ex:
        logger.exception("Google Ads API error pausing ad group %s: %s", platform_ad_group_id, ex.failure)
        raise
    except Exception:
        logger.exception("Failed to pause Google ad group %s", platform_ad_group_id)
        raise


def enable_ad_group(customer_id: str, platform_ad_group_id: str) -> bool:
    """Set a Google Ads ad group status to ENABLED."""
    customer_id = customer_id.replace("-", "")
    client = _get_client()
    try:
        ad_group_service = client.get_service("AdGroupService")
        operation = client.get_type("AdGroupOperation")
        ad_group = operation.update
        ad_group.resource_name = ad_group_service.ad_group_path(customer_id, platform_ad_group_id)
        ad_group.status = client.enums.AdGroupStatusEnum.ENABLED
        client.copy_from(
            operation.update_mask,
            client.get_type("FieldMask")(paths=["status"]),
        )
        ad_group_service.mutate_ad_groups(
            customer_id=customer_id, operations=[operation]
        )
        logger.info("Enabled Google ad group %s", platform_ad_group_id)
        return True
    except GoogleAdsException as ex:
        logger.exception("Google Ads API error enabling ad group %s: %s", platform_ad_group_id, ex.failure)
        raise
    except Exception:
        logger.exception("Failed to enable Google ad group %s", platform_ad_group_id)
        raise


def pause_ad(customer_id: str, platform_ad_group_id: str, platform_ad_id: str) -> bool:
    """Set a Google Ads ad (ad_group_ad) status to PAUSED."""
    customer_id = customer_id.replace("-", "")
    client = _get_client()
    try:
        ad_group_ad_service = client.get_service("AdGroupAdService")
        operation = client.get_type("AdGroupAdOperation")
        ad_group_ad = operation.update
        ad_group_ad.resource_name = ad_group_ad_service.ad_group_ad_path(
            customer_id, platform_ad_group_id, platform_ad_id
        )
        ad_group_ad.status = client.enums.AdGroupAdStatusEnum.PAUSED
        client.copy_from(
            operation.update_mask,
            client.get_type("FieldMask")(paths=["status"]),
        )
        ad_group_ad_service.mutate_ad_group_ads(
            customer_id=customer_id, operations=[operation]
        )
        logger.info("Paused Google ad %s", platform_ad_id)
        return True
    except GoogleAdsException as ex:
        logger.exception("Google Ads API error pausing ad %s: %s", platform_ad_id, ex.failure)
        raise
    except Exception:
        logger.exception("Failed to pause Google ad %s", platform_ad_id)
        raise


def enable_ad(customer_id: str, platform_ad_group_id: str, platform_ad_id: str) -> bool:
    """Set a Google Ads ad (ad_group_ad) status to ENABLED."""
    customer_id = customer_id.replace("-", "")
    client = _get_client()
    try:
        ad_group_ad_service = client.get_service("AdGroupAdService")
        operation = client.get_type("AdGroupAdOperation")
        ad_group_ad = operation.update
        ad_group_ad.resource_name = ad_group_ad_service.ad_group_ad_path(
            customer_id, platform_ad_group_id, platform_ad_id
        )
        ad_group_ad.status = client.enums.AdGroupAdStatusEnum.ENABLED
        client.copy_from(
            operation.update_mask,
            client.get_type("FieldMask")(paths=["status"]),
        )
        ad_group_ad_service.mutate_ad_group_ads(
            customer_id=customer_id, operations=[operation]
        )
        logger.info("Enabled Google ad %s", platform_ad_id)
        return True
    except GoogleAdsException as ex:
        logger.exception("Google Ads API error enabling ad %s: %s", platform_ad_id, ex.failure)
        raise
    except Exception:
        logger.exception("Failed to enable Google ad %s", platform_ad_id)
        raise


def update_campaign_budget(
    customer_id: str, platform_campaign_id: str, new_budget_micros: int
) -> bool:
    """Update a Google Ads campaign's daily budget (in micros: 1,000,000 = 1 unit)."""
    customer_id = customer_id.replace("-", "")
    client = _get_client()
    try:
        # First, get the campaign's budget resource name
        ga_service = client.get_service("GoogleAdsService")
        query = f"""
            SELECT campaign.campaign_budget
            FROM campaign
            WHERE campaign.id = {platform_campaign_id}
        """
        stream = ga_service.search_stream(customer_id=customer_id, query=query)
        budget_resource = None
        for batch in stream:
            for row in batch.results:
                budget_resource = row.campaign.campaign_budget
                break
            break

        if not budget_resource:
            raise ValueError(f"Budget not found for campaign {platform_campaign_id}")

        # Mutate the budget
        budget_service = client.get_service("CampaignBudgetService")
        operation = client.get_type("CampaignBudgetOperation")
        budget = operation.update
        budget.resource_name = budget_resource
        budget.amount_micros = new_budget_micros
        client.copy_from(
            operation.update_mask,
            client.get_type("FieldMask")(paths=["amount_micros"]),
        )
        budget_service.mutate_campaign_budgets(
            customer_id=customer_id, operations=[operation]
        )
        logger.info(
            "Updated budget for Google campaign %s to %d micros",
            platform_campaign_id, new_budget_micros,
        )
        return True
    except GoogleAdsException as ex:
        logger.exception(
            "Google Ads API error updating budget for campaign %s: %s",
            platform_campaign_id, ex.failure,
        )
        raise
    except Exception:
        logger.exception("Failed to update budget for Google campaign %s", platform_campaign_id)
        raise
