"""CWV ingestion orchestration.

Coordinates PSI and CrUX pulls across all active properties.
Called from Celery tasks in the nightly pipeline.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.logging import logger
from prism.db.models.cwv import CWVPageAudit, PropertySettings
from prism.db.models.ga4 import GA4LandingPagesDaily
from prism.db.models.property import Property
from prism.db.session import get_session_factory
from prism.services.cwv.crux import get_origin_cwv_for_property
from prism.services.cwv.psi import get_psi_audit_for_property


async def audit_top_pages_for_property(
    property_id: int,
    db: AsyncSession,
) -> dict:
    """Audit the top N pages for a property via PSI.

    Respects cwv_audit_enabled, cwv_audit_frequency_hours, and
    cwv_top_pages_count from PropertySettings. Creates one CWVPageAudit
    row per (page, strategy) that is stale or has never been audited.

    Returns a summary dict: {"audited": N, "skipped": M, "property_id": ...}
    """
    settings_row = (await db.execute(
        select(PropertySettings).where(PropertySettings.property_id == property_id)
    )).scalar_one_or_none()

    if settings_row and not settings_row.cwv_audit_enabled:
        return {"skipped": True, "reason": "cwv_audit_disabled", "property_id": property_id}

    top_n = settings_row.cwv_top_pages_count if settings_row else 25
    freq_hours = settings_row.cwv_audit_frequency_hours if settings_row else 24
    mobile_on = settings_row.cwv_mobile_enabled if settings_row else True
    desktop_on = settings_row.cwv_desktop_enabled if settings_row else True
    freshness_cutoff = datetime.now(UTC) - timedelta(hours=freq_hours)

    # Top pages by sessions over last 28 days
    cutoff_date = (datetime.now(UTC) - timedelta(days=28)).date()
    top_pages_result = await db.execute(
        select(
            GA4LandingPagesDaily.landing_page,
            func.sum(GA4LandingPagesDaily.sessions).label("sessions"),
        )
        .where(
            GA4LandingPagesDaily.property_id == property_id,
            GA4LandingPagesDaily.date >= cutoff_date,
        )
        .group_by(GA4LandingPagesDaily.landing_page)
        .order_by(desc("sessions"))
        .limit(top_n)
    )
    pages = [r["landing_page"] for r in top_pages_result.mappings().all()]

    strategies: list[str] = []
    if mobile_on:
        strategies.append("mobile")
    if desktop_on:
        strategies.append("desktop")

    audited = 0
    skipped = 0

    for page_url in pages:
        for strategy in strategies:
            # Check freshness
            existing = (await db.execute(
                select(CWVPageAudit)
                .where(
                    CWVPageAudit.property_id == property_id,
                    CWVPageAudit.audited_url == page_url,
                    CWVPageAudit.strategy == strategy,
                    CWVPageAudit.audited_at >= freshness_cutoff,
                )
                .limit(1)
            )).scalar_one_or_none()

            if existing is not None:
                skipped += 1
                continue

            try:
                await get_psi_audit_for_property(property_id, page_url, strategy, db)
                await db.commit()
                audited += 1
            except Exception as exc:
                await db.rollback()
                logger.error(
                    "PSI audit failed for page",
                    property_id=property_id, url=page_url,
                    strategy=strategy, error=str(exc),
                )

    return {"audited": audited, "skipped": skipped, "property_id": property_id}


async def run_cwv_audit_all_properties() -> dict:
    """Audit top pages for all active properties that have GA4 linked.

    Opens one DB session per property so a failure on one property
    does not abort the others.
    """
    factory = get_session_factory()
    async with factory() as db:
        props_result = await db.execute(
            select(Property).where(
                Property.status == "active",
                Property.ga4_property_id.is_not(None),
            )
        )
        properties = list(props_result.scalars().all())

    results: list[dict] = []
    for prop in properties:
        try:
            async with factory() as db:
                result = await audit_top_pages_for_property(prop.id, db)
                results.append(result)
        except Exception as exc:
            logger.error(
                "CWV audit failed for property",
                property_id=prop.id, error=str(exc),
            )
            results.append({"property_id": prop.id, "error": str(exc)})

    total_audited = sum(r.get("audited", 0) for r in results)
    logger.info(
        "CWV audit sweep complete",
        properties_processed=len(results),
        total_audited=total_audited,
    )
    return {"properties_processed": len(results), "total_audited": total_audited}


async def run_origin_pull_all_properties() -> dict:
    """Pull CrUX origin data for all active properties."""
    factory = get_session_factory()
    async with factory() as db:
        props_result = await db.execute(
            select(Property).where(Property.status == "active")
        )
        properties = list(props_result.scalars().all())

    total_rows = 0
    for prop in properties:
        try:
            async with factory() as db:
                rows = await get_origin_cwv_for_property(prop.id, db)
                await db.commit()
                total_rows += len(rows)
        except Exception as exc:
            logger.error(
                "CrUX origin pull failed for property",
                property_id=prop.id, error=str(exc),
            )

    logger.info("CrUX origin pull sweep complete", total_rows=total_rows)
    return {"properties_processed": len(properties), "total_rows": total_rows}
