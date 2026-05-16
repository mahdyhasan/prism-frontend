"""
Async sync runners — callable from both Celery tasks (via asyncio.run) and
FastAPI BackgroundTasks (in-process, no worker needed).
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from prism.core.logging import logger
from prism.db.session import get_session_factory


async def run_ga4_sync(
    job_id: int,
    property_id: int,
    ga4_property_id: str,
    refresh_token: str | None,
    start_date: str,
    end_date: str,
) -> dict:
    from sqlalchemy import select
    from prism.db.models.sync import SyncJob
    from prism.services.ga4.ingestion import ingest_property

    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(select(SyncJob).where(SyncJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            return {"error": "job not found"}

        job.status = "running"
        job.started_at = datetime.now(UTC)
        await db.commit()

        try:
            rows = await ingest_property(
                property_id=property_id,
                ga4_property_id=ga4_property_id,
                start_date=date.fromisoformat(start_date),
                end_date=date.fromisoformat(end_date),
                refresh_token=refresh_token,
            )
            job.status = "done"
            job.rows_pulled = rows
            job.finished_at = datetime.now(UTC)
            await db.commit()
            logger.info("GA4 sync done", job_id=job_id, rows=rows)
            return {"status": "done", "rows": rows}
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)[:4096]
            job.finished_at = datetime.now(UTC)
            await db.commit()
            logger.error("GA4 sync failed", job_id=job_id, error=str(exc))
            return {"status": "failed", "error": str(exc)}


async def run_gsc_sync(
    job_id: int,
    property_id: int,
    gsc_site_url: str,
    refresh_token: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    from sqlalchemy import select
    from prism.db.models.sync import SyncJob
    from prism.services.gsc.ingestion import ingest_property, run_daily_sync

    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(select(SyncJob).where(SyncJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            return {"error": "job not found"}

        job.status = "running"
        job.started_at = datetime.now(UTC)
        await db.commit()

        try:
            if start_date and end_date:
                rows = await ingest_property(
                    property_id=property_id,
                    gsc_site_url=gsc_site_url,
                    start_date=date.fromisoformat(start_date),
                    end_date=date.fromisoformat(end_date),
                    refresh_token=refresh_token,
                )
            else:
                # No explicit range — use the standard 3-day lookback window.
                rows = await run_daily_sync(
                    property_id=property_id,
                    gsc_site_url=gsc_site_url,
                    refresh_token=refresh_token,
                )
            job.status = "done"
            job.rows_pulled = rows
            job.finished_at = datetime.now(UTC)
            await db.commit()
            logger.info("GSC sync done", job_id=job_id, rows=rows)
            return {"status": "done", "rows": rows}
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)[:4096]
            job.finished_at = datetime.now(UTC)
            await db.commit()
            logger.error("GSC sync failed", job_id=job_id, error=str(exc))
            return {"status": "failed", "error": str(exc)}
