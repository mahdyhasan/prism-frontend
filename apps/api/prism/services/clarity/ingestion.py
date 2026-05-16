"""Microsoft Clarity nightly ingestion.

Pulls per-URL frustration metrics for the last 2 days (Clarity data can lag
~24 h) and upserts them into clarity_page_daily.  Called from the nightly
Celery task after the GA4 / GSC syncs complete.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.logging import logger
from prism.db.models.clarity import ClarityPageDaily
from prism.services.clarity.client import ClarityApiError, fetch_page_metrics


async def run_clarity_sync(
    property_id: int,
    project_id: str,
    api_token: str,
    db: AsyncSession,
    *,
    days_back: int = 2,
) -> dict[str, Any]:
    """Fetch `days_back` days of Clarity data and upsert into clarity_page_daily.

    Clarity data lags by ~24 h, so we pull the last 2 days on every nightly
    run to catch any delayed rows from the previous day.

    Returns a summary dict: {"rows_upserted": N, "pages": N, "errors": [...]}.
    """
    end = date.today() - timedelta(days=1)          # yesterday (latest available)
    start = end - timedelta(days=days_back - 1)

    errors: list[str] = []

    try:
        rows = await fetch_page_metrics(project_id, api_token, start, end)
    except ClarityApiError as exc:
        logger.error(
            "Clarity API error during sync",
            property_id=property_id,
            project_id=project_id,
            error=str(exc),
        )
        return {"rows_upserted": 0, "pages": 0, "errors": [str(exc)]}
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Unexpected error during Clarity sync",
            property_id=property_id,
            error=f"{type(exc).__name__}: {exc}",
        )
        return {"rows_upserted": 0, "pages": 0, "errors": [str(exc)]}

    if not rows:
        logger.info("Clarity sync: no rows returned", property_id=property_id)
        return {"rows_upserted": 0, "pages": 0, "errors": []}

    # Clarity returns data aggregated over the full requested date range, not
    # per-day.  We map every row to `end` (the most recent full day) so the
    # upsert key is (property_id, date=end, page_url).  When we add per-day
    # support (if Clarity adds a date dimension), we can expand this.
    upsert_rows = [
        {
            "property_id": property_id,
            "date": end,
            "page_url": r["page_url"],
            "session_count": r["session_count"],
            "dead_clicks": r["dead_clicks"],
            "rage_clicks": r["rage_clicks"],
            "quick_backs": r["quick_backs"],
            "scroll_depth_avg": r["scroll_depth_avg"],
        }
        for r in rows
    ]

    # Batch upsert in chunks of 500
    chunk_size = 500
    total_upserted = 0
    for i in range(0, len(upsert_rows), chunk_size):
        chunk = upsert_rows[i : i + chunk_size]
        stmt = mysql_insert(ClarityPageDaily).values(chunk)
        stmt = stmt.on_duplicate_key_update(
            session_count=stmt.inserted.session_count,
            dead_clicks=stmt.inserted.dead_clicks,
            rage_clicks=stmt.inserted.rage_clicks,
            quick_backs=stmt.inserted.quick_backs,
            scroll_depth_avg=stmt.inserted.scroll_depth_avg,
        )
        await db.execute(stmt)
        total_upserted += len(chunk)

    await db.commit()

    logger.info(
        "Clarity sync complete",
        property_id=property_id,
        project_id=project_id,
        pages=len(rows),
        rows_upserted=total_upserted,
    )
    return {
        "rows_upserted": total_upserted,
        "pages": len(rows),
        "errors": errors,
    }
