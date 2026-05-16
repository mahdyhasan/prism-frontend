"""Insight orchestration — runs detectors, asks Claude to narrate, persists.

Flow:
  1. Detector computes findings (pure stats — no LLM).
  2. Call Claude haiku with the precomputed numbers for a narrative.
  3. Parse the JSON response. On parse failure, fall back to a templated
     narrative so we never lose an insight to a bad LLM response.
  4. Insert the Insight row keyed on (property_id, kind, period_start,
     period_end). Content-hash dedupe prevents reruns from creating
     duplicate rows when the underlying findings haven't changed.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.logging import logger
from prism.db.models.insight import Insight
from prism.services.ai.client import CHEAP_MODEL, call_claude
from prism.services.ai.detectors.anomaly import detect_session_anomalies
from prism.services.ai.detectors.cannibalization import detect_cannibalization
from prism.services.ai.detectors.cwv_mobile_desktop import detect as detect_cwv_mobile_desktop
from prism.services.ai.detectors.cwv_regression import detect as detect_cwv_regression
from prism.services.ai.detectors.cwv_traffic_impact import detect as detect_cwv_traffic_impact
from prism.services.ai.detectors.decay import detect_content_decay
from prism.services.ai.detectors.frustration import detect as detect_frustration
from prism.services.ai.detectors.opportunity import detect_serp_opportunities
from prism.services.ai.detectors.trend import detect_metric_trends
from prism.services.ai.prompts import (
    INSIGHT_ANOMALY_SYSTEM,
    INSIGHT_CANNIBALIZATION_SYSTEM,
    INSIGHT_CWV_SYSTEM,
    INSIGHT_DECAY_SYSTEM,
    INSIGHT_FRUSTRATION_SYSTEM,
    INSIGHT_OPPORTUNITY_SYSTEM,
    INSIGHT_TREND_SYSTEM,
    build_anomaly_user_message,
    build_findings_user_message,
)

_ALLOWED_SEVERITIES = {"low", "medium", "high", "critical"}


def _strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        # remove leading fence (with optional language hint) and trailing fence
        first_newline = t.find("\n")
        if first_newline != -1:
            t = t[first_newline + 1:]
        if t.endswith("```"):
            t = t[: -3]
    return t.strip()


def _parse_claude_insight(text: str) -> dict | None:
    try:
        cleaned = _strip_code_fences(text)
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    title = data.get("title")
    summary = data.get("summary")
    severity = data.get("severity")
    if not isinstance(title, str) or not isinstance(summary, str):
        return None
    if severity not in _ALLOWED_SEVERITIES:
        return None
    return {
        "title": title[:500],
        "summary": summary,
        "severity": severity,
    }


def _fallback_narrative(anomaly: dict) -> dict:
    direction = "spike" if anomaly["actual"] > anomaly["baseline"] else "drop"
    title = f"Sessions {direction} on {anomaly['date'].isoformat()}"
    summary = (
        f"Sessions were {int(anomaly['actual'])} vs a 7-day baseline of "
        f"{anomaly['baseline']:.0f} (z={anomaly['z_score']})."
    )
    return {
        "title": title[:500],
        "summary": summary[:300],
        "severity": anomaly["severity"],
    }


async def generate_anomaly_insights(
    db: AsyncSession,
    property_id: int,
    tenant_id: int,
) -> int:
    """Detect session anomalies, narrate with Claude, persist as Insight rows.

    Returns the count of newly created insights (existing rows for the same
    period are skipped — idempotent).
    """
    anomalies = await detect_session_anomalies(db, property_id)
    if not anomalies:
        return 0

    # Pre-fetch existing insight keys to make the upsert cheap.
    existing_result = await db.execute(
        select(Insight.period_start, Insight.period_end).where(
            Insight.property_id == property_id,
            Insight.kind == "anomaly",
        )
    )
    existing_periods: set[tuple] = {(r[0], r[1]) for r in existing_result.all()}

    created = 0
    for anomaly in anomalies:
        period_start = anomaly["date"]
        period_end = anomaly["date"]
        if (period_start, period_end) in existing_periods:
            continue

        user_msg = build_anomaly_user_message(
            metric_name=anomaly["metric"],
            current_value=anomaly["actual"],
            baseline_value=anomaly["baseline"],
            z_score=anomaly["z_score"],
            period=period_start.isoformat(),
        )

        narrative: dict | None = None
        model_used: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None
        try:
            response_text = await call_claude(
                purpose="insight.anomaly",
                model=CHEAP_MODEL,
                system=INSIGHT_ANOMALY_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=400,
                db=db,
                tenant_id=tenant_id,
                property_id=property_id,
            )
            narrative = _parse_claude_insight(response_text)
            model_used = CHEAP_MODEL
            # Token counts are logged by call_claude; we'd need them returned to
            # also stamp them on the Insight row. Leaving as None for the
            # scaffolding pass — call_claude can be extended to return usage.
        except Exception as exc:
            logger.warning(
                "Claude narration failed; falling back to templated narrative",
                property_id=property_id,
                date=str(period_start),
                error=f"{type(exc).__name__}: {exc}",
            )
            narrative = None

        if narrative is None:
            narrative = _fallback_narrative(anomaly)
            model_used = None

        insight = Insight(
            property_id=property_id,
            kind="anomaly",
            severity=narrative["severity"],
            title=narrative["title"],
            summary=narrative["summary"],
            supporting_data={
                "metric": anomaly["metric"],
                "actual": anomaly["actual"],
                "baseline": anomaly["baseline"],
                "stddev": anomaly["stddev"],
                "z_score": anomaly["z_score"],
                "date": period_start.isoformat(),
            },
            detected_at=datetime.now(timezone.utc),
            period_start=period_start,
            period_end=period_end,
            status="new",
            claude_model_used=model_used,
            claude_input_tokens=input_tokens,
            claude_output_tokens=output_tokens,
        )
        db.add(insight)
        existing_periods.add((period_start, period_end))
        created += 1

    await db.commit()
    logger.info(
        "Anomaly insight generation complete",
        property_id=property_id,
        created=created,
        candidates=len(anomalies),
    )
    return created


# ── Cross-source detectors → Insight rows ────────────────────────────────────
#
# Shared shape: each detector returns one dict per scan ("finding bundle") with
# top_findings + total_count + content_identity. This block turns that bundle
# into one Insight row, narrated by Claude or by a template fallback.

# Map detector "kind" → (system prompt, plural label for fallback titles).
_KIND_PROMPTS: dict[str, tuple[str, str]] = {
    "decay":               (INSIGHT_DECAY_SYSTEM, "decaying pages"),
    "cannibalization":     (INSIGHT_CANNIBALIZATION_SYSTEM, "cannibalized queries"),
    "opportunity":         (INSIGHT_OPPORTUNITY_SYSTEM, "SERP opportunities"),
    "trend":               (INSIGHT_TREND_SYSTEM, "metric trends"),
    "frustration":         (INSIGHT_FRUSTRATION_SYSTEM, "high-frustration pages"),
    "cwv_traffic_impact":  (INSIGHT_CWV_SYSTEM, "high-traffic pages with poor Core Web Vitals"),
    "cwv_regression":      (INSIGHT_CWV_SYSTEM, "pages with CWV regression"),
    "cwv_mobile_desktop":  (INSIGHT_CWV_SYSTEM, "pages with mobile/desktop CWV divergence"),
}


def _compute_content_hash(kind: str, identity: list[str]) -> str:
    """Stable hash for an Insight's underlying findings.

    Two scan runs that surface the same set of top pages/queries/metrics
    produce the same hash — even if numbers shift slightly day-to-day. We
    use this to skip creating duplicate Insights for the same situation.
    """
    payload = json.dumps([kind, sorted(identity or [])], separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _fallback_findings_narrative(bundle: dict[str, Any]) -> dict:
    """Templated narrative used when Claude is unavailable or returns junk."""
    kind = bundle["kind"]
    _, plural = _KIND_PROMPTS[kind]
    n = bundle["total_count"]
    title = f"{n} {plural} detected" if n != 1 else f"1 {plural[:-1]} detected"
    summary_lines = []
    for f in bundle["top_findings"][:3]:
        # Pick the first identifying field that makes sense per detector kind
        ident = (
            f.get("page") or f.get("page_url") or f.get("query") or f.get("metric") or "?"
        )
        summary_lines.append(str(ident))
    summary = f"Top items: {'; '.join(summary_lines)}"
    return {
        "title": title[:500],
        "summary": summary[:300],
        "severity": bundle["severity"],
    }


async def _narrate_findings(
    db: AsyncSession,
    bundle: dict[str, Any],
    tenant_id: int,
    property_id: int,
) -> tuple[dict, str | None]:
    """Ask Claude to write a title + summary for a finding bundle.

    Returns (narrative_dict, model_used_or_None). Falls back to a template
    on any failure so the pipeline never loses an insight to an LLM hiccup.
    """
    kind = bundle["kind"]
    system_prompt, _ = _KIND_PROMPTS[kind]
    period = f"{bundle['period_start'].isoformat()} → {bundle['period_end'].isoformat()}"
    user_msg = build_findings_user_message(
        kind=kind,
        period=period,
        total_count=bundle["total_count"],
        top_findings=bundle["top_findings"],
        context=bundle.get("context"),
    )

    try:
        response_text = await call_claude(
            purpose=f"insight.{kind}",
            model=CHEAP_MODEL,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=400,
            db=db,
            tenant_id=tenant_id,
            property_id=property_id,
        )
        narrative = _parse_claude_insight(response_text)
        if narrative is not None:
            return narrative, CHEAP_MODEL
    except Exception as exc:
        logger.warning(
            "Claude narration failed; using fallback template",
            kind=kind,
            property_id=property_id,
            error=f"{type(exc).__name__}: {exc}",
        )

    return _fallback_findings_narrative(bundle), None


async def _persist_finding_bundle(
    db: AsyncSession,
    bundle: dict[str, Any],
    tenant_id: int,
    property_id: int,
) -> int:
    """Persist one detector bundle as an Insight if (a) it's not a duplicate of
    a recent finding and (b) the unique-constraint window doesn't already hold one.

    Returns 1 if created, 0 if skipped.
    """
    kind = bundle["kind"]
    content_hash = _compute_content_hash(kind, bundle.get("content_identity", []))

    # Dedupe rule: an existing live (new or acknowledged) Insight of the same
    # kind with the same content_hash means "nothing materially changed".
    # Look at the last 30 days so stale findings still re-fire eventually.
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    dup_result = await db.execute(
        select(Insight.id, Insight.supporting_data)
        .where(
            Insight.property_id == property_id,
            Insight.kind == kind,
            Insight.status.in_(("new", "acknowledged")),
            Insight.detected_at >= cutoff,
        )
        .order_by(Insight.detected_at.desc())
    )
    for row in dup_result.all():
        existing_hash = (row.supporting_data or {}).get("content_hash")
        if existing_hash == content_hash:
            logger.info(
                "Skipping duplicate finding (content_hash match)",
                kind=kind,
                property_id=property_id,
                content_hash=content_hash,
            )
            return 0

    narrative, model_used = await _narrate_findings(db, bundle, tenant_id, property_id)

    insight = Insight(
        property_id=property_id,
        kind=kind,
        severity=narrative["severity"],
        title=narrative["title"],
        summary=narrative["summary"],
        supporting_data={
            "content_hash": content_hash,
            "top_findings": bundle["top_findings"],
            "total_count": bundle["total_count"],
            "context": bundle.get("context", {}),
        },
        detected_at=datetime.now(timezone.utc),
        period_start=bundle["period_start"],
        period_end=bundle["period_end"],
        status="new",
        claude_model_used=model_used,
        claude_input_tokens=None,
        claude_output_tokens=None,
    )
    db.add(insight)
    try:
        await db.commit()
    except IntegrityError:
        # Race condition: another run already persisted same (kind, period)
        await db.rollback()
        logger.info(
            "Skipping insight (period unique constraint hit)",
            kind=kind, property_id=property_id,
        )
        return 0
    return 1


# Map of detector kind → callable. Each detector returns a bundle dict or None.
_CROSS_SOURCE_DETECTORS = (
    ("decay",               detect_content_decay),
    ("cannibalization",     detect_cannibalization),
    ("opportunity",         detect_serp_opportunities),
    ("trend",               detect_metric_trends),
    ("frustration",         detect_frustration),
    ("cwv_traffic_impact",  detect_cwv_traffic_impact),
    ("cwv_regression",      detect_cwv_regression),
    ("cwv_mobile_desktop",  detect_cwv_mobile_desktop),
)


async def generate_cross_source_insights(
    db: AsyncSession,
    property_id: int,
    tenant_id: int,
) -> dict[str, int]:
    """Run every cross-source detector and persist findings as Insights.

    Returns a dict: {kind: insights_created_count}. Failures of one detector
    do not stop the rest — each runs in its own try block.
    """
    out: dict[str, int] = {}
    for kind, detector in _CROSS_SOURCE_DETECTORS:
        try:
            bundle = await detector(db, property_id)
        except Exception as exc:
            logger.error(
                "Detector failed",
                kind=kind, property_id=property_id,
                error=f"{type(exc).__name__}: {exc}",
            )
            out[kind] = 0
            continue
        if bundle is None:
            out[kind] = 0
            continue
        out[kind] = await _persist_finding_bundle(db, bundle, tenant_id, property_id)
    return out


async def run_property_insights(
    db: AsyncSession,
    property_id: int,
    tenant_id: int,
) -> dict[str, int]:
    """Top-level orchestrator: run every detector for a property.

    Anomaly (per-day finding) and cross-source (one-bundle finding) detectors
    use separate persistence paths but share the same Insight table.
    Returns: {kind: created_count}.
    """
    counts: dict[str, int] = {}
    counts["anomaly"] = await generate_anomaly_insights(db, property_id, tenant_id)
    counts.update(await generate_cross_source_insights(db, property_id, tenant_id))
    logger.info("Property insights complete", property_id=property_id, **counts)
    return counts
