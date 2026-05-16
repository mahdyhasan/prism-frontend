from __future__ import annotations

from datetime import UTC, datetime, date, timedelta

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.errors import ForbiddenError, NotFoundError
from prism.core.logging import logger
from prism.db.models.sync import AuditLog, SyncJob
from prism.db.models.property import PropertyMember
from prism.db.models.user import User
from prism.schemas.properties import TriggerSyncRequest
from prism.services.properties import get_property

# Jobs stuck in pending/running longer than this are considered orphaned
# (e.g. Celery worker crashed or was never started).
_STALE_MINUTES = 5


async def trigger_manual_sync(
    db: AsyncSession,
    property_id: int,
    user: User,
    req: TriggerSyncRequest,
    background_tasks: BackgroundTasks | None = None,
) -> SyncJob:
    prop = await get_property(db, property_id, user)

    if req.source == "ga4" and not prop.ga4_property_id:
        raise NotFoundError("This property has no GA4 property linked.")
    if req.source == "gsc" and not prop.gsc_site_url:
        raise NotFoundError("This property has no GSC site linked.")

    # Auto-expire orphaned jobs (no worker picked them up within _STALE_MINUTES).
    from sqlalchemy import select, update
    stale_cutoff = datetime.now(UTC) - timedelta(minutes=_STALE_MINUTES)
    await db.execute(
        update(SyncJob)
        .where(
            SyncJob.property_id == property_id,
            SyncJob.status.in_(["pending", "running"]),
            SyncJob.started_at < stale_cutoff,
        )
        .values(status="failed", error=f"auto-expired: no progress for {_STALE_MINUTES} minutes")
    )

    running = await db.execute(
        select(SyncJob).where(
            SyncJob.property_id == property_id,
            SyncJob.source == req.source,
            SyncJob.status.in_(["pending", "running"]),
        ).limit(1)
    )
    if running.scalar_one_or_none():
        from prism.core.errors import ConflictError
        raise ConflictError("A sync is already in progress for this property.")

    end_date = date.fromisoformat(req.end_date) if req.end_date else date.today()

    if req.start_date:
        start_date = date.fromisoformat(req.start_date)
        sync_kind = "manual"
    else:
        # Auto-window: incremental from last successful sync, with a 2-day
        # buffer to recapture late-arriving data (GA4 finalises rows up to
        # ~48h after the event). On first sync, fall back to a 12-month
        # backfill. Cap incremental at 12 months in case a user returns
        # after a long absence.
        _BACKFILL_DAYS = 365
        _OVERLAP_BUFFER_DAYS = 2

        last_done_result = await db.execute(
            select(SyncJob)
            .where(
                SyncJob.property_id == property_id,
                SyncJob.source == req.source,
                SyncJob.status == "done",
            )
            .order_by(SyncJob.finished_at.desc())
            .limit(1)
        )
        last_done = last_done_result.scalar_one_or_none()

        if last_done is None or last_done.finished_at is None:
            start_date = end_date - timedelta(days=_BACKFILL_DAYS)
            sync_kind = "backfill"
        else:
            last_date = last_done.finished_at.date()
            start_date = max(
                last_date - timedelta(days=_OVERLAP_BUFFER_DAYS),
                end_date - timedelta(days=_BACKFILL_DAYS),
            )
            sync_kind = "manual"

    job = SyncJob(
        property_id=property_id,
        source=req.source,
        kind=sync_kind,
        status="pending",
        started_at=datetime.now(UTC),
    )
    db.add(job)

    db.add(AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="sync.trigger",
        target_type="property",
        target_id=property_id,
        payload={"source": req.source, "start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
    ))

    await db.commit()
    await db.refresh(job)

    # ── Dispatch ──────────────────────────────────────────────────────────────
    # Use BackgroundTasks when available (runs in-process — works without Celery).
    # Falls back to Celery .delay() otherwise.
    if req.source == "gsc":
        from prism.config import get_settings
        from prism.core.security import decrypt_token

        settings = get_settings()
        refresh_token: str | None = None
        if user.google_refresh_token_encrypted:
            try:
                refresh_token = decrypt_token(
                    user.google_refresh_token_encrypted,
                    settings.prism_token_encryption_key,
                )
            except Exception:
                pass

        if not refresh_token:
            job.status = "failed"
            job.error = "No Google refresh token found for this user."
            await db.commit()
            from prism.core.errors import ConflictError
            raise ConflictError("Cannot sync GSC: no Google OAuth token available.")

        if background_tasks is not None:
            from prism.services.sync_runner import run_gsc_sync
            background_tasks.add_task(
                run_gsc_sync,
                job.id,
                property_id,
                prop.gsc_site_url,
                refresh_token,
                start_date.isoformat(),
                end_date.isoformat(),
            )
        else:
            from prism.workers.tasks import run_gsc_sync_for_property
            run_gsc_sync_for_property.delay(
                job_id=job.id,
                property_id=property_id,
                gsc_site_url=prop.gsc_site_url,
                refresh_token=refresh_token,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
            )
    else:
        # Fetch the user's Google refresh token — required for GA4 API calls
        from prism.config import get_settings
        from prism.core.security import decrypt_token

        settings = get_settings()
        ga4_refresh_token: str | None = None
        if user.google_refresh_token_encrypted:
            try:
                ga4_refresh_token = decrypt_token(
                    user.google_refresh_token_encrypted,
                    settings.prism_token_encryption_key,
                )
            except Exception:
                pass

        if not ga4_refresh_token and not settings.google_service_account_json:
            job.status = "failed"
            job.error = "No Google credentials available. Connect your Google account in Settings first."
            await db.commit()
            from prism.core.errors import ConflictError
            raise ConflictError("Cannot sync GA4: no Google OAuth token available. Connect your Google account in Settings.")

        if background_tasks is not None:
            from prism.services.sync_runner import run_ga4_sync
            background_tasks.add_task(
                run_ga4_sync,
                job.id,
                property_id,
                prop.ga4_property_id,
                ga4_refresh_token,
                start_date.isoformat(),
                end_date.isoformat(),
            )
        else:
            from prism.workers.tasks import run_ga4_sync_for_property
            run_ga4_sync_for_property.delay(
                job_id=job.id,
                property_id=property_id,
                ga4_property_id=prop.ga4_property_id,
                refresh_token=ga4_refresh_token,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
            )

    logger.info("Manual sync triggered", property_id=property_id, source=req.source, job_id=job.id)
    return job
