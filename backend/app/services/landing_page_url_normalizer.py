"""URL normalization for matching ad destination URLs → landing pages.

Two normalization levels:

    raw_url                                                          (full URL from ad or Clarity)
       │
       ▼
    canonical_url       scheme://host/path   — strips *all* query strings, fragment, trailing slash
                                             — lowercased host                                       ← identity of a landing page
       │
       ▼
    (host, slug)        ("osk.staymeander.com", "couple-traveler-direct-zh")
                        host matches landing_pages.domain, slug matches landing_pages.slug

Plus a helper to extract UTM tags (utm_source / utm_medium / utm_campaign /
utm_content / utm_term) and to strip ad-platform click-id noise (fbclid,
gclid, gbraid, wbraid, gad_*) when we want to compare canonical URLs.

This module has zero DB / framework dependencies — it is pure and easy to
unit-test.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from urllib.parse import parse_qsl, urlparse, urlunparse

# Query-string keys that are ad-platform click ids or internal tracking —
# stripped from the canonical URL because they change every click.
_CLICK_ID_KEYS = {
    "fbclid", "gclid", "gbraid", "wbraid", "msclkid", "yclid", "ttclid",
    "gad_source", "gad_campaignid", "fb_source", "_ga", "ref",
    "s_kwcid", "mc_eid", "mc_cid",
}

# UTM keys we extract and persist as separate columns.
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")

# Meta-specific IDs worth keeping context on, but they are *not* UTMs.
_META_TAG_KEYS = {"utm_id"}


@dataclass(frozen=True)
class NormalizedUrl:
    raw: str
    canonical: str          # scheme://host/path, no query, lowercased host
    host: str               # lowercased, no port
    path: str               # path without trailing slash (unless root)
    slug: str               # path.lstrip('/'), no trailing slash
    utm: dict[str, str]     # utm_* only
    extra_query: dict[str, str]  # non-utm, non-click-id params (meta utm_id, etc.)


def normalize_url(raw_url: str) -> NormalizedUrl | None:
    """Parse a URL into its canonical parts.

    Returns None for non-http(s) or malformed input.
    """
    if not raw_url or not isinstance(raw_url, str):
        return None
    raw = raw_url.strip()
    if not raw:
        return None

    try:
        p = urlparse(raw)
    except Exception:
        return None

    if p.scheme not in ("http", "https"):
        return None
    if not p.netloc:
        return None

    host = p.hostname or ""
    host = host.lower()

    path = p.path or "/"
    # Collapse trailing slash except for root
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    slug = path.lstrip("/")

    # Query parsing — keep_blank_values=False so ?utm_source= doesn't land as ""
    qparams = parse_qsl(p.query, keep_blank_values=False)
    utm: dict[str, str] = {}
    extra: dict[str, str] = {}
    for key, val in qparams:
        k = key.lower()
        if k in UTM_KEYS:
            utm[k] = val
        elif k in _CLICK_ID_KEYS:
            continue
        elif k in _META_TAG_KEYS:
            extra[k] = val
        else:
            extra[k] = val

    canonical = urlunparse((p.scheme, host, path, "", "", ""))
    return NormalizedUrl(
        raw=raw,
        canonical=canonical,
        host=host,
        path=path,
        slug=slug,
        utm=utm,
        extra_query=extra,
    )


def match_lookup_key(raw_url: str) -> tuple[str, str] | None:
    """Return (host, slug) for DB lookup, or None if not parseable."""
    n = normalize_url(raw_url)
    if n is None:
        return None
    return (n.host, n.slug)


def build_url_with_utms(
    canonical_url: str,
    utms: Mapping[str, str],
) -> str:
    """Append utm_* params to a canonical URL for use as an ad destination."""
    n = normalize_url(canonical_url)
    base = n.canonical if n else canonical_url
    clean = {k: v for k, v in utms.items() if k in UTM_KEYS and v}
    if not clean:
        return base
    from urllib.parse import urlencode

    sep = "&" if "?" in base else "?"
    return f"{base}{sep}{urlencode(clean)}"


def infer_branch_from_host(host: str) -> str | None:
    """Map staymeander subdomains → branch names used in user_permissions.

    Subdomain patterns observed in Clarity data:
        osk.staymeander.com            → Osaka
        1948.staymeander.com           → 1948
        oani-taipei.staymeander.com    → Oani
        tpe.staymeander.com (guess)    → Taipei
        sgn.staymeander.com (guess)    → Saigon

    Returns canonical branch name or None if the host doesn't match a
    known pattern — the caller can then prompt the user to assign a branch.
    """
    if not host:
        return None
    host = host.lower()
    sub = host.split(".", 1)[0] if "." in host else host
    mapping = {
        "osk": "Osaka",
        "osaka": "Osaka",
        "1948": "1948",
        "tpe": "Taipei",
        "taipei": "Taipei",
        "sgn": "Saigon",
        "saigon": "Saigon",
        "oani": "Oani",
        "oani-taipei": "Oani",
        "bread": "Bread",
    }
    return mapping.get(sub)
