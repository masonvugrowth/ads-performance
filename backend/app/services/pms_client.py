"""PMS (Property Management System) API client.

Fetches reservation data from the HID Dashboard API.
Uses requests (sync) for Celery task compatibility.
"""

import logging
from datetime import date

import requests

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = settings.PMS_API_BASE_URL.rstrip("/")
RESERVATIONS_ENDPOINT = f"{BASE_URL}/api/public/reservations"


def fetch_reservations(
    date_from: date,
    date_to: date,
    branch_id: str | None = None,
    limit: int = 1000,
) -> list[dict]:
    """Fetch all reservations from PMS API with pagination.

    Args:
        date_from: Start date for check-in filter.
        date_to: End date for check-in filter.
        branch_id: Optional branch UUID filter.
        limit: Max results per page (API max 1000).

    Returns:
        List of reservation dicts from the API.
    """
    headers = {"X-API-Key": settings.PMS_API_KEY}
    all_reservations: list[dict] = []
    offset = 0

    while True:
        params = {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "limit": limit,
            "offset": offset,
        }
        if branch_id:
            params["branch_id"] = branch_id

        try:
            resp = requests.get(
                RESERVATIONS_ENDPOINT,
                headers=headers,
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()
        except requests.RequestException:
            logger.exception(
                "PMS API request failed (offset=%d, date_from=%s, date_to=%s)",
                offset, date_from, date_to,
            )
            raise

        if not body.get("success"):
            error_msg = body.get("error", "Unknown PMS API error")
            logger.error("PMS API returned error: %s", error_msg)
            raise RuntimeError(f"PMS API error: {error_msg}")

        data = body.get("data", {})
        reservations = data.get("reservations", [])
        total = data.get("total", 0)

        all_reservations.extend(reservations)
        offset += limit

        if offset >= total or not reservations:
            break

    logger.info(
        "Fetched %d reservations from PMS (%s to %s)",
        len(all_reservations), date_from, date_to,
    )
    return all_reservations
