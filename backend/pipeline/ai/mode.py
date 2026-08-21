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
from collections.abc import Callable
from enum import Enum
from typing import TypeVar

from pipeline.ai.client import AIUnavailableError, RateLimitError

logger = logging.getLogger(__name__)

T = TypeVar("T")


def strict_ai_enabled() -> bool:
    """When true, run_with_fallback() re-raises AI failures instead of
    silently degrading to the rule-based path.

    The rule-based paths (keyword substring matching, boilerplate templates)
    exist as an emergency "produce *something*" safety net, not as an
    acceptable everyday output path. Silently falling into them is exactly
    what produced short, generic, RFP-unrelated proposals while *looking*
    like the pipeline ran fine (fast, no visible error, generated_via just
    quietly said "rule_based" in a JSON field nobody was checking).

    Enable during development / debugging with BIDFORGE_STRICT_AI=true so a
    misconfigured provider (missing API key, bad model name, timeout) raises
    immediately instead of being masked. Leave off in production only once
    you've confirmed AI calls are reliably succeeding, since a hard failure
    there means no document at all rather than a degraded one.
    """
    from config.settings import settings
    raw = str(getattr(settings, "BIDFORGE_STRICT_AI", "") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


class AIMode(str, Enum):
    AI = "ai"
    RULE_BASED = "rule_based"
    AUTO = "auto"


import time

_ai_mode_cache: dict = {'value': None, 'expires': 0.0}

def get_ai_mode() -> AIMode:
    now = time.monotonic()
    if _ai_mode_cache['value'] is not None and now < _ai_mode_cache['expires']:
        return _ai_mode_cache['value']

    mode_result = None

    try:
        from utils.db_client import _mysql_available, get_sync_db_session
        if _mysql_available:
            from models.sql_models import SystemSettings as SQL_SystemSettings
            from sqlalchemy import select
            with get_sync_db_session() as db:
                stmt = select(SQL_SystemSettings).where(SQL_SystemSettings.key_name == "ai_mode")
                row = db.execute(stmt).scalar_one_or_none()
                if row:
                    val = getattr(row, "value", None)
                    if val:
                        mode_result = AIMode(str(val))
    except Exception:
        pass

    if mode_result is None:
        from config.settings import settings
        raw = str(getattr(settings, "AI_MODE", "auto") or "auto").strip().lower()
        try:
            mode_result = AIMode(raw)
        except ValueError:
            logger.warning(f"[ai.mode] Unrecognised AI_MODE='{raw}', defaulting to 'auto'.")
            mode_result = AIMode.AUTO

    _ai_mode_cache['value'] = mode_result
    _ai_mode_cache['expires'] = now + 60.0
    return mode_result


def ai_enabled() -> bool:
    return get_ai_mode() in (AIMode.AI, AIMode.AUTO)


def run_with_fallback(
    agent_name: str,
    ai_fn: Callable[[], T],
    rule_fn: Callable[[], T],
    *,
    force_mode: AIMode | None = None,
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

    strict = strict_ai_enabled()

    try:
        result = ai_fn()
        return result, "ai"
    except (RateLimitError, AIUnavailableError, Exception) as exc:
        kind = (
            "rate-limited (429)" if isinstance(exc, RateLimitError)
            else "unavailable" if isinstance(exc, AIUnavailableError)
            else "raised an unexpected error"
        )
        if strict:
            logger.error(
                f"[{agent_name}] AI {kind} — BIDFORGE_STRICT_AI is on, re-raising instead "
                f"of falling back to the rule-based path. {exc}",
                exc_info=True,
            )
            raise
        # ERROR (not warning) + traceback: this fallback silently produced
        # generic, RFP-unrelated output before while only ever logging a
        # warning nobody scanned for. Make it loud by default.
        logger.error(
            f"[{agent_name}] AI {kind} — falling back to the rule-based path. "
            f"Output from this stage will be generic/templated, not RFP-specific. {exc}",
            exc_info=True,
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
