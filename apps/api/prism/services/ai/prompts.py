"""Prompt registry for AI insight generation.

Every system prompt enforces the same hard rule: the LLM receives precomputed
metrics and never recomputes them. Output is JSON with title (<=80 chars),
summary (<=300 chars, plain English), severity (low/medium/high/critical).
"""
from __future__ import annotations

import json

_SHARED_RULES = (
    "You receive computed metrics from a trusted analytics pipeline. "
    "NEVER recompute, estimate, or infer numbers. Reference ONLY the figures "
    "I give you in the user message. If a number isn't in the data I provide, "
    "do not invent it.\n\n"
    "Output a single JSON object — no prose, no markdown fences — with exactly "
    "these keys:\n"
    '  "title":    string, <= 80 chars, plain English, no jargon\n'
    '  "summary":  string, <= 300 chars, plain English, no jargon, no em dashes\n'
    '  "severity": one of "low" | "medium" | "high" | "critical"\n'
    "Do not include any other keys. Do not wrap the JSON in code blocks."
)


INSIGHT_ANOMALY_SYSTEM = (
    "You are an analytics narrator. Your job is to describe a detected anomaly "
    "in a website's traffic metric in plain English for a marketer.\n\n"
    + _SHARED_RULES
)

INSIGHT_TREND_SYSTEM = (
    "You are an analytics narrator. Your job is to describe a sustained trend "
    "in a website's traffic metric in plain English for a marketer.\n\n"
    + _SHARED_RULES
)

INSIGHT_OPPORTUNITY_SYSTEM = (
    "You are an analytics narrator. Your job is to describe an opportunity "
    "(a page, query, or channel under-performing relative to its potential) "
    "in plain English for a marketer.\n\n"
    + _SHARED_RULES
)

INSIGHT_DECAY_SYSTEM = (
    "You are an analytics narrator. Your job is to describe content decay "
    "(a previously well-performing page losing traffic) in plain English "
    "for a marketer.\n\n"
    + _SHARED_RULES
)

INSIGHT_CANNIBALIZATION_SYSTEM = (
    "You are an analytics narrator. Your job is to describe SEO cannibalization "
    "(multiple pages on the same site competing for the same search query) "
    "in plain English for a marketer.\n\n"
    + _SHARED_RULES
)

INSIGHT_FRUSTRATION_SYSTEM = (
    "You are an analytics narrator. Your job is to describe user frustration "
    "signals detected on specific pages of a website. Frustration is measured "
    "by rage clicks (users clicking frantically), dead clicks (clicks that do "
    "nothing), and quick backs (users immediately returning to search results). "
    "Explain what the data likely means and suggest one or two investigation "
    "angles in plain English for a marketer.\n\n"
    + _SHARED_RULES
)


INSIGHT_CWV_SYSTEM = (
    "You are an analytics narrator. Your job is to describe a Core Web Vitals "
    "performance finding for a website's pages. Core Web Vitals are Google's "
    "user experience metrics: LCP (loading speed), INP (interactivity), and "
    "CLS (visual stability). Poor scores can hurt both user experience and "
    "Google search rankings. Explain which pages are affected, what the data "
    "shows, and why it matters for the business, in plain English for a marketer.\n\n"
    + _SHARED_RULES
)


def build_anomaly_user_message(
    *,
    metric_name: str,
    current_value: float,
    baseline_value: float,
    z_score: float,
    period: str,
    dimensions: dict | None = None,
) -> str:
    """Render the user-message JSON payload for an anomaly narration call.

    The Claude call must reference ONLY these numbers — they are computed
    by the detector layer (pandas/SQL), never by the LLM.
    """
    payload = {
        "metric": metric_name,
        "period": period,
        "current_value": current_value,
        "baseline_value": baseline_value,
        "z_score": round(float(z_score), 2),
        "direction": "above" if current_value >= baseline_value else "below",
        "dimensions": dimensions or {},
    }
    return (
        "Here are the precomputed metrics for an anomaly detection. "
        "Describe what happened. Use only these numbers:\n\n"
        + json.dumps(payload, indent=2)
    )


# ── Generic builder for "top N findings" narration ───────────────────────────
#
# All four cross-source detectors (decay, cannibalization, opportunity, trend)
# return a ranked list. They use the same shape: a list of facts + a count.
# Claude composes a single title + summary describing the top of the list.

def build_findings_user_message(
    *,
    kind: str,
    period: str,
    total_count: int,
    top_findings: list[dict],
    context: dict | None = None,
) -> str:
    """Render a user-message payload for any 'top N findings' narration call.

    Claude is told what kind of issue this is and given the top N rows of
    precomputed numbers. It composes title+summary; it never recomputes.
    """
    payload = {
        "kind": kind,
        "period": period,
        "total_findings": total_count,
        "top_findings": top_findings,
        "context": context or {},
    }
    return (
        f"Here are the precomputed top findings for a {kind} scan. "
        f"There are {total_count} finding{'s' if total_count != 1 else ''} in total; "
        f"the highest-impact ones are listed below. "
        "Describe what the data shows. Use only these numbers:\n\n"
        + json.dumps(payload, indent=2, default=str)
    )
