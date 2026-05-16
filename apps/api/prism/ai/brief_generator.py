"""
Async brief generation logic — callable from both the FastAPI route (via
BackgroundTasks) and the Celery task (via asyncio.run).
"""
from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from anthropic import AsyncAnthropic
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401

from prism.ai.client import NARRATIVE_MODEL
from prism.config import get_settings
from prism.core.logging import logger
from prism.db.session import get_session_factory


def _pct_delta(current: float, prior: float) -> float | None:
    if not prior:
        return None
    return round((current - prior) / prior * 100, 1)


async def generate_brief_for_property(property_id: int) -> dict:
    """
    Gather analytics inputs, call Claude with the daily_brief.md system prompt,
    and persist the result in the daily_briefs table.

    Returns {"status": "done"} on success or {"error": "..."} on failure.
    """
    from prism.db.models.brief import DailyBrief
    from prism.db.models.chat import ChatMemory, PinnedQuestion
    from prism.db.models.cross_source import XSPageDaily
    from prism.db.models.ga4 import GA4DailyMetrics, GA4LandingPagesDaily
    from prism.db.models.gsc import GSCQueriesDaily
    from prism.db.models.property import Property

    settings = get_settings()
    factory = get_session_factory()
    today = date.today()
    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=8)  # 7 days before yesterday

    try:
        async with factory() as db:
            # ── Property ──────────────────────────────────────────────────────
            prop = (await db.execute(
                select(Property).where(Property.id == property_id)
            )).scalar_one_or_none()
            if prop is None:
                return {"error": f"property {property_id} not found"}

            # ── GA4 yesterday totals ───────────────────────────────────────────
            ga4_yest = (await db.execute(
                select(
                    func.sum(GA4DailyMetrics.sessions).label("sessions"),
                    func.sum(GA4DailyMetrics.users).label("users"),
                    func.sum(GA4DailyMetrics.conversions).label("conversions"),
                    func.sum(GA4DailyMetrics.total_revenue).label("revenue"),
                    func.avg(GA4DailyMetrics.engagement_rate).label("engagement_rate"),
                ).where(
                    GA4DailyMetrics.property_id == property_id,
                    GA4DailyMetrics.date == yesterday,
                )
            )).mappings().first() or {}

            # ── GA4 prior 7-day average ────────────────────────────────────────
            ga4_7d = (await db.execute(
                select(
                    func.avg(GA4DailyMetrics.sessions).label("avg_sessions"),
                    func.avg(GA4DailyMetrics.users).label("avg_users"),
                    func.avg(GA4DailyMetrics.conversions).label("avg_conversions"),
                    func.avg(GA4DailyMetrics.total_revenue).label("avg_revenue"),
                ).where(
                    GA4DailyMetrics.property_id == property_id,
                    GA4DailyMetrics.date >= week_start,
                    GA4DailyMetrics.date < yesterday,
                )
            )).mappings().first() or {}

            # ── GSC yesterday totals ───────────────────────────────────────────
            gsc_yest = (await db.execute(
                select(
                    func.sum(GSCQueriesDaily.clicks).label("clicks"),
                    func.sum(GSCQueriesDaily.impressions).label("impressions"),
                    func.avg(GSCQueriesDaily.ctr).label("ctr"),
                    func.avg(GSCQueriesDaily.position).label("avg_position"),
                ).where(
                    GSCQueriesDaily.property_id == property_id,
                    GSCQueriesDaily.date == yesterday,
                )
            )).mappings().first() or {}

            # ── GSC prior 7-day average ────────────────────────────────────────
            gsc_7d = (await db.execute(
                select(
                    func.avg(GSCQueriesDaily.clicks).label("avg_clicks"),
                    func.avg(GSCQueriesDaily.impressions).label("avg_impressions"),
                    func.avg(GSCQueriesDaily.ctr).label("avg_ctr"),
                    func.avg(GSCQueriesDaily.position).label("avg_position"),
                ).where(
                    GSCQueriesDaily.property_id == property_id,
                    GSCQueriesDaily.date >= week_start,
                    GSCQueriesDaily.date < yesterday,
                )
            )).mappings().first() or {}

            # ── Top landing pages last 7d ──────────────────────────────────────
            top_pages = (await db.execute(
                select(
                    GA4LandingPagesDaily.landing_page,
                    func.sum(GA4LandingPagesDaily.sessions).label("sessions"),
                    func.sum(GA4LandingPagesDaily.conversions).label("conversions"),
                ).where(
                    GA4LandingPagesDaily.property_id == property_id,
                    GA4LandingPagesDaily.date >= (today - timedelta(days=7)),
                ).group_by(GA4LandingPagesDaily.landing_page)
                .order_by(desc("sessions"))
                .limit(10)
            )).mappings().all()

            # ── Top queries last 7d ────────────────────────────────────────────
            top_queries = (await db.execute(
                select(
                    GSCQueriesDaily.query,
                    func.sum(GSCQueriesDaily.clicks).label("clicks"),
                    func.sum(GSCQueriesDaily.impressions).label("impressions"),
                    func.avg(GSCQueriesDaily.position).label("avg_position"),
                ).where(
                    GSCQueriesDaily.property_id == property_id,
                    GSCQueriesDaily.date >= (today - timedelta(days=7)),
                ).group_by(GSCQueriesDaily.query)
                .order_by(desc("clicks"))
                .limit(15)
            )).mappings().all()

            # ── SERP opportunities (xs_page_daily) ────────────────────────────
            serp_rows = (await db.execute(
                select(
                    XSPageDaily.page_url_normalized,
                    func.avg(XSPageDaily.avg_position).label("avg_position"),
                    func.sum(XSPageDaily.impressions).label("impressions"),
                    func.sum(XSPageDaily.clicks).label("clicks"),
                    func.sum(XSPageDaily.sessions).label("sessions"),
                ).where(
                    XSPageDaily.property_id == property_id,
                    XSPageDaily.date >= (today - timedelta(days=14)),
                    XSPageDaily.avg_position.between(5, 20),
                    XSPageDaily.impressions > 50,
                ).group_by(XSPageDaily.page_url_normalized)
                .order_by(desc("impressions"))
                .limit(10)
            )).mappings().all()

            # ── Prior brief (yesterday) ────────────────────────────────────────
            prior_row = (await db.execute(
                select(DailyBrief).where(
                    DailyBrief.property_id == property_id,
                    DailyBrief.brief_date == yesterday,
                )
            )).scalar_one_or_none()
            prior_data: dict | None = None
            if prior_row and prior_row.brief_json:
                try:
                    prior_data = json.loads(prior_row.brief_json)
                except Exception:
                    pass

            # ── Memories ──────────────────────────────────────────────────────
            memories = [
                {"kind": r.kind, "text": r.text}
                for r in (await db.execute(
                    select(ChatMemory.kind, ChatMemory.text).where(
                        ChatMemory.property_id == property_id,
                        ChatMemory.status == "active",
                    ).limit(12)
                )).all()
            ]

            # ── Pinned questions ───────────────────────────────────────────────
            pinned_titles = [
                r.title
                for r in (await db.execute(
                    select(PinnedQuestion.title).where(
                        PinnedQuestion.property_id == property_id,
                    ).limit(10)
                )).all()
            ]

        # ── Compute deltas ─────────────────────────────────────────────────────
        y_sessions   = int(ga4_yest.get("sessions") or 0)
        avg_sessions = float(ga4_7d.get("avg_sessions") or 0)
        y_users      = int(ga4_yest.get("users") or 0)
        avg_users    = float(ga4_7d.get("avg_users") or 0)
        y_conv       = int(ga4_yest.get("conversions") or 0)
        avg_conv     = float(ga4_7d.get("avg_conversions") or 0)
        y_rev        = float(ga4_yest.get("revenue") or 0)
        avg_rev      = float(ga4_7d.get("avg_revenue") or 0)

        y_clicks     = int(gsc_yest.get("clicks") or 0)
        avg_clicks   = float(gsc_7d.get("avg_clicks") or 0)
        y_impr       = int(gsc_yest.get("impressions") or 0)
        avg_impr     = float(gsc_7d.get("avg_impressions") or 0)
        y_ctr        = float(gsc_yest.get("ctr") or 0)
        avg_ctr      = float(gsc_7d.get("avg_ctr") or 0)
        y_pos        = float(gsc_yest.get("avg_position") or 0)
        avg_pos      = float(gsc_7d.get("avg_position") or 0)

        # Cross-platform date label (%-d is Linux-only)
        day_label = f"{yesterday.strftime('%A, %B')} {yesterday.day}, {yesterday.year}"

        payload = {
            "property": {
                "name": prop.display_name,
                "domain": prop.gsc_site_url or prop.ga4_property_id or str(property_id),
            },
            "period": {
                "date": yesterday.isoformat(),
                "label": day_label,
                "comparing_to": "prior 7-day average",
            },
            "headline_metrics": {
                "ga4": {
                    "sessions": y_sessions,
                    "sessions_vs_7d_avg_pct": _pct_delta(y_sessions, avg_sessions),
                    "users": y_users,
                    "users_vs_7d_avg_pct": _pct_delta(y_users, avg_users),
                    "conversions": y_conv,
                    "conversions_vs_7d_avg_pct": _pct_delta(y_conv, avg_conv),
                    "revenue": round(y_rev, 2),
                    "revenue_vs_7d_avg_pct": _pct_delta(y_rev, avg_rev),
                    "engagement_rate_pct": round(
                        float(ga4_yest.get("engagement_rate") or 0) * 100, 1
                    ),
                },
                "gsc": {
                    "clicks": y_clicks,
                    "clicks_vs_7d_avg_pct": _pct_delta(y_clicks, avg_clicks),
                    "impressions": y_impr,
                    "impressions_vs_7d_avg_pct": _pct_delta(y_impr, avg_impr),
                    "ctr_pct": round(y_ctr * 100, 2),
                    "ctr_vs_7d_avg_pct": _pct_delta(y_ctr, avg_ctr),
                    "avg_position": round(y_pos, 1),
                    "avg_position_vs_7d_avg": round(y_pos - avg_pos, 1) if avg_pos else None,
                },
            },
            "top_pages_7d": [
                {
                    "page": r["landing_page"],
                    "sessions": int(r["sessions"] or 0),
                    "conversions": int(r["conversions"] or 0),
                }
                for r in top_pages
            ],
            "top_queries_7d": [
                {
                    "query": r["query"],
                    "clicks": int(r["clicks"] or 0),
                    "impressions": int(r["impressions"] or 0),
                    "avg_position": round(float(r["avg_position"] or 0), 1),
                }
                for r in top_queries
            ],
            "cross_source_signals": {
                "serp_opportunity_scan": [
                    {
                        "page": r["page_url_normalized"],
                        "avg_position": round(float(r["avg_position"] or 0), 1),
                        "impressions_14d": int(r["impressions"] or 0),
                        "clicks_14d": int(r["clicks"] or 0),
                        "sessions_14d": int(r["sessions"] or 0),
                    }
                    for r in serp_rows
                ],
            },
            "prior_brief": {
                "headline": prior_data.get("headline") if prior_data else None,
                "bullets": prior_data.get("bullets", []) if prior_data else [],
            } if prior_data else None,
            "memory": memories,
            "pinned_questions": pinned_titles,
        }

        # ── Call Claude ────────────────────────────────────────────────────────
        prompt_path = Path(__file__).parent / "prompts" / "daily_brief.md"
        system_prompt = prompt_path.read_text(encoding="utf-8")

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=NARRATIVE_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": (
                    f"Generate the daily brief for {day_label}.\n\n"
                    f"Input payload:\n```json\n"
                    f"{json.dumps(payload, indent=2, default=str)}\n```"
                ),
            }],
        )

        raw = response.content[0].text.strip()
        # Strip accidental markdown fences
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw.strip())

        brief_obj = json.loads(raw)  # raises if Claude returned invalid JSON

        # ── Persist ────────────────────────────────────────────────────────────
        async with factory() as db:
            existing = (await db.execute(
                select(DailyBrief).where(
                    DailyBrief.property_id == property_id,
                    DailyBrief.brief_date == today,
                )
            )).scalar_one_or_none()

            if existing is None:
                db.add(DailyBrief(
                    property_id=property_id,
                    brief_date=today,
                    brief_json=json.dumps(brief_obj),
                    generated_at=datetime.now(UTC),
                    generation_count=1,
                ))
            else:
                existing.brief_json = json.dumps(brief_obj)
                existing.generated_at = datetime.now(UTC)
                # generation_count already incremented by the regenerate route

            await db.commit()

        logger.info("Daily brief generated", property_id=property_id)
        return {"status": "done", "property_id": property_id}

    except Exception as exc:
        logger.error(
            "Daily brief generation failed",
            property_id=property_id,
            error=str(exc),
        )
        # Persist an error marker so the UI can surface the failure instead
        # of showing "not ready" indefinitely with no feedback.
        try:
            from prism.db.models.brief import DailyBrief
            async with factory() as db:
                existing = (await db.execute(
                    select(DailyBrief).where(
                        DailyBrief.property_id == property_id,
                        DailyBrief.brief_date == today,
                    )
                )).scalar_one_or_none()
                if existing is not None:
                    existing.brief_json = json.dumps({
                        "__error": str(exc)[:500],
                    })
                    existing.generated_at = datetime.now(UTC)
                    await db.commit()
        except Exception:
            pass  # best-effort; don't mask the original error
        return {"error": str(exc), "property_id": property_id}
