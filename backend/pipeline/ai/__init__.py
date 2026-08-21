"""
ai/
---
Shared AI infrastructure for the whole project: one Ollama Cloud client
(ai.client) and one master AI/rule-based toggle with automatic
429-aware fallback (ai.mode). Every agent (website, linkedin,
google_search, compactor, RFP parsing, RFP response / BidForge-style
document generation) plugs into this instead of rolling its own LLM
calling code.
"""

from pipeline.ai.client import (
    AIUnavailableError,
    OllamaAIClient,
    RateLimitError,
    get_ai_client,
)
from pipeline.ai.mode import AIMode, ai_enabled, get_ai_mode, run_with_fallback

__all__ = [
    "AIMode",
    "AIUnavailableError",
    "OllamaAIClient",
    "RateLimitError",
    "ai_enabled",
    "get_ai_client",
    "get_ai_mode",
    "run_with_fallback",
]
