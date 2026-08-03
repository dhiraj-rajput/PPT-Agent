import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# Warm-up stages configuration as defined in Section 4.3 of the plan:
# Stage 0: 3-5 requests, 5-8 messages
# Stage 1: 5-8 requests, 8-12 messages
# Stage 2: 8-12 requests, 12-18 messages
# Stage 3: 12-15 requests, 18-25 messages
# Steady State (4+): 15-20 requests, 25-35 messages
STAGE_CAPS = {
    0: {"conn": 5, "msg": 8},
    1: {"conn": 8, "msg": 12},
    2: {"conn": 12, "msg": 18},
    3: {"conn": 15, "msg": 25},
}
STEADY_STATE_CAPS = {"conn": 20, "msg": 35}

def get_caps_for_stage(warmup_stage: int) -> Tuple[int, int]:
    """
    Returns the maximum (conn_cap, msg_cap) allowed for the given warm-up stage.
    """
    caps = STAGE_CAPS.get(warmup_stage, STEADY_STATE_CAPS)
    return caps["conn"], caps["msg"]

def get_account_caps(warmup_stage: int) -> Tuple[int, int]:
    """
    Helper to calculate current caps for an account.
    In Phase 1 MVP, this returns fixed conservative caps.
    In Phase 2, this will support stochastic volume limits (randomized by ±30%).
    """
    conn_cap, msg_cap = get_caps_for_stage(warmup_stage)
    logger.debug(f"Calculated caps for stage {warmup_stage}: connections={conn_cap}, messages={msg_cap}")
    return conn_cap, msg_cap
