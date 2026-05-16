"""Action agent tools — create pending actions for the user to confirm.

These tools do NOT execute immediately. They create an ActionExecution row with
status="pending_confirmation" and return a structured confirmation request.
The frontend renders a confirmation card; on approval the user calls
POST /api/v1/actions/{id}/confirm.

Non-destructive tools (gsc_inspect_url, run_psi_audit) execute immediately
because they are read-only / write-only-to-PRISM (no external mutation).

Available tools:
  gsc_submit_sitemap  — submit a sitemap URL to Google Search Console
  gsc_delete_sitemap  — remove a sitemap from GSC (destructive — requires confirm)
  gsc_inspect_url     — URL inspection via GSC API (read-only, no confirm needed)
  run_psi_audit       — trigger a fresh PSI audit and store results in PRISM
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.logging import logger


# ── Schemas ───────────────────────────────────────────────────────────────────

class GSCSubmitSitemapInput(BaseModel):
    property_id: int
    sitemap_url: str = Field(..., description="Full URL of the sitemap, e.g. https://example.com/sitemap.xml")


class GSCDeleteSitemapInput(BaseModel):
    property_id: int
    sitemap_url: str = Field(..., description="Full URL of the sitemap to delete")


class GSCInspectURLInput(BaseModel):
    property_id: int
    url: str = Field(..., description="Full URL to inspect")


class RunPSIAuditInput(BaseModel):
    property_id: int
    url: str = Field(..., description="Full URL or normalized path to audit")
    strategy: Literal["mobile", "desktop"] = "mobile"


# ── Tool functions ─────────────────────────────────────────────────────────────

async def gsc_submit_sitemap(
    inp: GSCSubmitSitemapInput,
    db: AsyncSession,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Create a pending action to submit a sitemap to Google Search Console.

    user_id is injected by dispatch_tool from the authenticated session — never
    taken from LLM tool input.
    """
    from prism.services.actions.confirmation import create_pending_action
    from prism.db.models.property import Property
    from sqlalchemy import select

    if user_id is None:
        return {"error": "Authenticated user required to create an action."}

    prop_result = await db.execute(select(Property).where(Property.id == inp.property_id))
    prop = prop_result.scalar_one_or_none()
    if prop is None:
        return {"error": "Property not found."}
    if not prop.gsc_site_url:
        return {"error": "This property has no linked Google Search Console site."}

    # Validate sitemap URL is within the property's GSC domain
    gsc_domain = prop.gsc_site_url.rstrip("/")
    if not inp.sitemap_url.startswith(gsc_domain.replace("sc-domain:", "https://").replace("sc-domain:", "http://")):
        # Best-effort domain check (sc-domain: prefixed sites use domain-level matching)
        parsed_gsc = gsc_domain.lstrip("sc-domain:").lstrip("https://").lstrip("http://").rstrip("/")
        if parsed_gsc and parsed_gsc not in inp.sitemap_url:
            return {
                "error": (
                    f"Sitemap URL does not appear to belong to this property's GSC domain ({parsed_gsc}). "
                    "Refusing to submit a sitemap for a different domain."
                )
            }

    action = await create_pending_action(
        db,
        tenant_id=prop.tenant_id,
        property_id=inp.property_id,
        user_id=user_id,
        tool_name="gsc_submit_sitemap",
        tool_input={"sitemap_url": inp.sitemap_url},
        requires_confirmation=True,
    )
    await db.commit()

    return {
        "status": "pending_confirmation",
        "action_id": action.id,
        "tool_name": "gsc_submit_sitemap",
        "description": f"Submit sitemap {inp.sitemap_url} to Google Search Console",
        "requires_confirmation": True,
        "message": (
            "This action requires your confirmation before it is sent to Google. "
            f"Action ID: {action.id}. Please confirm or cancel in the Actions panel."
        ),
    }


async def gsc_delete_sitemap(
    inp: GSCDeleteSitemapInput,
    db: AsyncSession,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Create a pending action to DELETE a sitemap from Google Search Console.

    Destructive — requires explicit user confirmation.
    user_id injected by dispatch_tool, never from LLM input.
    """
    from prism.services.actions.confirmation import create_pending_action
    from prism.db.models.property import Property
    from sqlalchemy import select

    if user_id is None:
        return {"error": "Authenticated user required to create an action."}

    prop_result = await db.execute(select(Property).where(Property.id == inp.property_id))
    prop = prop_result.scalar_one_or_none()
    if prop is None:
        return {"error": "Property not found."}
    if not prop.gsc_site_url:
        return {"error": "This property has no linked Google Search Console site."}

    action = await create_pending_action(
        db,
        tenant_id=prop.tenant_id,
        property_id=inp.property_id,
        user_id=user_id,
        tool_name="gsc_delete_sitemap",
        tool_input={"sitemap_url": inp.sitemap_url},
        requires_confirmation=True,
    )
    await db.commit()

    return {
        "status": "pending_confirmation",
        "action_id": action.id,
        "tool_name": "gsc_delete_sitemap",
        "description": f"Delete sitemap {inp.sitemap_url} from Google Search Console",
        "requires_confirmation": True,
        "destructive": True,
        "message": (
            "WARNING: This will permanently remove the sitemap from Google Search Console. "
            f"Action ID: {action.id}. Review carefully before confirming."
        ),
    }


async def gsc_inspect_url(inp: GSCInspectURLInput, db: AsyncSession) -> dict[str, Any]:
    """Inspect a URL via the Google Search Console URL Inspection API.

    Read-only — executes immediately without confirmation.
    Returns indexing status, crawl date, coverage state, and enhancements.
    """
    from prism.db.models.property import Property
    from prism.db.models.user import User
    from prism.core.security import decrypt_token
    from prism.config import get_settings
    from sqlalchemy import select

    settings = get_settings()

    prop_result = await db.execute(select(Property).where(Property.id == inp.property_id))
    prop = prop_result.scalar_one_or_none()
    if prop is None:
        return {"error": "Property not found."}
    if not prop.gsc_site_url:
        return {"error": "This property has no linked Google Search Console site."}

    # Fetch the linked user's refresh token
    user_result = await db.execute(
        select(User).where(User.id == prop.linked_by_user_id)
    )
    user = user_result.scalar_one_or_none()
    if user is None or not user.google_refresh_token_encrypted:
        return {"error": "No Google OAuth token found for this property."}

    try:
        refresh_token = decrypt_token(
            user.google_refresh_token_encrypted,
            settings.prism_token_encryption_key,
        )
    except Exception as exc:
        return {"error": f"Failed to decrypt Google token: {exc}"}

    # Call URL inspection API
    try:
        from prism.services.gsc.url_inspection import inspect_url
        data = await inspect_url(
            site_url=prop.gsc_site_url,
            inspect_url=inp.url,
            refresh_token=refresh_token,
        )
        return {"found": True, **data}
    except NotImplementedError:
        return {
            "found": False,
            "message": "URL inspection service not yet available. Use Google Search Console directly.",
            "gsc_url": f"https://search.google.com/search-console/inspect?resource_id={prop.gsc_site_url}&id={inp.url}",
        }
    except Exception as exc:
        logger.warning("GSC URL inspection failed", url=inp.url, error=str(exc))
        return {"error": f"URL inspection failed: {exc}"}


async def run_psi_audit(
    inp: RunPSIAuditInput,
    db: AsyncSession,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Trigger a fresh PageSpeed Insights audit for a specific URL.

    Writes results to cwv_page_audits and returns the metrics immediately.
    No confirmation required — PSI is read-only against the live site.
    user_id is accepted but not used (required by dispatch_tool for user-scoped tools).
    """
    from prism.services.cwv.psi import get_psi_audit_for_property

    try:
        audit = await get_psi_audit_for_property(
            property_id=inp.property_id,
            url=inp.url,
            strategy=inp.strategy,
            db=db,
        )
        return {
            "success": True,
            "url": audit.url_normalized,
            "strategy": audit.strategy,
            "cwv_status": audit.cwv_status,
            "lcp_ms": audit.lcp_ms,
            "inp_ms": audit.inp_ms,
            "cls": audit.cls,
            "fcp_ms": audit.fcp_ms,
            "ttfb_ms": audit.ttfb_ms,
            "lighthouse_performance_score": audit.lighthouse_performance_score,
            "opportunities": audit.opportunities or [],
        }
    except Exception as exc:
        logger.error("PSI audit failed", property_id=inp.property_id, url=inp.url, error=str(exc))
        return {"error": f"PSI audit failed: {exc}"}
