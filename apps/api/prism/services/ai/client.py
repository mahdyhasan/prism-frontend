"""Async Anthropic client wrapper.

Every call goes through `call_claude` so it gets logged to ClaudeCallLog
(success and error paths). The LLM is never asked to compute numbers — the
caller passes precomputed values in the prompt.
"""
from __future__ import annotations

from time import perf_counter

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from prism.config import get_settings
from prism.core.logging import logger
from prism.db.models.insight import ClaudeCallLog

# Default models. Sonnet for narrative generation, Haiku for cheap routing /
# classification / per-anomaly narration.
NARRATIVE_MODEL = "claude-sonnet-4-7-20251222"
CHEAP_MODEL = "claude-haiku-4-5-20251001"


_claude_client: AsyncAnthropic | None = None


def get_claude_client() -> AsyncAnthropic:
    global _claude_client
    if _claude_client is None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            msg = "ANTHROPIC_API_KEY is not configured."
            raise RuntimeError(msg)
        _claude_client = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=120.0,
            max_retries=1,
        )
    return _claude_client


def _reset_claude_client() -> None:
    """Reset the cached client. Call in tests that need a fresh instance."""
    global _claude_client
    _claude_client = None


async def call_claude(
    *,
    purpose: str,
    model: str,
    system: str,
    messages: list[dict],
    max_tokens: int,
    db: AsyncSession,
    tenant_id: int,
    property_id: int | None = None,
) -> str:
    """Call Claude and log the call. Returns the response text.

    The caller is responsible for parsing JSON from the text if the prompt
    expects structured output. Errors are logged and re-raised.
    """
    client = get_claude_client()
    started = perf_counter()
    input_tokens = 0
    output_tokens = 0
    status = "success"
    error_text: str | None = None
    text_out = ""

    try:
        response = await client.messages.create(
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
        )
        # Extract concatenated text from all text blocks.
        parts: list[str] = []
        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                parts.append(getattr(block, "text", ""))
        text_out = "".join(parts)

        usage = getattr(response, "usage", None)
        if usage is not None:
            input_tokens = getattr(usage, "input_tokens", 0) or 0
            output_tokens = getattr(usage, "output_tokens", 0) or 0
        return text_out
    except Exception as exc:
        status = "error"
        error_text = f"{type(exc).__name__}: {exc}"
        logger.error(
            "Claude call failed",
            purpose=purpose,
            model=model,
            tenant_id=tenant_id,
            property_id=property_id,
            error=error_text,
        )
        raise
    finally:
        latency_ms = int((perf_counter() - started) * 1000)
        try:
            db.add(ClaudeCallLog(
                tenant_id=tenant_id,
                property_id=property_id,
                purpose=purpose,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                status=status,
                error=error_text,
            ))
            await db.flush()
        except Exception as log_exc:  # pragma: no cover — never let logging mask the real error
            logger.error(
                "Failed to persist ClaudeCallLog",
                purpose=purpose,
                model=model,
                error=f"{type(log_exc).__name__}: {log_exc}",
            )
        logger.info(
            "Claude call",
            purpose=purpose,
            model=model,
            status=status,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tenant_id=tenant_id,
            property_id=property_id,
        )
