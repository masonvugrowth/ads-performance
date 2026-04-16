"""Per-branch + per-section permission helpers.

Model:
- User has 0..N rows in `user_permissions`, each (branch, section, level).
- level='view' => read-only for that (branch, section).
- level='edit' => read + write.
- No row => no access to that (branch, section).
- If user.roles contains 'admin' => bypass everything (full edit on all).
"""
from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_permission import UserPermission

# ── Canonical constants ────────────────────────────────────────

BRANCHES: list[str] = ["Saigon", "Osaka", "Taipei", "1948", "Oani", "Bread"]

SECTIONS: list[str] = [
    "analytics",
    "meta_ads",
    "google_ads",
    "budget",
    "automation",
    "ai",
    "settings",
]

LEVELS: list[str] = ["view", "edit"]

# 'edit' implies 'view' — use this for comparisons
_LEVEL_RANK = {"view": 1, "edit": 2}


# ── Core helpers ───────────────────────────────────────────────


def is_admin(user: User | None) -> bool:
    if user is None:
        return False
    return "admin" in (user.roles or [])


def _level_at_least(have: str, need: str) -> bool:
    return _LEVEL_RANK.get(have, 0) >= _LEVEL_RANK.get(need, 0)


def accessible_branches(
    db: Session,
    user: User,
    section: str,
    min_level: str = "view",
) -> list[str] | None:
    """Return branch names the user can access at >= min_level for `section`.

    Returns None when the user is an admin — meaning "no branch filter, all allowed".
    Returns [] when the user has no access at all (callers should treat as empty result).
    """
    if is_admin(user):
        return None
    if section not in SECTIONS:
        return []

    rows = (
        db.query(UserPermission.branch, UserPermission.level)
        .filter(UserPermission.user_id == user.id, UserPermission.section == section)
        .all()
    )
    return [b for (b, lvl) in rows if _level_at_least(lvl, min_level)]


def has_section_access(
    db: Session,
    user: User,
    section: str,
    min_level: str = "view",
) -> bool:
    """True if user has ANY branch access at >= min_level for `section`."""
    if is_admin(user):
        return True
    branches = accessible_branches(db, user, section, min_level)
    return bool(branches)


def has_branch_access(
    db: Session,
    user: User,
    section: str,
    branch: str,
    min_level: str = "view",
) -> bool:
    """True if user can access `branch` in `section` at >= min_level."""
    if is_admin(user):
        return True
    branches = accessible_branches(db, user, section, min_level)
    return branch in (branches or [])


def resolve_branch_filter(
    db: Session,
    user: User,
    section: str,
    requested_branch: str | None,
    min_level: str = "view",
) -> tuple[bool, list[str] | None, str | None]:
    """Helper used by list endpoints to resolve a client-supplied branch param.

    Returns (ok, branches_filter, error_message):
      - ok=False with error when a requested branch is not permitted
      - ok=True with branches_filter=None   -> admin, no filter needed
      - ok=True with branches_filter=[...]  -> filter results to these branch names
      - ok=True with branches_filter=[req]  -> a single specific branch was requested and is allowed
    """
    if is_admin(user):
        if requested_branch:
            return True, [requested_branch], None
        return True, None, None

    allowed = accessible_branches(db, user, section, min_level) or []
    if requested_branch:
        if requested_branch not in allowed:
            return False, None, f"No {min_level} access to branch '{requested_branch}'"
        return True, [requested_branch], None
    return True, allowed, None


def scoped_account_ids(
    db: Session,
    user: User,
    section: str,
    requested_account_id: str | None = None,
    requested_branches: list[str] | None = None,
    min_level: str = "view",
) -> tuple[bool, list[str] | None, str | None]:
    """Resolve the final account-id filter for an analytics-style endpoint.

    Returns (ok, account_ids, error):
      - ok=False + error   -> caller should return 403 with the error string
      - account_ids=None   -> no filter (admin + no params)
      - account_ids=[...]  -> apply .filter(account_id IN (...))
      - account_ids=[]     -> caller should return an empty result

    Branch -> account IDs mapping uses get_account_ids_for_branches in accounts.py.
    """
    # Local import to avoid circular imports at module load time
    from app.routers.accounts import get_account_ids_for_branches

    admin = is_admin(user)

    # Admin: honor whatever the client asked for
    if admin:
        if requested_account_id:
            return True, [requested_account_id], None
        if requested_branches:
            ids = get_account_ids_for_branches(db, requested_branches)
            return True, ids, None
        return True, None, None

    allowed_branches = accessible_branches(db, user, section, min_level) or []
    if not allowed_branches:
        return False, None, f"No {min_level} access to section '{section}'"

    allowed_ids = set(get_account_ids_for_branches(db, allowed_branches))

    # Client asked for a specific account_id — it must be within allowed set
    if requested_account_id:
        if requested_account_id not in allowed_ids:
            return False, None, f"No {min_level} access to account '{requested_account_id}'"
        return True, [requested_account_id], None

    # Client asked for branches — intersect
    if requested_branches:
        req_ids = set(get_account_ids_for_branches(db, requested_branches))
        unauthorized = [
            b for b in requested_branches if b not in allowed_branches
        ]
        if unauthorized:
            return False, None, f"No {min_level} access to branches: {unauthorized}"
        return True, list(req_ids & allowed_ids), None

    # Default: all accounts the user can see for this section
    return True, list(allowed_ids), None


def permission_dict(user: User, permissions: Iterable[UserPermission]) -> dict:
    """Shape used by /auth/me and /users/{id}/permissions responses."""
    items = [
        {"branch": p.branch, "section": p.section, "level": p.level}
        for p in permissions
    ]
    # accessible_sections is a denormalised view keyed by section for quick UI lookups.
    accessible: dict[str, list[str]] = {s: [] for s in SECTIONS}
    for p in permissions:
        if p.section in accessible and p.branch not in accessible[p.section]:
            accessible[p.section].append(p.branch)
    return {
        "is_admin": is_admin(user),
        "permissions": items,
        "accessible_sections": accessible,
    }
