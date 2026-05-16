"""Page Performance — aggregates xs_page_daily into a ranked-and-scored list.

Reuses the nightly-materialized cross-source view rather than re-joining GA4 +
GSC on the fly. Returns one row per page with all the headline metrics plus a
composite Page Health score for sortability and visual highlighting.

When clarity_page_daily rows exist for the property the response gains:
  - frustration_score  = (dead_clicks + 2*rage_clicks + quick_backs) / sessions
  - scroll_depth_avg   = average scroll depth [0..1]
  - health_score       uses the 4-factor formula (conv 35% + engage 25% +
                        1-bounce 20% + 1-frustration 20%)
Without Clarity data, health_score uses the original 3-factor formula and
frustration_score is null.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from prism.db.models.clarity import ClarityPageDaily
from prism.db.models.cross_source import XSPageDaily
from prism.db.models.ga4 import GA4LandingPageDeviceDaily

# Sort keys the frontend can request. Keep this list tight so SQL injection
# is impossible — every value gets mapped to a known column / expression.
SortKey = Literal[
    "sessions",
    "conv_rate",
    "engagement_rate",
    "bounce_rate",
    "avg_duration",
    "exit_rate",
    "clicks",
    "impressions",
    "position",
    "health_score",
    "frustration_score",
    "scroll_depth",
]

# ── Page Health score weights ────────────────────────────────────────────────
# Without Clarity: 3-factor (original weights)
_W_CONV_NO_CLARITY = 0.40
_W_ENGAGE_NO_CLARITY = 0.30
_W_BOUNCE_INV_NO_CLARITY = 0.30

# With Clarity: 4-factor (frustration gets its own slice)
_W_CONV_CLARITY = 0.35
_W_ENGAGE_CLARITY = 0.25
_W_BOUNCE_INV_CLARITY = 0.20
_W_FRUST_INV_CLARITY = 0.20

# Pages with fewer than this many sessions get a null health score (too noisy).
_HEALTH_MIN_SESSIONS = 30

# Frustration score is clamped to this max before normalising to [0, 1].
# Interpretation: a page where every session has 3 frustration events = worst.
_FRUSTRATION_CAP = 3.0


def _compute_frustration(
    dead_clicks: int,
    rage_clicks: int,
    quick_backs: int,
    session_count: int,
) -> float | None:
    """Weighted frustration events per session, clamped to [0, 1]."""
    if not session_count:
        return None
    raw = (dead_clicks + 2 * rage_clicks + quick_backs) / float(session_count)
    return round(min(raw / _FRUSTRATION_CAP, 1.0), 4)


def _compute_health(row: dict[str, Any]) -> float | None:
    sessions = float(row.get("sessions") or 0)
    if sessions < _HEALTH_MIN_SESSIONS:
        return None
    conv_rate = float(row.get("conversion_rate") or 0)
    engagement_rate = float(row.get("engagement_rate") or 0)
    bounce_rate = float(row.get("bounce_rate") or 0)

    frust = row.get("frustration_score")
    if frust is not None:
        # 4-factor formula when Clarity data is present
        score = (
            _W_CONV_CLARITY * min(conv_rate * 10, 1.0)
            + _W_ENGAGE_CLARITY * engagement_rate
            + _W_BOUNCE_INV_CLARITY * (1.0 - bounce_rate)
            + _W_FRUST_INV_CLARITY * (1.0 - float(frust))
        )
    else:
        # 3-factor fallback (original weights)
        score = (
            _W_CONV_NO_CLARITY * min(conv_rate * 10, 1.0)
            + _W_ENGAGE_NO_CLARITY * engagement_rate
            + _W_BOUNCE_INV_NO_CLARITY * (1.0 - bounce_rate)
        )
    # Clamp to [0, 1] for sanity (bounce_rate can sometimes exceed 1 in GA4)
    return round(max(0.0, min(1.0, score)), 4)


def _exit_rate(exits: int, sessions: int) -> float | None:
    s = float(sessions or 0)
    if s <= 0:
        return None
    return round(float(exits or 0) / s, 6)


async def _fetch_clarity_map(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
) -> dict[str, dict[str, Any]]:
    """Return {page_url: {dead_clicks, rage_clicks, quick_backs, scroll_depth_avg,
    session_count}} summed over the date range.  Empty dict if no Clarity data.

    page_url is normalised to lowercase, no trailing slash for matching.
    """
    result = await db.execute(
        select(
            ClarityPageDaily.page_url,
            func.sum(ClarityPageDaily.dead_clicks).label("dead_clicks"),
            func.sum(ClarityPageDaily.rage_clicks).label("rage_clicks"),
            func.sum(ClarityPageDaily.quick_backs).label("quick_backs"),
            func.avg(ClarityPageDaily.scroll_depth_avg).label("scroll_depth_avg"),
            func.sum(ClarityPageDaily.session_count).label("session_count"),
        )
        .where(
            ClarityPageDaily.property_id == property_id,
            ClarityPageDaily.date >= start,
            ClarityPageDaily.date <= end,
        )
        .group_by(ClarityPageDaily.page_url)
    )
    clarity: dict[str, dict[str, Any]] = {}
    for row in result.mappings().all():
        # Normalise URL: lowercase, strip trailing slash, extract path only
        raw_url: str = row["page_url"] or ""
        norm = raw_url.lower().rstrip("/")
        # Strip protocol + domain to get path
        for prefix in ("https://", "http://"):
            if norm.startswith(prefix):
                norm = norm[len(prefix):]
                if "/" in norm:
                    norm = norm[norm.index("/"):]
                break
        clarity[norm] = {
            "dead_clicks": int(row["dead_clicks"] or 0),
            "rage_clicks": int(row["rage_clicks"] or 0),
            "quick_backs": int(row["quick_backs"] or 0),
            "scroll_depth_avg": round(float(row["scroll_depth_avg"] or 0), 4),
            "session_count": int(row["session_count"] or 0),
        }
    return clarity


async def get_page_performance(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
    *,
    min_sessions: int = 1,
    sort_by: SortKey = "sessions",
    sort_desc: bool = True,
    limit: int = 100,
    device: str | None = None,
) -> list[dict[str, Any]]:
    """Aggregate per-page metrics over a date range, sorted and filtered.

    When `device` is set (mobile/desktop/tablet), queries the GA4-only
    `ga4_landing_page_device_daily` table — GSC columns will be 0/null
    because GSC doesn't have a device dimension at our page grain.
    Otherwise queries `xs_page_daily` for the full GA4 + GSC join.

    Clarity frustration data is LEFT-JOINed by page URL regardless of which
    source table is active.  frustration_score is null when no Clarity rows
    exist for the property/period.
    """
    # Fetch Clarity frustration data concurrently with the main query (same
    # async session, sequential await — fine for our load pattern).
    clarity_map = await _fetch_clarity_map(db, property_id, start, end)

    # Choose the source table based on whether device filtering is requested
    if device:
        T = GA4LandingPageDeviceDaily
        stmt = (
            select(
                T.landing_page.label("page"),
                func.coalesce(func.sum(T.sessions), 0).label("sessions"),
                func.coalesce(func.sum(T.users), 0).label("users"),
                func.coalesce(func.sum(T.engaged_sessions), 0).label("engaged_sessions"),
                func.coalesce(func.sum(T.conversions), 0).label("conversions"),
                func.coalesce(func.sum(T.revenue), 0).label("revenue"),
                func.coalesce(func.avg(T.bounce_rate), 0).label("bounce_rate"),
                func.coalesce(func.avg(T.avg_session_duration), 0).label("avg_session_duration"),
                func.coalesce(func.sum(T.exits), 0).label("exits"),
            )
            .where(
                T.property_id == property_id,
                T.date >= start,
                T.date <= end,
                T.device_category == device,
            )
            .group_by(T.landing_page)
            .having(func.sum(T.sessions) >= min_sessions)
        )
        has_gsc = False
    else:
        stmt = (
            select(
                XSPageDaily.page_url_normalized.label("page"),
                func.coalesce(func.sum(XSPageDaily.sessions), 0).label("sessions"),
                func.coalesce(func.sum(XSPageDaily.users), 0).label("users"),
                func.coalesce(func.sum(XSPageDaily.engaged_sessions), 0).label("engaged_sessions"),
                func.coalesce(func.sum(XSPageDaily.conversions), 0).label("conversions"),
                func.coalesce(func.sum(XSPageDaily.revenue), 0).label("revenue"),
                func.coalesce(func.avg(XSPageDaily.bounce_rate), 0).label("bounce_rate"),
                func.coalesce(func.avg(XSPageDaily.avg_session_duration), 0).label("avg_session_duration"),
                func.coalesce(func.sum(XSPageDaily.clicks), 0).label("clicks"),
                func.coalesce(func.sum(XSPageDaily.impressions), 0).label("impressions"),
                func.coalesce(func.avg(XSPageDaily.ctr), 0).label("ctr"),
                func.coalesce(func.avg(XSPageDaily.avg_position), 0).label("avg_position"),
            )
            .where(
                XSPageDaily.property_id == property_id,
                XSPageDaily.date >= start,
                XSPageDaily.date <= end,
            )
            .group_by(XSPageDaily.page_url_normalized)
            .having(func.sum(XSPageDaily.sessions) >= min_sessions)
        )
        has_gsc = True

    # Sort: direct SQL where possible, Python-side for derived metrics
    direct_sort_map: dict[str, str] = {
        "sessions":         "sessions",
        "bounce_rate":      "bounce_rate",
        "avg_duration":     "avg_session_duration",
    }
    if has_gsc:
        direct_sort_map.update({
            "clicks":      "clicks",
            "impressions": "impressions",
            "position":    "avg_position",
        })
    if sort_by in direct_sort_map:
        col = direct_sort_map[sort_by]
        direction = "DESC" if sort_desc else "ASC"
        stmt = stmt.order_by(text(f"{col} {direction}"))
    else:
        stmt = stmt.order_by(text("sessions DESC"))

    result = await db.execute(
        stmt.limit(limit * 3 if sort_by not in direct_sort_map else limit),
    )
    raw = result.mappings().all()

    rows: list[dict[str, Any]] = []
    for r in raw:
        sessions = int(r["sessions"] or 0)
        engaged = int(r["engaged_sessions"] or 0)
        conversions = int(r["conversions"] or 0)
        bounce = float(r["bounce_rate"] or 0)

        conv_rate = conversions / sessions if sessions > 0 else None
        engagement_rate = engaged / sessions if sessions > 0 else None

        # Exits: device table has the column directly; XS table doesn't.
        # When using XSPageDaily we approximate via sessions × bounce_rate
        # (same convention as the GA4 ingestion's `exits` derivation).
        if has_gsc:
            exits = int(round(sessions * bounce))
            clicks = int(r["clicks"] or 0)
            impressions = int(r["impressions"] or 0)
            ctr = float(r["ctr"] or 0)
            avg_position = float(r["avg_position"] or 0)
        else:
            exits = int(r["exits"] or 0)
            clicks = 0
            impressions = 0
            ctr = 0.0
            avg_position = 0.0

        # Clarity LEFT-JOIN: normalise the page path for lookup
        page_raw: str = r["page"] or ""
        page_norm = page_raw.lower().rstrip("/")
        for pfx in ("https://", "http://"):
            if page_norm.startswith(pfx):
                page_norm = page_norm[len(pfx):]
                if "/" in page_norm:
                    page_norm = page_norm[page_norm.index("/"):]
                break
        clarity = clarity_map.get(page_norm)

        frustration_score: float | None = None
        scroll_depth_avg: float | None = None
        if clarity:
            frustration_score = _compute_frustration(
                clarity["dead_clicks"],
                clarity["rage_clicks"],
                clarity["quick_backs"],
                clarity["session_count"],
            )
            scroll_depth_avg = clarity["scroll_depth_avg"] or None

        row = {
            "page": r["page"],
            "sessions": sessions,
            "users": int(r["users"] or 0),
            "engaged_sessions": engaged,
            "conversions": conversions,
            "revenue": float(r["revenue"] or 0),
            "bounce_rate": round(bounce, 4),
            "engagement_rate": round(engagement_rate, 4) if engagement_rate is not None else None,
            "conversion_rate": round(conv_rate, 6) if conv_rate is not None else None,
            "avg_session_duration": round(float(r["avg_session_duration"] or 0), 2),
            "exits": exits,
            "exit_rate": _exit_rate(exits, sessions),
            "clicks": clicks,
            "impressions": impressions,
            "ctr": round(ctr, 4),
            "avg_position": round(avg_position, 2),
            "frustration_score": frustration_score,
            "scroll_depth_avg": scroll_depth_avg,
        }
        row["health_score"] = _compute_health(row)
        rows.append(row)

    # Python-side sort for derived metrics (and any GSC sort when device-filtered)
    if sort_by not in direct_sort_map:
        key_map = {
            "conv_rate":          "conversion_rate",
            "engagement_rate":    "engagement_rate",
            "health_score":       "health_score",
            "exit_rate":          "exit_rate",
            "clicks":             "clicks",
            "impressions":        "impressions",
            "position":           "avg_position",
            "frustration_score":  "frustration_score",
            "scroll_depth":       "scroll_depth_avg",
        }
        attr = key_map.get(sort_by, "sessions")
        worst = float("-inf") if sort_desc else float("inf")
        rows.sort(
            key=lambda r: (r.get(attr) if r.get(attr) is not None else worst),
            reverse=sort_desc,
        )
        rows = rows[:limit]

    return rows
