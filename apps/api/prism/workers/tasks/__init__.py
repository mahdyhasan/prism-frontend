from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, date, timedelta

from prism.workers.celery_app import celery_app
from prism.core.logging import logger


def _run(coro):  # type: ignore[no-untyped-def]
    """Run an async coroutine from a sync Celery task."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# GA4 tasks (unchanged)
# ---------------------------------------------------------------------------

@celery_app.task(name="prism.workers.tasks.run_ga4_sync_for_property", bind=True)
def run_ga4_sync_for_property(
    self,
    job_id: int,
    property_id: int,
    ga4_property_id: str,
    refresh_token: str | None = None,
    start_date: str = "",
    end_date: str = "",
) -> dict:
    from prism.services.sync_runner import run_ga4_sync
    return _run(run_ga4_sync(job_id, property_id, ga4_property_id, refresh_token, start_date, end_date))


@celery_app.task(name="prism.workers.tasks.sync_ga4_all_properties")
def sync_ga4_all_properties() -> dict:
    from prism.db.session import get_session_factory
    from prism.db.models.property import Property
    from prism.db.models.sync import SyncJob
    from prism.services.ga4.ingestion import run_daily_sync
    from sqlalchemy import select
    from datetime import UTC, datetime

    async def _run_all() -> dict:
        factory = get_session_factory()
        async with factory() as db:
            result = await db.execute(
                select(Property).where(
                    Property.status == "active",
                    Property.ga4_property_id.is_not(None),
                )
            )
            properties = result.scalars().all()

        # task_acks_late=True means tasks are re-queued if the worker crashes mid-execution.
        # Without this check, a crash after creating N SyncJob rows but before finishing
        # would produce duplicate rows on retry. The check makes the loop idempotent.
        today = date.today()
        dispatched = []
        for prop in properties:
            # Idempotency: skip dispatch if a pending/running job already exists for this property+date+source.
            async with factory() as db:
                existing = await db.execute(
                    select(SyncJob).where(
                        SyncJob.property_id == prop.id,
                        SyncJob.source == "ga4",
                        SyncJob.date == today,
                        SyncJob.status.in_(["pending", "running"]),
                    )
                )
                if existing.scalar_one_or_none():
                    logger.info("sync_job_already_exists", property_id=prop.id, date=today, source="ga4")
                    continue

            job = SyncJob(
                property_id=prop.id,
                source="ga4",
                kind="daily",
                status="pending",
                started_at=datetime.now(UTC),
            )
            async with factory() as db:
                db.add(job)
                await db.commit()
                await db.refresh(job)

            run_ga4_sync_for_property.delay(
                job_id=job.id,
                property_id=prop.id,
                ga4_property_id=prop.ga4_property_id,
                start_date=(date.today() - timedelta(days=3)).isoformat(),
                end_date=date.today().isoformat(),
            )
            dispatched.append(prop.id)

        logger.info("Dispatched GA4 daily syncs", count=len(dispatched))
        return {"dispatched": dispatched}

    return _run(_run_all())


# ---------------------------------------------------------------------------
# GSC tasks
# ---------------------------------------------------------------------------

@celery_app.task(name="prism.workers.tasks.sync_gsc_all_properties")
def sync_gsc_all_properties() -> dict:
    from prism.db.session import get_session_factory
    from prism.db.models.property import Property
    from prism.db.models.user import User
    from prism.core.security import decrypt_token
    from prism.config import get_settings
    from prism.services.gsc.ingestion import run_daily_sync
    from sqlalchemy import select

    async def _run_all() -> dict:
        settings = get_settings()
        factory = get_session_factory()

        async with factory() as db:
            result = await db.execute(
                select(Property).where(
                    Property.status == "active",
                    Property.gsc_site_url.is_not(None),
                )
            )
            properties = list(result.scalars().all())

        dispatched: list[int] = []
        failed: list[int] = []

        for prop in properties:
            try:
                async with factory() as db:
                    user_result = await db.execute(
                        select(User).where(User.id == prop.linked_by_user_id)
                    )
                    user = user_result.scalar_one_or_none()

                if user is None or not user.google_refresh_token_encrypted:
                    logger.warning(
                        "GSC sync skipped — no token",
                        property_id=prop.id,
                    )
                    failed.append(prop.id)
                    continue

                refresh_token = decrypt_token(
                    user.google_refresh_token_encrypted,
                    settings.prism_token_encryption_key,
                )

                await run_daily_sync(
                    property_id=prop.id,
                    site_url=prop.gsc_site_url,
                    refresh_token=refresh_token,
                )
                dispatched.append(prop.id)
                logger.info("GSC daily sync dispatched", property_id=prop.id)

            except Exception as exc:
                logger.error(
                    "GSC sync failed for property",
                    property_id=prop.id,
                    error=str(exc),
                )
                failed.append(prop.id)

        logger.info(
            "GSC daily sync batch complete",
            dispatched=len(dispatched),
            failed=len(failed),
        )
        return {"dispatched": dispatched, "failed": failed}

    return _run(_run_all())


@celery_app.task(name="prism.workers.tasks.run_gsc_sync_for_property", bind=True)
def run_gsc_sync_for_property(
    self,
    job_id: int,
    property_id: int,
    gsc_site_url: str,
    refresh_token: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    from prism.services.sync_runner import run_gsc_sync
    return _run(run_gsc_sync(job_id, property_id, gsc_site_url, refresh_token, start_date, end_date))


# ---------------------------------------------------------------------------
# Cross-source materialisation
# ---------------------------------------------------------------------------

def _normalize_url(url: str) -> str:
    """Normalize URL to just the path component for joining."""
    url = url.lower().strip()
    # Strip protocol
    url = re.sub(r'^https?://', '', url)
    # Strip domain if present (gsc pages have full URLs sometimes)
    url = re.sub(r'^[a-z0-9.-]+/', '/', url)
    # Strip query string and fragment
    url = url.split('?')[0].split('#')[0]
    # Normalize trailing slash (remove it)
    url = url.rstrip('/')
    if not url.startswith('/'):
        url = '/' + url
    return url[:500]  # enforce DB column limit


@celery_app.task(name="prism.workers.tasks.precompute_cross_source_views")
def precompute_cross_source_views() -> dict:
    from prism.db.session import get_session_factory
    from prism.db.models.property import Property
    from prism.db.models.ga4 import GA4LandingPagesDaily
    from prism.db.models.gsc import GSCPagesDaily
    from prism.db.models.cross_source import XSPageDaily
    from sqlalchemy import select, func
    from sqlalchemy.dialects.mysql import insert as mysql_insert

    cutoff = date.today() - timedelta(days=90)

    async def _materialise() -> dict:
        factory = get_session_factory()
        properties_processed = 0
        total_rows = 0

        async with factory() as db:
            result = await db.execute(
                select(Property).where(Property.status == "active")
            )
            properties = list(result.scalars().all())

        for prop in properties:
            try:
                async with factory() as db:
                    # --- GA4 landing pages ---
                    ga4_stmt = (
                        select(
                            GA4LandingPagesDaily.date,
                            GA4LandingPagesDaily.landing_page,
                            func.sum(GA4LandingPagesDaily.sessions).label("sessions"),
                            func.sum(GA4LandingPagesDaily.users).label("users"),
                            func.sum(GA4LandingPagesDaily.conversions).label("conversions"),
                            func.sum(GA4LandingPagesDaily.revenue).label("revenue"),
                            func.avg(GA4LandingPagesDaily.bounce_rate).label("bounce_rate"),
                        )
                        .where(
                            GA4LandingPagesDaily.property_id == prop.id,
                            GA4LandingPagesDaily.date >= cutoff,
                        )
                        .group_by(
                            GA4LandingPagesDaily.date,
                            GA4LandingPagesDaily.landing_page,
                        )
                    )
                    ga4_result = await db.execute(ga4_stmt)
                    ga4_rows = ga4_result.mappings().all()

                    # Build lookup: (date, normalized_url) -> ga4 metrics
                    ga4_map: dict[tuple, dict] = {}
                    for row in ga4_rows:
                        key = (row["date"], _normalize_url(row["landing_page"]))
                        ga4_map[key] = {
                            "sessions": int(row["sessions"] or 0),
                            "users": int(row["users"] or 0),
                            "conversions": int(row["conversions"] or 0),
                            "revenue": float(row["revenue"] or 0.0),
                            "bounce_rate": float(row["bounce_rate"] or 0.0),
                            "avg_session_duration": 0.0,  # not in LP table
                            "engaged_sessions": 0,
                        }

                    # --- GSC pages ---
                    gsc_stmt = (
                        select(
                            GSCPagesDaily.date,
                            GSCPagesDaily.page,
                            func.sum(GSCPagesDaily.clicks).label("clicks"),
                            func.sum(GSCPagesDaily.impressions).label("impressions"),
                            func.avg(GSCPagesDaily.ctr).label("ctr"),
                            func.avg(GSCPagesDaily.position).label("avg_position"),
                        )
                        .where(
                            GSCPagesDaily.property_id == prop.id,
                            GSCPagesDaily.date >= cutoff,
                        )
                        .group_by(
                            GSCPagesDaily.date,
                            GSCPagesDaily.page,
                        )
                    )
                    gsc_result = await db.execute(gsc_stmt)
                    gsc_rows = gsc_result.mappings().all()

                    gsc_map: dict[tuple, dict] = {}
                    for row in gsc_rows:
                        key = (row["date"], _normalize_url(row["page"]))
                        gsc_map[key] = {
                            "clicks": int(row["clicks"] or 0),
                            "impressions": int(row["impressions"] or 0),
                            "ctr": float(row["ctr"] or 0.0),
                            "avg_position": float(row["avg_position"] or 0.0),
                        }

                    # --- Join on (date, normalized_url) ---
                    all_keys = set(ga4_map.keys()) | set(gsc_map.keys())
                    if not all_keys:
                        continue

                    upsert_rows = []
                    for key in all_keys:
                        d, page_url = key
                        ga4 = ga4_map.get(key, {})
                        gsc = gsc_map.get(key, {})
                        upsert_rows.append({
                            "property_id": prop.id,
                            "date": d,
                            "page_url_normalized": page_url,
                            "sessions": ga4.get("sessions", 0),
                            "users": ga4.get("users", 0),
                            "engaged_sessions": ga4.get("engaged_sessions", 0),
                            "conversions": ga4.get("conversions", 0),
                            "revenue": ga4.get("revenue", 0.0),
                            "bounce_rate": ga4.get("bounce_rate", 0.0),
                            "avg_session_duration": ga4.get("avg_session_duration", 0.0),
                            "clicks": gsc.get("clicks", 0),
                            "impressions": gsc.get("impressions", 0),
                            "ctr": gsc.get("ctr", 0.0),
                            "avg_position": gsc.get("avg_position", 0.0),
                        })

                    # Batch upsert in chunks of 500
                    chunk_size = 500
                    for i in range(0, len(upsert_rows), chunk_size):
                        chunk = upsert_rows[i:i + chunk_size]
                        stmt = mysql_insert(XSPageDaily).values(chunk)
                        stmt = stmt.on_duplicate_key_update(
                            sessions=stmt.inserted.sessions,
                            users=stmt.inserted.users,
                            engaged_sessions=stmt.inserted.engaged_sessions,
                            conversions=stmt.inserted.conversions,
                            revenue=stmt.inserted.revenue,
                            bounce_rate=stmt.inserted.bounce_rate,
                            avg_session_duration=stmt.inserted.avg_session_duration,
                            clicks=stmt.inserted.clicks,
                            impressions=stmt.inserted.impressions,
                            ctr=stmt.inserted.ctr,
                            avg_position=stmt.inserted.avg_position,
                        )
                        await db.execute(stmt)
                    await db.commit()

                    prop_rows = len(upsert_rows)
                    total_rows += prop_rows
                    properties_processed += 1
                    logger.info(
                        "XS view materialised",
                        property_id=prop.id,
                        rows=prop_rows,
                    )

            except Exception as exc:
                logger.error(
                    "precompute_cross_source_views failed for property",
                    property_id=prop.id,
                    error=str(exc),
                )

        logger.info(
            "precompute_cross_source_views complete",
            properties_processed=properties_processed,
            total_rows=total_rows,
        )
        return {"properties_processed": properties_processed, "total_rows": total_rows}

    return _run(_materialise())


# ---------------------------------------------------------------------------
# Daily brief
# ---------------------------------------------------------------------------

@celery_app.task(name="prism.workers.tasks.generate_daily_brief")
def generate_daily_brief(property_id: int) -> dict:
    """Phase 2D: delegate to the shared async generator."""
    from prism.ai.brief_generator import generate_brief_for_property
    return _run(generate_brief_for_property(property_id))



@celery_app.task(name="prism.workers.tasks.generate_daily_brief_all")
def generate_daily_brief_all() -> dict:
    """Loop all active properties and dispatch generate_daily_brief for each."""
    from prism.db.session import get_session_factory
    from prism.db.models.property import Property
    from sqlalchemy import select

    async def _dispatch_all() -> dict:
        factory = get_session_factory()
        async with factory() as db:
            result = await db.execute(
                select(Property.id).where(Property.status == "active")
            )
            property_ids = [row[0] for row in result.all()]

        for pid in property_ids:
            generate_daily_brief.delay(pid)

        logger.info("Dispatched daily brief generation", count=len(property_ids))
        return {"dispatched": property_ids}

    return _run(_dispatch_all())


# ---------------------------------------------------------------------------
# Memory extraction
# ---------------------------------------------------------------------------

@celery_app.task(name="prism.workers.tasks.extract_memories_from_chat")
def extract_memories_from_chat(session_id: int, message_id: int) -> dict:
    """Extract durable memories from a completed chat exchange.

    Fires after the assistant message is committed so both turns are available.
    Uses Claude Haiku via memory_extractor.md — non-blocking, fire-and-forget.
    """
    from prism.services.ai.memory_extractor import extract_memories_async
    return _run(extract_memories_async(
        session_id=session_id,
        trigger_message_id=message_id,
    ))


# ---------------------------------------------------------------------------
# Pinned question runner
# ---------------------------------------------------------------------------

@celery_app.task(name="prism.workers.tasks.run_pinned_question", bind=True)
def run_pinned_question(self, pin_id: int, run_id: int) -> dict:
    """Execute a single pinned question via the agent loop and persist the answer."""
    from prism.services.ai.pinned_runner import run_pinned_question_async
    return _run(run_pinned_question_async(pin_id=pin_id, run_id=run_id))


@celery_app.task(name="prism.workers.tasks.rerun_all_due_pinned_questions")
def rerun_all_due_pinned_questions() -> dict:
    """Daily sweep: create run records and dispatch run_pinned_question for every
    active pin that hasn't run today.
    """
    from prism.services.ai.pinned_runner import rerun_all_due_async
    return _run(rerun_all_due_async())


# ---------------------------------------------------------------------------
# Microsoft Clarity nightly sync
# ---------------------------------------------------------------------------

@celery_app.task(name="prism.workers.tasks.sync_clarity_all_properties")
def sync_clarity_all_properties() -> dict:
    """Pull per-URL frustration metrics from the Clarity Data Export API for
    every active property that has both a project ID and an API token stored.
    """
    from prism.config import get_settings
    from prism.core.security import decrypt_token
    from prism.db.models.property import Property
    from prism.db.session import get_session_factory
    from prism.services.clarity.ingestion import run_clarity_sync
    from sqlalchemy import select

    async def _run_all() -> dict:
        settings = get_settings()
        factory = get_session_factory()

        async with factory() as db:
            result = await db.execute(
                select(Property).where(
                    Property.status == "active",
                    Property.clarity_project_id.is_not(None),
                    Property.clarity_api_token_encrypted.is_not(None),
                )
            )
            properties = list(result.scalars().all())

        logger.info("Clarity sync: found properties", count=len(properties))
        dispatched: list[int] = []
        failed: list[int] = []

        for prop in properties:
            try:
                api_token = decrypt_token(
                    prop.clarity_api_token_encrypted,
                    settings.prism_token_encryption_key,
                )
                async with factory() as db:
                    summary = await run_clarity_sync(
                        property_id=prop.id,
                        project_id=prop.clarity_project_id,
                        api_token=api_token,
                        db=db,
                    )
                logger.info(
                    "Clarity sync done",
                    property_id=prop.id,
                    **{k: v for k, v in summary.items() if k != "errors"},
                )
                if summary["errors"]:
                    logger.warning(
                        "Clarity sync errors",
                        property_id=prop.id,
                        errors=summary["errors"],
                    )
                    failed.append(prop.id)
                else:
                    dispatched.append(prop.id)
            except Exception as exc:
                logger.error(
                    "Clarity sync failed",
                    property_id=prop.id,
                    error=f"{type(exc).__name__}: {exc}",
                )
                failed.append(prop.id)

        return {"synced": dispatched, "failed": failed}

    return _run(_run_all())


# ---------------------------------------------------------------------------
# Nightly insights — anomaly + cross-source detectors for every active property
# ---------------------------------------------------------------------------

@celery_app.task(name="prism.workers.tasks.run_nightly_insights")
def run_nightly_insights() -> dict:
    """For every active property, run every insight detector and persist
    the findings. Content-hash dedupe means stable runs from day to day."""
    from prism.db.session import get_session_factory
    from prism.db.models.property import Property
    from prism.services.ai.insights import run_property_insights
    from sqlalchemy import select

    async def _run_all() -> dict:
        factory = get_session_factory()
        results: dict[str, dict[str, int]] = {}
        async with factory() as db:
            stmt = select(Property).where(Property.status == "active")
            prop_rows = (await db.execute(stmt)).scalars().all()

        for prop in prop_rows:
            try:
                async with factory() as db:
                    by_kind = await run_property_insights(
                        db, prop.id, prop.tenant_id,
                    )
                results[str(prop.id)] = by_kind
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Nightly insights failed for property",
                    property_id=prop.id,
                    error=f"{type(exc).__name__}: {exc}",
                )
                results[str(prop.id)] = {"error": 1}

        return {
            "properties_processed": len(prop_rows),
            "by_property": results,
        }

    return _run(_run_all())


# ---------------------------------------------------------------------------
# CWV (Core Web Vitals) tasks
# ---------------------------------------------------------------------------

@celery_app.task(name="prism.workers.tasks.daily_cwv_audit_top_pages")
def daily_cwv_audit_top_pages() -> dict:
    """Run PageSpeed Insights for the top-N pages of every active GA4 property
    that has a PSI API key configured (stored in PropertySettings or global config).
    """
    from prism.services.cwv.ingestion import run_cwv_audit_all_properties
    return _run(run_cwv_audit_all_properties())


@celery_app.task(name="prism.workers.tasks.daily_cwv_origin_pull")
def daily_cwv_origin_pull() -> dict:
    """Pull origin-level CrUX field data for all active properties."""
    from prism.services.cwv.ingestion import run_origin_pull_all_properties
    return _run(run_origin_pull_all_properties())


# ---------------------------------------------------------------------------
# Action lifecycle maintenance
# ---------------------------------------------------------------------------

@celery_app.task(name="prism.workers.tasks.cleanup_expired_actions")
def cleanup_expired_actions() -> dict:
    """Bulk-expire pending actions older than the 10-minute TTL.

    Runs every 5 minutes via beat.  Fast: single UPDATE WHERE status=pending AND
    created_at < cutoff.
    """
    from prism.db.session import get_session_factory
    from prism.services.actions.confirmation import expire_stale_actions

    async def _run_cleanup() -> dict:
        factory = get_session_factory()
        async with factory() as db:
            # expire_stale_actions already commits internally
            expired = await expire_stale_actions(db)
        return {"expired": expired}

    return _run(_run_cleanup())
