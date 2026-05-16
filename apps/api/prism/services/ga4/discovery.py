"""List GA4 properties accessible to a Google user via the Admin REST API.

Prefers `access_token` (hot path right after OAuth) over `refresh_token`
(slow path requiring a token refresh round-trip).
"""
from __future__ import annotations

import httpx

from prism.config import get_settings
from prism.core.logging import logger

_ADMIN_BASE = "https://analyticsadmin.googleapis.com/v1beta"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


async def _refresh_to_access_token(refresh_token: str) -> str:
    """Exchange a refresh token for a fresh access token."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            _TOKEN_URL,
            data={
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
    if r.status_code != 200:
        msg = f"Google token refresh failed: {r.status_code} {r.text[:200]}"
        raise RuntimeError(msg)
    return r.json()["access_token"]


async def list_ga4_properties(
    access_token: str | None = None,
    refresh_token: str | None = None,
) -> list[dict]:
    """Return GA4 properties the authenticated user can read.

    Result shape: `[{property_id, display_name, account_name}, ...]`.
    `property_id` is the bare numeric ID (no `properties/` prefix).
    """
    if not access_token:
        if not refresh_token:
            msg = "Need access_token or refresh_token"
            raise RuntimeError(msg)
        access_token = await _refresh_to_access_token(refresh_token)

    headers = {"Authorization": f"Bearer {access_token}"}
    properties: list[dict] = []
    next_token: str | None = None

    async with httpx.AsyncClient(timeout=20) as c:
        while True:
            params: dict = {"pageSize": 200}
            if next_token:
                params["pageToken"] = next_token
            r = await c.get(
                f"{_ADMIN_BASE}/accountSummaries",
                headers=headers,
                params=params,
            )
            if r.status_code != 200:
                logger.error(
                    "GA4 Admin API list failed",
                    status=r.status_code,
                    body=r.text[:300],
                )
                msg = f"GA4 Admin API: {r.status_code}"
                raise RuntimeError(msg)
            data = r.json()
            for acct in data.get("accountSummaries", []):
                acct_name = acct.get("displayName", "(unnamed account)")
                for prop in acct.get("propertySummaries", []):
                    raw = prop.get("property", "")
                    properties.append({
                        "property_id": raw.removeprefix("properties/"),
                        "display_name": prop.get("displayName", "(unnamed)"),
                        "account_name": acct_name,
                    })
            next_token = data.get("nextPageToken")
            if not next_token:
                break

    properties.sort(key=lambda p: (p["account_name"].lower(), p["display_name"].lower()))
    return properties
