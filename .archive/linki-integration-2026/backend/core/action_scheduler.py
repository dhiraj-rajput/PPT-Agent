from datetime import datetime
import logging
from typing import Tuple, Any, Optional

logger = logging.getLogger(__name__)

# Fallback warm-up stage caps for legacy calls
STAGE_CAPS = {
    0: {"conn": 5, "msg": 8},
    1: {"conn": 8, "msg": 12},
    2: {"conn": 12, "msg": 18},
    3: {"conn": 15, "msg": 25},
}
STEADY_STATE_CAPS = {"conn": 20, "msg": 35}

def get_effective_account_caps(account: Any) -> Tuple[int, int]:
    """
    Calculates separate (effective_conn_cap, effective_msg_cap) for a LinkedInAccount row.
    Uses account.daily_connection_cap and account.daily_message_cap as ceilings,
    and applies a linear ramp-up ladder (days_active * 2 for conn, days_active * 5 for msg)
    if ramp_up_enabled is True.
    """
    if not account:
        return 5, 8

    conn_ceiling = getattr(account, "daily_connection_cap", 20) or 20
    msg_ceiling = getattr(account, "daily_message_cap", 50) or 50

    ramp_enabled = getattr(account, "ramp_up_enabled", True)
    if ramp_enabled:
        start_dt = getattr(account, "ramp_start_date", None) or getattr(account, "created_at", None) or datetime.utcnow()
        days_active = max(1, (datetime.utcnow() - start_dt).days + 1)
        conn_cap = min(conn_ceiling, days_active * 2)
        msg_cap = min(msg_ceiling, days_active * 5)
    else:
        conn_cap = conn_ceiling
        msg_cap = msg_ceiling

    logger.debug(f"Account {getattr(account, 'id', 'unknown')} effective caps: conn={conn_cap}, msg={msg_cap}")
    return conn_cap, msg_cap

def get_caps_for_stage(warmup_stage: int) -> Tuple[int, int]:
    """
    Returns the maximum (conn_cap, msg_cap) allowed for the given warm-up stage (legacy fallback).
    """
    caps = STAGE_CAPS.get(warmup_stage, STEADY_STATE_CAPS)
    return caps["conn"], caps["msg"]

def get_account_caps(account_or_stage: Any) -> Tuple[int, int]:
    """
    Backward-compatible helper. If passed a LinkedInAccount object, calls get_effective_account_caps.
    If passed an integer warmup_stage, calls get_caps_for_stage.
    """
    if isinstance(account_or_stage, int):
        return get_caps_for_stage(account_or_stage)
    return get_effective_account_caps(account_or_stage)

