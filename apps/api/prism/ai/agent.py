from __future__ import annotations

import json
from pathlib import Path
from typing import AsyncGenerator

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401 — kept for type annotation clarity

from prism.ai.client import NARRATIVE_MODEL
from prism.ai.tools import TOOL_DEFINITIONS, dispatch_tool
from prism.core.logging import logger
from prism.db.session import get_session_factory

MAX_TOOL_CALLS = 10


def _load_system_prompt() -> str:
    path = Path(__file__).parent / "prompts" / "chatbot_system.md"
    return path.read_text(encoding="utf-8")


def _build_system(
    property_id: int,
    scope: str,
    memories: list[dict],
    property_meta: dict | None = None,
) -> str:
    base = _load_system_prompt()

    context_block = "\n\n---\n## Current session context\n"
    context_block += f"**Property ID: {property_id}** — use this for every tool call that requires property_id.\n"
    context_block += f"Source scope: {scope}\n"

    if property_meta and not property_meta.get("error"):
        context_block += (
            f"Property name: {property_meta.get('display_name', 'Unknown')}\n"
            f"Domain: {property_meta.get('domain') or 'not set'}\n"
            f"GA4 linked: {property_meta.get('ga4_linked', False)}\n"
            f"GSC linked: {property_meta.get('gsc_linked', False)}\n"
        )
        if property_meta.get("focus_pages"):
            context_block += f"Focus pages: {', '.join(property_meta['focus_pages'])}\n"
        if property_meta.get("primary_conversions"):
            context_block += f"Primary conversions: {', '.join(property_meta['primary_conversions'])}\n"

    if memories:
        context_block += "\n## Prior context (from memory)\n"
        for m in memories[:8]:
            context_block += f"- [{m['kind']}] {m['text']}\n"

    return base + context_block


async def run_agent_streaming(
    property_id: int,
    user_id: int,
    session_id: int,
    user_message: str,
    source_scope: str = "all",
) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE-formatted strings.

    SSE event types:
    - tool_start:  {"type": "tool_start",  "tool": "query_ga4", "input": {...}}
    - tool_result: {"type": "tool_result", "tool": "query_ga4", "row_count": N, "truncated": bool}
    - text_delta:  {"type": "text_delta",  "text": "..."}
    - done:        {"type": "done",        "tool_calls_count": N}
    - error:       {"type": "error",       "message": "..."}
    """
    from prism.config import get_settings
    from prism.ai.tools.memory_tools import recall_memory
    from prism.ai.tools.schemas import RecallMemoryInput

    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    factory = get_session_factory()
    tool_calls_count = 0

    try:
        # 1. Pre-fetch property metadata + memory in parallel (both non-fatal)
        memories: list[dict] = []
        property_meta: dict | None = None
        try:
            async with factory() as db:
                from prism.ai.tools.memory_tools import get_property_metadata
                from prism.ai.tools.schemas import GetPropertyMetaInput

                mem_input = RecallMemoryInput(property_id=property_id, query=user_message)
                meta_input = GetPropertyMetaInput(property_id=property_id)

                mem_result = await recall_memory(mem_input, db)
                memories = mem_result.get("memories", [])

                property_meta = await get_property_metadata(meta_input, db)
        except Exception:
            pass  # Non-fatal — agent can still run without upfront context

        system_prompt = _build_system(property_id, source_scope, memories, property_meta)

        # 2. Seed the message list
        messages: list[dict] = [{"role": "user", "content": user_message}]

        # 3. Agentic loop — single DB session for all tool calls in this request
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

                # Append assistant turn so future calls have full context
                messages.append({"role": "assistant", "content": response.content})

                if response.stop_reason == "end_turn":
                    for block in response.content:
                        if hasattr(block, "text"):
                            text = block.text
                            chunk_size = 50
                            for i in range(0, len(text), chunk_size):
                                yield f"data: {json.dumps({'type': 'text_delta', 'text': text[i:i + chunk_size]})}\n\n"
                    break

                if response.stop_reason == "tool_use":
                    tool_results = []

                    for block in response.content:
                        if block.type != "tool_use":
                            continue

                        tool_calls_count += 1
                        tool_name = block.name
                        tool_input = block.input

                        yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name, 'input': tool_input})}\n\n"

                        try:
                            result = await dispatch_tool(
                                tool_name, tool_input, db, user_id=user_id,
                            )
                        except Exception as exc:
                            result = {"error": str(exc), "tool": tool_name}

                        # Determine row count from whichever list key is present
                        row_count = len(
                            result.get(
                                "rows",
                                result.get(
                                    "pages",
                                    result.get(
                                        "opportunities",
                                        result.get(
                                            "anomalies",
                                            result.get("trend", []),
                                        ),
                                    ),
                                ),
                            )
                        )
                        yield f"data: {json.dumps({'type': 'tool_result', 'tool': tool_name, 'row_count': row_count, 'truncated': result.get('truncated', False)})}\n\n"

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        })

                    messages.append({"role": "user", "content": tool_results})

                    if tool_calls_count >= MAX_TOOL_CALLS:
                        # Cap reached — ask Claude to summarise with what it has
                        messages.append({
                            "role": "user",
                            "content": (
                                "You have reached the maximum tool call limit. "
                                "Please summarise your findings with the data you have gathered so far."
                            ),
                        })
                        final = await client.messages.create(
                            model=NARRATIVE_MODEL,
                            max_tokens=4096,
                            system=system_prompt,
                            messages=messages,
                        )
                        for block in final.content:
                            if hasattr(block, "text"):
                                text = block.text
                                chunk_size = 50
                                for i in range(0, len(text), chunk_size):
                                    yield f"data: {json.dumps({'type': 'text_delta', 'text': text[i:i + chunk_size]})}\n\n"
                        break
                else:
                    # Unexpected stop_reason — exit cleanly
                    break

        yield f"data: {json.dumps({'type': 'done', 'tool_calls_count': tool_calls_count})}\n\n"

    except Exception as exc:
        logger.error("Agent loop error", error=str(exc), property_id=property_id)
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
