"""PageSpeed Insights API client.

Provides an async client for the PSI v5 API and a helper that ties
audit results to a specific PRISM property.
"""
from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.logging import logger
from prism.db.models.cwv import CWVPageAudit, PropertySettings

_PSI_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
_TIMEOUT = 60.0  # seconds
_RATE_LIMIT_SLEEP = 1.1  # seconds between PSI calls to respect quota


def _normalize_url(url: str) -> str:
    url = url.lower().strip()
    url = re.sub(r"^https?://", "", url)
    url = re.sub(r"^[a-z0-9.-]+/", "/", url)
    url = url.split("?")[0].split("#")[0]
    url = url.rstrip("/")
    if not url.startswith("/"):
        url = "/" + url
    return url[:500]


def _cwv_status(lcp_ms: int | None, inp_ms: int | None, cls: float | None) -> str:
    """Derive composite CWV status from LCP, INP, CLS thresholds."""
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


def _parse_audit_value(audits: dict, key: str) -> float | None:
    audit = audits.get(key, {})
    val = audit.get("numericValue")
    if val is None:
        return None
    return float(val)


def _extract_opportunities(audits: dict) -> list[dict]:
    """Return top 5 PSI opportunities sorted by estimated savings."""
    opps = []
    for audit_id, audit in audits.items():
        if audit.get("details", {}).get("type") == "opportunity":
            savings = audit.get("details", {}).get("overallSavingsMs", 0) or 0
            opps.append({
                "id": audit_id,
                "title": audit.get("title", ""),
                "description": audit.get("description", "")[:200],
                "savings_ms": int(savings),
                "score": audit.get("score"),
            })
    opps.sort(key=lambda x: x["savings_ms"], reverse=True)
    return opps[:5]


def _extract_diagnostics(audits: dict) -> list[dict]:
    """Return top 5 PSI diagnostics (non-opportunity, non-passing)."""
    diags = []
    for audit_id, audit in audits.items():
        if (
            audit.get("details", {}).get("type") not in ("opportunity", None)
            and audit.get("score") is not None
            and float(audit.get("score", 1)) < 1.0
        ):
            diags.append({
                "id": audit_id,
                "title": audit.get("title", ""),
                "score": audit.get("score"),
            })
    return diags[:5]


class PSIClient:
    """Async client for the PageSpeed Insights v5 API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    async def audit(self, url: str, strategy: str = "mobile") -> dict[str, Any]:
        """Run a PSI audit for the given URL and strategy.

        Returns a structured dict ready to be stored in CWVPageAudit.
        Raises RuntimeError on non-200 responses.
        """
        params: dict[str, str] = {
            "url": url,
            "strategy": strategy.upper(),
            "category": "PERFORMANCE",
        }
        if self._api_key:
            params["key"] = self._api_key

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(_PSI_URL, params=params)
        finally:
            # Rate-limit regardless of success or failure
            await asyncio.sleep(_RATE_LIMIT_SLEEP)

        if response.status_code != 200:
            raise RuntimeError(
                f"PSI API returned {response.status_code} for {url}: {response.text[:200]}"
            )

        data = response.json()
        lhr = data.get("lighthouseResult", {})
        audits = lhr.get("audits", {})
        loading_exp = data.get("loadingExperience", {})

        lcp_ms = _parse_audit_value(audits, "largest-contentful-paint")
        lcp_ms = int(lcp_ms) if lcp_ms is not None else None

        inp_ms = _parse_audit_value(audits, "interaction-to-next-paint")
        inp_ms = int(inp_ms) if inp_ms is not None else None

        cls_val = _parse_audit_value(audits, "cumulative-layout-shift")

        fcp_ms = _parse_audit_value(audits, "first-contentful-paint")
        fcp_ms = int(fcp_ms) if fcp_ms is not None else None

        ttfb_ms = _parse_audit_value(audits, "server-response-time")
        ttfb_ms = int(ttfb_ms) if ttfb_ms is not None else None

        perf_score_raw = lhr.get("categories", {}).get("performance", {}).get("score")
        perf_score = int(float(perf_score_raw) * 100) if perf_score_raw is not None else None

        field_data_available = bool(loading_exp.get("metrics"))
        lab_data_available = bool(lhr)

        return {
            "url": url,
            "strategy": strategy.lower(),
            "lcp_ms": lcp_ms,
            "inp_ms": inp_ms,
            "cls": round(float(cls_val), 4) if cls_val is not None else None,
            "fcp_ms": fcp_ms,
            "ttfb_ms": ttfb_ms,
            "lighthouse_performance_score": perf_score,
            "field_data_available": field_data_available,
            "lab_data_available": lab_data_available,
            "cwv_status": _cwv_status(lcp_ms, inp_ms, cls_val),
            "opportunities": _extract_opportunities(audits),
            "diagnostics": _extract_diagnostics(audits),
        }


async def get_psi_audit_for_property(
    property_id: int,
    url: str,
    strategy: str,
    db: AsyncSession,
) -> CWVPageAudit:
    """Run a PSI audit for a property's page and persist to DB.

    Resolves the API key from property settings (falls back to no key).
    Calls db.flush() so the caller controls the commit boundary.
    """
    from prism.config import get_settings

    settings_row = (await db.execute(
        select(PropertySettings).where(PropertySettings.property_id == property_id)
    )).scalar_one_or_none()

    api_key: str | None = None
    if settings_row and settings_row.psi_api_key_encrypted:
        try:
            from prism.core.security import decrypt_token
            cfg = get_settings()
            api_key = decrypt_token(
                settings_row.psi_api_key_encrypted, cfg.prism_token_encryption_key
            )
        except Exception as exc:
            logger.warning(
                "Could not decrypt PSI API key",
                property_id=property_id, error=str(exc),
            )

    # Fall back to global env key
    if not api_key:
        cfg = get_settings()
        api_key = getattr(cfg, "psi_api_key", None) or None

    result = await PSIClient(api_key=api_key).audit(url, strategy)

    audit = CWVPageAudit(
        property_id=property_id,
        audited_url=url,
        url_normalized=_normalize_url(url),
        strategy=result["strategy"],
        audited_at=datetime.now(UTC),
        source="psi",
        lcp_ms=result["lcp_ms"],
        inp_ms=result["inp_ms"],
        cls=result["cls"],
        fcp_ms=result["fcp_ms"],
        ttfb_ms=result["ttfb_ms"],
        lighthouse_performance_score=result["lighthouse_performance_score"],
        field_data_available=result["field_data_available"],
        lab_data_available=result["lab_data_available"],
        cwv_status=result["cwv_status"],
        opportunities=result["opportunities"],
        diagnostics=result["diagnostics"],
    )
    db.add(audit)
    await db.flush()
    logger.info(
        "PSI audit complete",
        property_id=property_id,
        url=url,
        strategy=strategy,
        cwv_status=result["cwv_status"],
    )
    return audit
