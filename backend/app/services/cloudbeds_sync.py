"""Cloudbeds reservation sync — pull from Cloudbeds + upsert into reservations.

Mirrors reservation_sync.py shape (chunked commits, robust error handling)
but maps Cloudbeds' getReservationsWithRateDetails payload to the existing
Reservation model so booking_match_service.run_matching keeps working
unchanged.

Branch dispatch lives in reservation_sync.sync_reservations: a branch with
Cloudbeds credentials configured comes here, all others stay on HID PMS.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models.reservation import Reservation
from app.services import cloudbeds_client

logger = logging.getLogger(__name__)

# Same chunk size as the HID sync — keeps each transaction well below the
# Supabase statement_timeout window.
COMMIT_BATCH_SIZE = 100

# Branch key (used for Cloudbeds credentials lookup) → canonical name we
# persist on Reservation.branch. normalize_branch() in booking_match_service
# already handles these, so matching works without changes.
_BRANCH_CANONICAL_NAME: dict[str, str] = {
    "Saigon": "Meander Saigon",
    "Taipei": "Meander Taipei",
    "1948": "Meander 1948",
    "Osaka": "Meander Osaka",
    "Oani": "Oani",
}


# ---------- field parsers --------------------------------------------------


def _parse_date(val) -> date | None:
    if not val:
        return None
    try:
        return date.fromisoformat(str(val)[:10])
    except (ValueError, TypeError):
        return None


def _parse_numeric(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _join_unique(items, sep: str = ", ") -> str | None:
    out: list[str] = []
    seen: set[str] = set()
    for it in items:
        if not it:
            continue
        key = str(it).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return sep.join(out) if out else None


# ---------- field extractors -----------------------------------------------


def _extract_room_types(raw: dict) -> str | None:
    rooms = raw.get("assigned") or []
    return _join_unique(r.get("roomTypeName") for r in rooms)


def _extract_rate_plans(raw: dict) -> str | None:
    """Cloudbeds analogue of HID's 'rate plan' is the per-room marketName
    (e.g. 'Retail', 'Direct Booking', 'Booking.com'). Some properties use
    rateName instead — fall back to that if marketName is empty.
    """
    rooms = raw.get("assigned") or []
    return _join_unique(
        (r.get("marketName") or r.get("rateName") or "")
        for r in rooms
    )


def _sum_adults(raw: dict) -> int | None:
    rooms = raw.get("assigned") or []
    total = 0
    seen_value = False
    for r in rooms:
        v = _parse_int(r.get("adults"))
        if v is not None:
            total += v
            seen_value = True
    if seen_value:
        return total
    return _parse_int(raw.get("adults"))


def _grand_total(raw: dict) -> float | None:
    """Prefer balanceDetailed.grandTotal (taxes + fees included), fall back
    to the top-level total."""
    detailed = raw.get("balanceDetailed") or {}
    if isinstance(detailed, dict):
        gt = detailed.get("grandTotal")
        if gt is not None:
            return _parse_numeric(gt)
    return _parse_numeric(raw.get("total"))


def _source_name(raw: dict) -> str | None:
    """Cloudbeds returns source as a string in some endpoints, dict in others
    ({name, paymentCollect, sourceID, category}). Normalize to the human
    name so downstream filters can do case-insensitive substring matches."""
    s = raw.get("source") or raw.get("sourceName")
    if isinstance(s, dict):
        return s.get("name")
    return s


def _calc_nights(check_in: date | None, check_out: date | None) -> int | None:
    if not check_in or not check_out:
        return None
    delta = (check_out - check_in).days
    return delta if delta >= 0 else None


def _normalise_country(raw: dict) -> str | None:
    """Cloudbeds returns ISO-2 country codes (e.g. 'CN', 'VN'). Store as-is
    in upper case so country_iso_matches_reservation can hit its fast path."""
    val = (raw.get("guestCountry") or "").strip().upper()
    return val or None


def _extract_email(raw: dict) -> str | None:
    """getReservationsWithRateDetails doesn't always surface guestEmail at
    top level — fall back to digging into guestList[<id>].guestEmail."""
    direct = raw.get("guestEmail")
    if direct:
        return direct
    guest_list = raw.get("guestList") or {}
    if isinstance(guest_list, dict):
        for guest in guest_list.values():
            if isinstance(guest, dict) and guest.get("guestEmail"):
                return guest["guestEmail"]
    return None


def _map_to_fields(raw: dict, branch_key: str) -> dict:
    branch_canonical = _BRANCH_CANONICAL_NAME.get(branch_key, branch_key)
    check_in = _parse_date(raw.get("reservationCheckIn") or raw.get("startDate"))
    check_out = _parse_date(raw.get("reservationCheckOut") or raw.get("endDate"))
    return {
        "reservation_date": _parse_date(raw.get("dateCreated")),
        "check_in_date": check_in,
        "check_out_date": check_out,
        "grand_total": _grand_total(raw),
        "country": _normalise_country(raw),
        "name": raw.get("guestName") or None,
        "email": _extract_email(raw),
        "status": raw.get("status") or None,
        "source": _source_name(raw),
        "room_type": _extract_room_types(raw),
        "rate_plan_name": _extract_rate_plans(raw),
        "branch": branch_canonical,
        "nights": _calc_nights(check_in, check_out),
        "adults": _sum_adults(raw),
        "raw_data": raw,
    }


# ---------- sync entrypoint ------------------------------------------------


def sync_branch(
    db: Session,
    branch_key: str,
    date_from: date,
    date_to: date,
) -> dict:
    """Pull Cloudbeds reservations for one branch + upsert into DB.

    Returns a per-branch summary. Errors on individual rows are recorded but
    don't abort the run; an OperationalError on a batch commit (e.g. a
    statement_timeout) rolls back that batch only.
    """
    raw_reservations = cloudbeds_client.fetch_reservations(
        branch_key, date_from, date_to,
    )

    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []
    in_batch = 0
    batches_committed = 0

    def _flush() -> None:
        nonlocal in_batch, batches_committed
        try:
            db.commit()
            batches_committed += 1
        except OperationalError as e:
            db.rollback()
            errors.append(f"batch rollback: {e}")
            logger.warning(
                "Cloudbeds batch commit OperationalError (branch=%s): %s",
                branch_key, e,
            )
        in_batch = 0

    for raw in raw_reservations:
        try:
            res_id = raw.get("reservationID")
            if not res_id:
                skipped += 1
                continue

            fields = _map_to_fields(raw, branch_key)

            existing = db.query(Reservation).filter(
                Reservation.reservation_number == str(res_id),
            ).first()

            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
                existing.updated_at = datetime.now(timezone.utc)
                updated += 1
            else:
                db.add(Reservation(reservation_number=str(res_id), **fields))
                db.flush()
                created += 1

            in_batch += 1
            if in_batch >= COMMIT_BATCH_SIZE:
                _flush()

        except Exception as e:
            db.rollback()
            errors.append(str(e))
            logger.warning(
                "Failed to upsert Cloudbeds reservation %s (branch=%s): %s",
                raw.get("reservationID"), branch_key, e,
            )
            in_batch = 0

    if in_batch > 0:
        _flush()

    summary = {
        "branch": branch_key,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "fetched": len(raw_reservations),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "batches_committed": batches_committed,
        "errors": errors,
    }
    logger.info("Cloudbeds sync complete: %s", summary)
    return summary
