"""Chrome UX Report (CrUX) API client.

Provides an async client for the CrUX v1 API and a helper that stores
origin-level field data for a PRISM property.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.logging import logger
from prism.db.models.cwv import CWVOriginAudit, PropertySettings

_CRUX_URL = "https://chromeuxreport.googleapis.com/v1/records:queryRecord"
_TIMEOUT = 30.0

_FORM_FACTOR_MAP = {
    "mobile": "PHONE",
    "desktop": "DESKTOP",
    "all": "ALL_FORM_FACTORS",
}

_METRICS = [
    "largest_contentful_paint",
    "interaction_to_next_paint",
    "cumulative_layout_shift",
    "first_contentful_paint",
    "experimental_time_to_first_byte",
]


def _cwv_status(lcp_ms: int | None, inp_ms: int | None, cls: float | None) -> str:
    if lcp_ms is None and inp_ms is None and cls is None:
        return "insufficient_data"
    poor = (
        (lcp_ms is not None and lcp_ms > 4000)
        or (inp_ms is not None and inp_ms > 500)
        or (cls is not None and cls > 0.25)
    )
    if poor:
        return "poor"
    good = (
        (lcp_ms is None or lcp_ms <= 2500)
        and (inp_ms is None or inp_ms <= 200)
        and (cls is None or cls <= 0.1)
    )
    return "good" if good else "needs_improvement"


def _p75(metrics: dict, key: str) -> float | None:
    m = metrics.get(key, {})
    p = m.get("percentiles", {}).get("p75")
    return float(p) if p is not None else None


def _derive_origin(property_gsc_url: str | None, property_ga4_id: str | None) -> str | None:
    """Derive HTTPS origin from GSC site URL or GA4 property ID."""
    if property_gsc_url:
        url = property_gsc_url.strip()
        if url.startswith("sc-domain:"):
            domain = url[len("sc-domain:"):]
            return f"https://{domain}"
        if url.startswith("http"):
            # Strip trailing slash and path
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}"
    return None


class CrUXClient:
    """Async client for the Chrome UX Report v1 API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    async def get_origin(
        self, origin: str, form_factor: str = "PHONE"
    ) -> dict[str, Any]:
        """Fetch origin-level CrUX field data.

        Returns a structured dict with p75 metrics.
        Returns field_data_available=False silently when CrUX has no data (HTTP 404).
        Raises RuntimeError on other non-2xx responses.
        """
        body: dict[str, Any] = {
            "origin": origin,
            "formFactor": form_factor,
            "metrics": _METRICS,
        }
        params = {}
        if self._api_key:
            params["key"] = self._api_key

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(_CRUX_URL, json=body, params=params)

        if response.status_code == 404:
            logger.info("No CrUX data for origin", origin=origin, form_factor=form_factor)
            return {
                "origin": origin,
                "form_factor": form_factor,
                "lcp_ms": None,
                "inp_ms": None,
                "cls": None,
                "fcp_ms": None,
                "ttfb_ms": None,
                "field_data_available": False,
                "cwv_status": "insufficient_data",
            }

        if response.status_code != 200:
            raise RuntimeError(
                f"CrUX API returned {response.status_code}: {response.text[:200]}"
            )

        data = response.json()
        metrics = data.get("record", {}).get("metrics", {})

        lcp = _p75(metrics, "largest_contentful_paint")
        lcp_ms = int(lcp) if lcp is not None else None

        inp = _p75(metrics, "interaction_to_next_paint")
        inp_ms = int(inp) if inp is not None else None

        cls_val = _p75(metrics, "cumulative_layout_shift")

        fcp = _p75(metrics, "first_contentful_paint")
        fcp_ms = int(fcp) if fcp is not None else None

        ttfb = _p75(metrics, "experimental_time_to_first_byte")
        ttfb_ms = int(ttfb) if ttfb is not None else None

        return {
            "origin": origin,
            "form_factor": form_factor,
            "lcp_ms": lcp_ms,
            "inp_ms": inp_ms,
            "cls": round(float(cls_val), 4) if cls_val is not None else None,
            "fcp_ms": fcp_ms,
            "ttfb_ms": ttfb_ms,
            "field_data_available": bool(metrics),
            "cwv_status": _cwv_status(lcp_ms, inp_ms, cls_val),
        }


async def get_origin_cwv_for_property(
    property_id: int,
    db: AsyncSession,
) -> list[CWVOriginAudit]:
    """Fetch CrUX origin data for all enabled strategies for a property.

    Stores one CWVOriginAudit row per strategy. Returns the created rows.
    """
    from prism.db.models.property import Property
    from prism.config import get_settings

    prop = (await db.execute(
        select(Property).where(Property.id == property_id)
    )).scalar_one_or_none()
    if prop is None:
        return []

    origin = _derive_origin(prop.gsc_site_url, prop.ga4_property_id)
    if not origin:
        logger.warning("Cannot derive origin for property", property_id=property_id)
        return []

    settings_row = (await db.execute(
        select(PropertySettings).where(PropertySettings.property_id == property_id)
    )).scalar_one_or_none()

    api_key: str | None = None
    try:
        cfg = get_settings()
        api_key = getattr(cfg, "crux_api_key", None) or getattr(cfg, "psi_api_key", None) or None
    except Exception:
        pass

    strategies: list[tuple[str, str]] = []
    mobile_on = settings_row.cwv_mobile_enabled if settings_row else True
    desktop_on = settings_row.cwv_desktop_enabled if settings_row else True
    if mobile_on:
        strategies.append(("mobile", "PHONE"))
    if desktop_on:
        strategies.append(("desktop", "DESKTOP"))

    client = CrUXClient(api_key=api_key)
    created: list[CWVOriginAudit] = []

    for strategy_name, form_factor in strategies:
        try:
            result = await client.get_origin(origin, form_factor)
        except Exception as exc:
            logger.error(
                "CrUX origin pull failed",
                property_id=property_id, origin=origin, error=str(exc),
            )
            continue

        row = CWVOriginAudit(
            property_id=property_id,
            origin=origin,
            strategy=strategy_name,
            audited_at=datetime.now(UTC),
            lcp_ms=result["lcp_ms"],
            inp_ms=result["inp_ms"],
            cls=result["cls"],
            fcp_ms=result["fcp_ms"],
            ttfb_ms=result["ttfb_ms"],
            cwv_status=result["cwv_status"],
            field_data_available=result["field_data_available"],
        )
        db.add(row)
        created.append(row)

    if created:
        await db.flush()

    logger.info(
        "CrUX origin pull complete",
        property_id=property_id, origin=origin, rows=len(created),
    )
    return created
