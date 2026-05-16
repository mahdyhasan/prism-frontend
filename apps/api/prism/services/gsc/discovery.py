"""List Search Console sites a Google user has verified access to."""
from __future__ import annotations

import httpx

from prism.core.logging import logger
from prism.services.ga4.discovery import _refresh_to_access_token

_SC_BASE = "https://www.googleapis.com/webmasters/v3"


async def list_gsc_sites(
    access_token: str | None = None,
    refresh_token: str | None = None,
) -> list[dict]:
    """Return GSC sites the authenticated user can read.

    Filters out unverified sites. Result shape: `[{site_url, permission_level}, ...]`.
    """
    if not access_token:
        if not refresh_token:
            msg = "Need access_token or refresh_token"
            raise RuntimeError(msg)
        access_token = await _refresh_to_access_token(refresh_token)

    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(
            f"{_SC_BASE}/sites",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if r.status_code != 200:
        logger.error(
            "GSC sites list failed",
            status=r.status_code,
            body=r.text[:300],
        )
        msg = f"GSC API: {r.status_code}"
        raise RuntimeError(msg)

    sites = []
    for entry in r.json().get("siteEntry", []):
        level = entry.get("permissionLevel", "")
        # Exclude sites the user hasn't verified yet
        if level == "siteUnverifiedUser":
            continue
        sites.append({
            "site_url": entry.get("siteUrl", ""),
            "permission_level": level,
        })
    sites.sort(key=lambda s: s["site_url"])
    return sites
