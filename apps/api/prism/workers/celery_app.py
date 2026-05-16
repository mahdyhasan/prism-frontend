from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from prism.config import get_settings


def create_celery_app() -> Celery:
    settings = get_settings()

    app = Celery(
        "prism",
        broker=settings.prism_redis_url,
        backend=settings.prism_redis_url,
        include=["prism.workers.tasks"],
    )

    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        beat_schedule={
            # Microsoft Clarity nightly sync — 03:30 UTC (before GA4, after midnight)
            "clarity-nightly-sync": {
                "task": "prism.workers.tasks.sync_clarity_all_properties",
                "schedule": crontab(hour=3, minute=30),
            },
            # GA4 daily sync — 04:00 UTC (tasks handle per-property timezone offset)
            "ga4-daily-sync": {
                "task": "prism.workers.tasks.sync_ga4_all_properties",
                "schedule": crontab(hour=4, minute=0),
            },
            # GSC daily sync — 05:00 UTC
            "gsc-daily-sync": {
                "task": "prism.workers.tasks.sync_gsc_all_properties",
                "schedule": crontab(hour=5, minute=0),
            },
            # Cross-source materialisation — 06:00 UTC (after syncs complete)
            "precompute-cross-source-views": {
                "task": "prism.workers.tasks.precompute_cross_source_views",
                "schedule": crontab(hour=6, minute=0),
            },
            # Daily brief generation — 07:00 UTC (after materialisation)
            "generate-daily-brief-all": {
                "task": "prism.workers.tasks.generate_daily_brief_all",
                "schedule": crontab(hour=7, minute=0),
            },
            # Nightly insights job — kept for backward compatibility
            "nightly-insights": {
                "task": "prism.workers.tasks.run_nightly_insights",
                "schedule": crontab(hour=6, minute=0),
            },
            # Pinned question re-run sweep — 08:00 UTC (after briefs, after materialization)
            "rerun-pinned-questions": {
                "task": "prism.workers.tasks.rerun_all_due_pinned_questions",
                "schedule": crontab(hour=8, minute=0),
            },
            # CWV top-pages audit — 03:00 UTC (low-traffic window, before GA4 sync)
            "cwv-audit-top-pages": {
                "task": "prism.workers.tasks.daily_cwv_audit_top_pages",
                "schedule": crontab(hour=3, minute=0),
            },
            # CWV origin pull (CrUX) — 04:15 UTC
            "cwv-origin-pull": {
                "task": "prism.workers.tasks.daily_cwv_origin_pull",
                "schedule": crontab(hour=4, minute=15),
            },
            # Expire stale pending actions — every 5 minutes
            "cleanup-expired-actions": {
                "task": "prism.workers.tasks.cleanup_expired_actions",
                "schedule": crontab(minute="*/5"),
            },
        },
    )

    return app


celery_app = create_celery_app()
