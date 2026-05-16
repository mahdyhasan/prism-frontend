from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Anthropic tool definitions (Claude reads these)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "query_ga4",
        "description": (
            "Query GA4 warehouse data. Returns sessions, users, conversions, and other metrics "
            "broken down by optional dimensions. Respects 200-row cap with tail summary."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "date_range": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                    },
                    "required": ["start", "end"],
                },
                "metrics": {"type": "array", "items": {"type": "string"}},
                "dimensions": {"type": "array", "items": {"type": "string"}},
                "filters": {"type": "object"},
                "limit": {"type": "integer", "default": 200},
                "sort_by": {"type": "string"},
            },
            "required": ["property_id", "date_range", "metrics"],
        },
    },
    {
        "name": "query_gsc",
        "description": (
            "Query Google Search Console warehouse data. Returns clicks, impressions, CTR, "
            "position by dimension. Respects 200-row cap."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "date_range": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                    },
                    "required": ["start", "end"],
                },
                "dimensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["date"],
                },
                "filters": {"type": "object"},
                "limit": {"type": "integer", "default": 200},
                "sort_by": {"type": "string"},
            },
            "required": ["property_id", "date_range"],
        },
    },
    {
        "name": "compare_periods",
        "description": (
            "Compare a metric between two time periods for GA4 or GSC. "
            "Returns delta percentage and absolute change."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "source": {"type": "string", "enum": ["ga4", "gsc"]},
                "metric": {"type": "string"},
                "period_a": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                    },
                    "required": ["start", "end"],
                },
                "period_b": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                    },
                    "required": ["start", "end"],
                },
                "dimensions": {"type": "array", "items": {"type": "string"}},
                "filters": {"type": "object"},
            },
            "required": ["property_id", "source", "metric", "period_a", "period_b"],
        },
    },
    {
        "name": "correlate_page_performance",
        "description": (
            "Join GA4 and GSC data for pages matching a URL pattern. Shows sessions, "
            "conversions, clicks, impressions, CTR, and position side by side."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "page_pattern": {
                    "type": "string",
                    "description": "Exact path like /staff-augmentation or prefix like /blog/",
                },
                "date_range": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                    },
                    "required": ["start", "end"],
                },
            },
            "required": ["property_id", "page_pattern", "date_range"],
        },
    },
    {
        "name": "intent_vs_outcome",
        "description": (
            "Find pages where GSC impressions rose but GA4 conversions did not (or vice versa). "
            "Surfaces intent/conversion mismatches."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "date_range": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                    },
                    "required": ["start", "end"],
                },
                "min_impression_delta_pct": {"type": "number", "default": 20},
            },
            "required": ["property_id", "date_range"],
        },
    },
    {
        "name": "vanity_vs_value_queries",
        "description": (
            "Rank GSC queries by actual business value (clicks weighted by conversion rate "
            "of their landing pages), not just click volume."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "date_range": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                    },
                    "required": ["start", "end"],
                },
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["property_id", "date_range"],
        },
    },
    {
        "name": "cannibalization_scan",
        "description": (
            "Find GSC queries where 2 or more pages are competing for the same query. "
            "Recommends which page to consolidate to based on GA4 conversions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "date_range": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                    },
                    "required": ["start", "end"],
                },
                "impression_threshold": {"type": "integer", "default": 100},
            },
            "required": ["property_id", "date_range"],
        },
    },
    {
        "name": "serp_opportunity_scan",
        "description": (
            "Find GSC queries ranking at position 8-20 with high impressions — "
            "low-hanging SEO opportunities. Includes GA4 performance of the ranking page."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "min_position": {"type": "number", "default": 8},
                "max_position": {"type": "number", "default": 20},
                "min_impressions": {"type": "integer", "default": 50},
            },
            "required": ["property_id"],
        },
    },
    {
        "name": "content_decay_scan",
        "description": (
            "Find pages losing traffic, classified by cause: ranking loss, CTR loss, "
            "demand loss, or GA4-only drop."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "lookback_days": {"type": "integer", "default": 90},
                "min_sessions_threshold": {"type": "integer", "default": 10},
            },
            "required": ["property_id"],
        },
    },
    {
        "name": "detect_anomalies",
        "description": (
            "Detect statistical anomalies in a metric time series using rolling z-score. "
            "Returns dates where the metric was unusually high or low."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "source": {"type": "string", "enum": ["ga4", "gsc"]},
                "metric": {"type": "string"},
                "lookback_days": {"type": "integer", "default": 30},
                "z_threshold": {"type": "number", "default": 2.5},
            },
            "required": ["property_id", "source", "metric"],
        },
    },
    {
        "name": "rolling_trend",
        "description": (
            "Compute rolling average trend for a metric over time. "
            "Shows whether a metric is trending up or down."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "source": {"type": "string", "enum": ["ga4", "gsc"]},
                "metric": {"type": "string"},
                "window_days": {"type": "integer", "default": 7},
                "lookback_days": {"type": "integer", "default": 90},
            },
            "required": ["property_id", "source", "metric"],
        },
    },
    {
        "name": "segment_split",
        "description": (
            "Split a metric by a dimension to see Pareto distribution. "
            "Shows which segments drive 80% of the value."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "source": {"type": "string", "enum": ["ga4", "gsc"]},
                "metric": {"type": "string"},
                "dimension": {"type": "string"},
                "date_range": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                    },
                    "required": ["start", "end"],
                },
            },
            "required": ["property_id", "source", "metric", "dimension", "date_range"],
        },
    },
    {
        "name": "recall_memory",
        "description": (
            "Search prior memory for hypotheses, decisions, goals, and business context "
            "Mahdy has shared. Call this at the start of open-ended questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 8},
            },
            "required": ["property_id", "query"],
        },
    },
    {
        "name": "save_memory",
        "description": (
            "Save a goal, decision, hypothesis, business context, or preference to long-term "
            "memory. Call after the user states something worth remembering."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "kind": {
                    "type": "string",
                    "enum": ["goal", "decision", "hypothesis", "business_context", "preference", "recurring_concern"],
                },
                "text": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "confidence": {
                    "type": "string",
                    "enum": ["explicit", "implied"],
                    "default": "explicit",
                },
                "supersedes_memory_id": {"type": "integer"},
                "expires_after_days": {"type": "integer"},
            },
            "required": ["property_id", "kind", "text"],
        },
    },
    {
        "name": "list_pinned_questions",
        "description": "List all pinned questions for this property.",
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
            },
            "required": ["property_id"],
        },
    },
    {
        "name": "get_property_metadata",
        "description": (
            "Get property business context: name, domain, linked sources, "
            "focus pages, primary conversion events."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
            },
            "required": ["property_id"],
        },
    },
    # ── Core Web Vitals tools ─────────────────────────────────────────────────
    {
        "name": "get_page_cwv",
        "description": (
            "Get the latest Core Web Vitals (LCP, INP, CLS) audit for a specific page. "
            "Returns cwv_status (good/needs_improvement/poor), metric values, and "
            "PageSpeed Insights opportunities."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "url": {"type": "string", "description": "Page path like /blog/my-post or full URL"},
                "strategy": {"type": "string", "enum": ["mobile", "desktop"], "default": "mobile"},
            },
            "required": ["property_id", "url"],
        },
    },
    {
        "name": "get_origin_cwv",
        "description": (
            "Get origin-level Chrome UX Report (CrUX) field data. "
            "Shows real-user p75 metrics and percentage of users in each threshold bucket. "
            "More representative than lab data for high-traffic sites."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "strategy": {"type": "string", "enum": ["mobile", "desktop", "all_traffic"], "default": "mobile"},
            },
            "required": ["property_id"],
        },
    },
    {
        "name": "scan_cwv_problem_pages",
        "description": (
            "Scan all audited pages and list those with poor or needs-improvement CWV status. "
            "Sorted by LCP descending (worst pages first). Use to prioritize performance fixes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "strategy": {"type": "string", "enum": ["mobile", "desktop"], "default": "mobile"},
                "status_filter": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["poor", "needs_improvement"],
                    "description": "Which CWV statuses to include",
                },
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["property_id"],
        },
    },
    {
        "name": "cwv_mobile_desktop_compare",
        "description": (
            "Compare mobile vs desktop Core Web Vitals for the same pages. "
            "Identifies pages where mobile performance is significantly worse than desktop."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["property_id"],
        },
    },
    {
        "name": "cwv_trend",
        "description": (
            "Show the CWV audit history for a specific URL over recent weeks. "
            "Useful for verifying whether a performance fix actually improved scores."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "url": {"type": "string"},
                "strategy": {"type": "string", "enum": ["mobile", "desktop"], "default": "mobile"},
                "days": {"type": "integer", "default": 30, "description": "How many days of history to return"},
            },
            "required": ["property_id", "url"],
        },
    },
    # ── Action tools ──────────────────────────────────────────────────────────
    {
        "name": "gsc_submit_sitemap",
        "description": (
            "Submit a sitemap URL to Google Search Console. "
            "Creates a pending action that requires user confirmation before execution."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "sitemap_url": {"type": "string", "description": "Full sitemap URL, e.g. https://example.com/sitemap.xml"},
            },
            "required": ["property_id", "sitemap_url"],
        },
    },
    {
        "name": "gsc_delete_sitemap",
        "description": (
            "Remove a sitemap from Google Search Console. "
            "DESTRUCTIVE — creates a pending action requiring explicit user confirmation. "
            "Only call this if the user explicitly asks to delete a sitemap."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "sitemap_url": {"type": "string"},
            },
            "required": ["property_id", "sitemap_url"],
        },
    },
    {
        "name": "gsc_inspect_url",
        "description": (
            "Inspect a URL via the Google Search Console URL Inspection API. "
            "Returns indexing status, last crawl date, and coverage state. "
            "Read-only — executes immediately."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "url": {"type": "string", "description": "Full URL to inspect"},
            },
            "required": ["property_id", "url"],
        },
    },
    {
        "name": "run_psi_audit",
        "description": (
            "Trigger a fresh PageSpeed Insights audit for a specific page and store the results. "
            "Returns LCP, INP, CLS, performance score, and optimization opportunities. "
            "Takes 5-10 seconds. Call only when the user explicitly asks for a fresh audit."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "integer"},
                "url": {"type": "string", "description": "Page path or full URL"},
                "strategy": {"type": "string", "enum": ["mobile", "desktop"], "default": "mobile"},
            },
            "required": ["property_id", "url"],
        },
    },
]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

# Tools that require server-injected user_id (never from LLM input)
_USER_SCOPED_TOOLS = frozenset({
    "gsc_submit_sitemap",
    "gsc_delete_sitemap",
    "run_psi_audit",
})


async def dispatch_tool(
    name: str,
    input_dict: dict[str, Any],
    db: AsyncSession,
    user_id: int | None = None,
) -> dict[str, Any]:
    from prism.ai.tools.ga4_tools import compare_periods, query_ga4
    from prism.ai.tools.gsc_tools import query_gsc
    from prism.ai.tools.cross_source_tools import (
        cannibalization_scan,
        content_decay_scan,
        correlate_page_performance,
        intent_vs_outcome,
        serp_opportunity_scan,
        vanity_vs_value_queries,
    )
    from prism.ai.tools.statistical_tools import detect_anomalies, rolling_trend, segment_split
    from prism.ai.tools.memory_tools import (
        get_property_metadata,
        list_pinned_questions,
        recall_memory,
        save_memory,
    )
    from prism.ai.tools.cwv_tools import (
        get_page_cwv,
        get_origin_cwv,
        scan_cwv_problem_pages,
        cwv_mobile_desktop_compare,
        cwv_trend,
    )
    from prism.ai.tools.action_tools import (
        gsc_submit_sitemap,
        gsc_delete_sitemap,
        gsc_inspect_url,
        run_psi_audit,
    )
    from prism.ai.tools.schemas import (
        CannibalizationInput,
        ComparePeriodsInput,
        ContentDecayInput,
        CorrelatePageInput,
        DetectAnomaliesInput,
        GetPropertyMetaInput,
        IntentVsOutcomeInput,
        ListPinnedInput,
        QueryGA4Input,
        QueryGSCInput,
        RecallMemoryInput,
        RollingTrendInput,
        SaveMemoryInput,
        SegmentSplitInput,
        SerpOpportunityInput,
        VanityVsValueInput,
        # CWV schemas
        GetPageCWVInput,
        GetOriginCWVInput,
        ScanCWVProblemsInput,
        CWVMobileDesktopInput,
        CWVTrendInput,
        # Action schemas
        GSCSubmitSitemapInput,
        GSCDeleteSitemapInput,
        GSCInspectURLInput,
        RunPSIAuditInput,
    )

    _map: dict[str, tuple[Any, Any]] = {
        "query_ga4": (query_ga4, QueryGA4Input),
        "query_gsc": (query_gsc, QueryGSCInput),
        "compare_periods": (compare_periods, ComparePeriodsInput),
        "correlate_page_performance": (correlate_page_performance, CorrelatePageInput),
        "intent_vs_outcome": (intent_vs_outcome, IntentVsOutcomeInput),
        "vanity_vs_value_queries": (vanity_vs_value_queries, VanityVsValueInput),
        "cannibalization_scan": (cannibalization_scan, CannibalizationInput),
        "serp_opportunity_scan": (serp_opportunity_scan, SerpOpportunityInput),
        "content_decay_scan": (content_decay_scan, ContentDecayInput),
        "detect_anomalies": (detect_anomalies, DetectAnomaliesInput),
        "rolling_trend": (rolling_trend, RollingTrendInput),
        "segment_split": (segment_split, SegmentSplitInput),
        "recall_memory": (recall_memory, RecallMemoryInput),
        "save_memory": (save_memory, SaveMemoryInput),
        "list_pinned_questions": (list_pinned_questions, ListPinnedInput),
        "get_property_metadata": (get_property_metadata, GetPropertyMetaInput),
        # CWV tools
        "get_page_cwv": (get_page_cwv, GetPageCWVInput),
        "get_origin_cwv": (get_origin_cwv, GetOriginCWVInput),
        "scan_cwv_problem_pages": (scan_cwv_problem_pages, ScanCWVProblemsInput),
        "cwv_mobile_desktop_compare": (cwv_mobile_desktop_compare, CWVMobileDesktopInput),
        "cwv_trend": (cwv_trend, CWVTrendInput),
        # Action tools
        "gsc_submit_sitemap": (gsc_submit_sitemap, GSCSubmitSitemapInput),
        "gsc_delete_sitemap": (gsc_delete_sitemap, GSCDeleteSitemapInput),
        "gsc_inspect_url": (gsc_inspect_url, GSCInspectURLInput),
        "run_psi_audit": (run_psi_audit, RunPSIAuditInput),
    }

    if name not in _map:
        return {"error": f"Unknown tool: {name}"}

    fn, schema_cls = _map[name]
    try:
        parsed = schema_cls.model_validate(input_dict)
        # user_id is server-injected for mutation tools — never trusted from LLM input
        if name in _USER_SCOPED_TOOLS:
            if user_id is None:
                return {"error": "This action requires an authenticated user — user_id not available in this context."}
            return await fn(parsed, db, user_id=user_id)
        return await fn(parsed, db)
    except Exception as exc:
        return {"error": str(exc), "tool": name}
