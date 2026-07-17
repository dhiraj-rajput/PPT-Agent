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

from pipeline.ai.client import get_ai_client, OllamaAIClient, RateLimitError, AIUnavailableError
from pipeline.ai.mode import get_ai_mode, ai_enabled, run_with_fallback, AIMode

__all__ = [
    "get_ai_client",
    "OllamaAIClient",
    "RateLimitError",
    "AIUnavailableError",
    "get_ai_mode",
    "ai_enabled",
    "run_with_fallback",
    "AIMode",
]
