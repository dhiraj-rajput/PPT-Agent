"""
ai/mode.py
----------
Global AI / rule-based master switch.

Controlled by a single environment variable:

    AI_MODE=ai            -> always try AI first, fall back to rules on failure
    AI_MODE=rule_based     -> never call AI, always use the rule-based path
    AI_MODE=auto (default) -> same behaviour as "ai" (AI-first with fallback);
                              kept as a distinct value so it can be tuned later
                              (e.g. per time-of-day / budget) without another
                              migration.

Every agent that has both an AI path and a rule-based path should route
through `run_with_fallback()` below rather than checking `settings.AI_MODE`
itself. That keeps the fallback behaviour (including the 429 rate-limit
carve-out you asked for) consistent everywhere.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Callable, Optional, TypeVar

from pipeline.ai.client import RateLimitError, AIUnavailableError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AIMode(str, Enum):
    AI = "ai"
    RULE_BASED = "rule_based"
    AUTO = "auto"


def get_ai_mode() -> AIMode:
    try:
        from utils.db_client import get_collection
        col = get_collection("system_settings")
        record = col.find_one({"key": "ai_mode"})
        if record and "value" in record:
            return AIMode(record["value"])
    except Exception:
        pass

    from config.settings import settings
    raw = str(getattr(settings, "AI_MODE", "auto") or "auto").strip().lower()
    try:
        return AIMode(raw)
    except ValueError:
        logger.warning(f"[ai.mode] Unrecognised AI_MODE='{raw}', defaulting to 'auto'.")
        return AIMode.AUTO


def ai_enabled() -> bool:
    return get_ai_mode() in (AIMode.AI, AIMode.AUTO)


def run_with_fallback(
    agent_name: str,
    ai_fn: Callable[[], T],
    rule_fn: Callable[[], T],
    *,
    force_mode: Optional[AIMode] = None,
) -> tuple[T, str]:
    """
    Run `ai_fn()` if the AI_MODE allows it, otherwise (or on failure)
    run `rule_fn()`.

    Returns:
        (result, path_used) where path_used is one of
        "ai", "rule_based" — useful for logging/telemetry on the result.

    Behaviour:
        - AI_MODE=rule_based        -> rule_fn() only, ai_fn() never called.
        - AI_MODE=ai / auto         -> ai_fn() first.
            * On RateLimitError     -> log a clear rate-limit notice, fall
                                        back to rule_fn() immediately (no
                                        further AI retries for this call).
            * On any other failure  -> log the error, fall back to rule_fn().
        - Per-agent override: if settings has an uppercase
          "<AGENT_NAME>_MODE" attribute set (e.g. WEBSITE_AGENT_MODE), it
          takes precedence over the master AI_MODE for this call only.
    """
    mode = force_mode or _resolve_mode_for_agent(agent_name)

    if mode == AIMode.RULE_BASED:
        logger.info(f"[{agent_name}] AI_MODE=rule_based — using rule-based path.")
        return rule_fn(), "rule_based"

    try:
        result = ai_fn()
        return result, "ai"
    except RateLimitError as exc:
        logger.warning(
            f"[{agent_name}] AI rate-limited (429) — falling back to rule-based path. {exc}"
        )
    except AIUnavailableError as exc:
        logger.warning(
            f"[{agent_name}] AI unavailable — falling back to rule-based path. {exc}"
        )
    except Exception as exc:  # noqa: BLE001 - agents must never hard-fail because AI failed
        logger.warning(
            f"[{agent_name}] AI path raised an unexpected error — falling back to rule-based path. {exc}"
        )

    return rule_fn(), "rule_based"


def _resolve_mode_for_agent(agent_name: str) -> AIMode:
    """Check for a per-agent override (e.g. WEBSITE_AGENT_MODE) before
    falling back to the master AI_MODE toggle."""
    from config.settings import settings
    override_attr = f"{agent_name.upper()}_MODE"
    override_val = getattr(settings, override_attr, None)
    if override_val:
        try:
            return AIMode(str(override_val).strip().lower())
        except ValueError:
            logger.warning(f"[ai.mode] Unrecognised {override_attr}='{override_val}', ignoring.")
    return get_ai_mode()
