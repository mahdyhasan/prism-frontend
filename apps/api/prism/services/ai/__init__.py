"""AI services — Claude wrapper, prompts, detectors, insight orchestration.

Hard rule: the LLM never computes metrics. Detectors (SQL/pandas) compute
numbers and Claude writes the narrative around them.
"""
from prism.services.ai.client import (
    CHEAP_MODEL,
    NARRATIVE_MODEL,
    call_claude,
    get_claude_client,
)

__all__ = [
    "CHEAP_MODEL",
    "NARRATIVE_MODEL",
    "call_claude",
    "get_claude_client",
]
