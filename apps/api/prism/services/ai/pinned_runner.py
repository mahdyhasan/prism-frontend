"""Pinned question re-run service.

Loads the pinned_rerun.md system prompt, gathers context (prior runs, property
metadata, memories), runs the agent loop (with full tool access, max 8 calls),
and persists the structured JSON answer to PinnedQuestionRun.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from anthropic import AsyncAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.services.ai.client import NARRATIVE_MODEL
from prism.ai.tools import TOOL_DEFINITIONS, dispatch_tool
from prism.config import get_settings
from prism.core.logging import logger
from prism.db.models.chat import ChatMemory, PinnedQuestion, PinnedQuestionRun
from prism.db.models.property import Property
from prism.db.session import get_session_factory

MAX_TOOL_CALLS = 8  # Tighter budget for pinned re-runs per prompt spec

_FALLBACK_RESPONSE: dict = {
    "diff_headline": "Run completed — structured answer could not be parsed.",
    "diff_direction": "insufficient_data",
    "diff_confidence": "insufficient_data",
    "current_answer": {
        "headline": "Could not generate structured answer.",
        "findings": [],
        "interpretation": "The model returned output that did not parse as valid JSON.",
    },
    "comparison_to_prior": {
        "prior_run_date": None,
        "what_changed": [],
        "what_held": None,
    },
    "recommendations": [],
    "reframe": None,
}


def resolve_date_range(strategy: str) -> tuple[date, date]:
    """Convert a date_range_strategy string to (start, end) dates.

    All end dates are yesterday (most recent complete day).
    """
    today = date.today()
    yesterday = today - timedelta(days=1)

    match strategy:
        case "rolling_7d":
            return today - timedelta(days=7), yesterday
        case "rolling_28d":
            return today - timedelta(days=28), yesterday
        case "rolling_90d":
            return today - timedelta(days=90), yesterday
        case "last_12m":
            return today - timedelta(days=365), yesterday
        case "mtd":
            return today.replace(day=1), yesterday
        case "qtd":
            month = today.month
            qstart_month = ((month - 1) // 3) * 3 + 1
            return today.replace(month=qstart_month, day=1), yesterday
        case "ytd":
            return today.replace(month=1, day=1), yesterday
        case _:
            logger.warning("Unknown date_range_strategy; defaulting to rolling_28d", strategy=strategy)
            return today - timedelta(days=28), yesterday


def _load_pinned_prompt() -> str:
    path = Path(__file__).parent.parent.parent / "ai" / "prompts" / "pinned_rerun.md"
    return path.read_text(encoding="utf-8")


def _strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\n?", "", t)
        t = re.sub(r"\n?```$", "", t.strip())
    return t.strip()


def _extract_json_object(text: str) -> str:
    """Try to extract the outermost {...} block from text."""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


async def _run_agent_for_pin(
    pin: PinnedQuestion,
    prior_runs: list[PinnedQuestionRun],
    property_row: Property,
    memories: list[dict],
    start: date,
    end: date,
) -> str:
    """Run the agent loop with pinned_rerun.md system prompt.

    Returns the raw text output from Claude (caller parses JSON).
    Opens its own DB session for tool dispatch.
    """
    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    base_prompt = _load_pinned_prompt()
    context_block = (
        "\n\n---\n## Run context\n"
        f"Property ID: {pin.property_id}\n"
        f"Property name: {property_row.display_name}\n"
        f"Source scope: {pin.source_scope}\n"
        f"Resolved date range: {start.isoformat()} to {end.isoformat()}\n"
    )
    system_prompt = base_prompt + context_block

    # Build prior runs summary for context
    prior_summary: list[dict] = []
    for run in prior_runs:
        if not run.answer_json:
            continue
        try:
            parsed = json.loads(run.answer_json)
            prior_summary.append({
                "run_at": run.run_at.isoformat() if run.run_at else None,
                "headline": parsed.get("current_answer", {}).get("headline", ""),
                "diff_headline": parsed.get("diff_headline", ""),
                "key_numbers": [
                    f"{c['metric_or_signal']}: {c['current_value']}"
                    for c in (
                        parsed.get("comparison_to_prior", {}).get("what_changed", [])[:3]
                    )
                ],
            })
        except Exception:
            pass

    payload = {
        "pinned_question": {
            "title": pin.title,
            "prompt": pin.prompt,
            "source_scope": pin.source_scope,
            "date_range_strategy": pin.date_range_strategy,
            "resolved_start": start.isoformat(),
            "resolved_end": end.isoformat(),
            "tags": pin.tags or [],
        },
        "prior_runs": prior_summary,
        "property": {
            "id": property_row.id,
            "name": property_row.display_name,
            "ga4_linked": bool(property_row.ga4_property_id),
            "gsc_linked": bool(property_row.gsc_site_url),
        },
        "memory": memories,
        "current_data": "Call tools to fetch fresh data for the analysis.",
    }

    user_message = (
        f"Re-run this pinned question: {pin.prompt}\n\n"
        f"Context payload:\n```json\n{json.dumps(payload, indent=2, default=str)}\n```\n\n"
        "Use tools to fetch fresh data, compare against prior runs, and return the structured JSON."
    )

    messages: list[dict] = [{"role": "user", "content": user_message}]
    tool_calls_count = 0
    full_text = ""

    factory = get_session_factory()
    async with factory() as db:
        while tool_calls_count < MAX_TOOL_CALLS:
            response = await client.messages.create(
                model=NARRATIVE_MODEL,
                max_tokens=4096,
                system=system_prompt,
                tools=TOOL_DEFINITIONS,
                messages=messages,
                stream=False,
            )
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text"):
                        full_text += block.text
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    tool_calls_count += 1
                    try:
                        result = await dispatch_tool(
                            block.name, block.input, db,
                            user_id=pin.user_id,
                        )
                    except Exception as exc:
                        result = {"error": str(exc), "tool": block.name}
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })
                messages.append({"role": "user", "content": tool_results})

                if tool_calls_count >= MAX_TOOL_CALLS:
                    messages.append({
                        "role": "user",
                        "content": (
                            "Tool call budget exhausted (8 calls). "
                            "Synthesise your findings into the structured JSON response now."
                        ),
                    })
                    final = await client.messages.create(
                        model=NARRATIVE_MODEL,
                        max_tokens=4096,
                        system=system_prompt,
                        messages=messages,
                        stream=False,
                    )
                    for block in final.content:
                        if hasattr(block, "text"):
                            full_text += block.text
                    break
            else:
                # Unexpected stop_reason
                break

    return full_text


async def run_pinned_question_async(pin_id: int, run_id: int) -> dict:
    """Main entry point called by the Celery task.

    Fetches pin and run records, orchestrates the agent, and persists the
    structured JSON answer to the PinnedQuestionRun row.
    """
    factory = get_session_factory()

    async with factory() as db:
        pin = (await db.execute(
            select(PinnedQuestion).where(PinnedQuestion.id == pin_id)
        )).scalar_one_or_none()
        if pin is None:
            logger.error("PinnedQuestion not found", pin_id=pin_id)
            return {"error": f"PinnedQuestion {pin_id} not found"}

        run = (await db.execute(
            select(PinnedQuestionRun).where(PinnedQuestionRun.id == run_id)
        )).scalar_one_or_none()
        if run is None:
            logger.error("PinnedQuestionRun not found", run_id=run_id)
            return {"error": f"PinnedQuestionRun {run_id} not found"}

        # Mark as running
        run.run_status = "running"
        await db.commit()

        # Prior completed runs (most recent first, exclude this run)
        prior_result = await db.execute(
            select(PinnedQuestionRun)
            .where(
                PinnedQuestionRun.pin_id == pin_id,
                PinnedQuestionRun.id != run_id,
                PinnedQuestionRun.run_status == "done",
            )
            .order_by(PinnedQuestionRun.run_at.desc())
            .limit(5)
        )
        prior_runs = list(prior_result.scalars().all())

        property_row = (await db.execute(
            select(Property).where(Property.id == pin.property_id)
        )).scalar_one_or_none()
        if property_row is None:
            run.run_status = "failed"
            run.error = f"Property {pin.property_id} not found"
            await db.commit()
            return {"error": run.error}

        memories_result = await db.execute(
            select(ChatMemory.kind, ChatMemory.text)
            .where(
                ChatMemory.property_id == pin.property_id,
                ChatMemory.status == "active",
            )
            .limit(15)
        )
        memories = [{"kind": r.kind, "text": r.text} for r in memories_result.all()]

    start, end = resolve_date_range(pin.date_range_strategy)

    # Run the agent
    try:
        raw_text = await _run_agent_for_pin(pin, prior_runs, property_row, memories, start, end)
        cleaned = _strip_code_fences(raw_text)
        cleaned = _extract_json_object(cleaned)
        answer = json.loads(cleaned)
        status = "done"
        error: str | None = None
    except json.JSONDecodeError:
        logger.warning(
            "Pinned runner: JSON parse failure",
            pin_id=pin_id,
            run_id=run_id,
        )
        answer = {**_FALLBACK_RESPONSE}
        status = "done"  # Still a "done" run — just used the fallback
        error = None
    except Exception as exc:
        logger.error("Pinned runner error", pin_id=pin_id, run_id=run_id, error=str(exc))
        answer = {**_FALLBACK_RESPONSE}
        status = "failed"
        error = str(exc)[:500]

    # Persist result
    async with factory() as db:
        run = (await db.execute(
            select(PinnedQuestionRun).where(PinnedQuestionRun.id == run_id)
        )).scalar_one_or_none()
        if run is not None:
            run.run_status = status
            run.answer_json = json.dumps(answer)
            run.error = error
            await db.commit()

    logger.info(
        "Pinned question run complete",
        pin_id=pin_id, run_id=run_id, status=status,
    )
    return {"status": status, "pin_id": pin_id, "run_id": run_id}


async def rerun_all_due_async() -> dict:
    """Daily sweep: create and dispatch runs for all pinned questions.

    Skips questions that already have a run created today (UTC) so the sweep
    is safe to call multiple times without creating duplicate runs.
    """
    factory = get_session_factory()
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    dispatched = 0

    async with factory() as db:
        all_pins = list((await db.execute(select(PinnedQuestion))).scalars().all())

        for pin in all_pins:
            # Check for an existing run today
            existing = (await db.execute(
                select(PinnedQuestionRun)
                .where(
                    PinnedQuestionRun.pin_id == pin.id,
                    PinnedQuestionRun.run_at >= today_start,
                )
                .limit(1)
            )).scalar_one_or_none()
            if existing is not None:
                continue

            new_run = PinnedQuestionRun(
                pin_id=pin.id,
                run_status="pending",
                answer_json=None,
                error=None,
            )
            db.add(new_run)
            await db.flush()
            run_id = new_run.id

            # Dispatch via Celery (local import avoids circular dependency)
            from prism.workers.celery_app import celery_app
            celery_app.send_task(
                "prism.workers.tasks.run_pinned_question",
                kwargs={"pin_id": pin.id, "run_id": run_id},
            )
            dispatched += 1

        await db.commit()

    logger.info("Pinned question daily rerun sweep complete", dispatched=dispatched)
    return {"dispatched": dispatched}
