from __future__ import annotations

from functools import lru_cache

import anthropic

from prism.config import get_settings

# Model constants
NARRATIVE_MODEL = "claude-sonnet-4-6"
CHEAP_MODEL = "claude-haiku-4-5"


@lru_cache
def get_anthropic_client() -> anthropic.Anthropic:
    settings = get_settings()
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)
