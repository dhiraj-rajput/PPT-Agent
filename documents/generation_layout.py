"""
documents/generation_layout.py
-------------------------------
Provides target word budgets and section weights per proposal section
to guide AI text generation and prevent runaway/spillover length.
"""

from __future__ import annotations

from typing import Dict, Tuple

WORDS_PER_PAGE = 480

SECTION_WEIGHTS: Dict[str, float] = {
    "executive_summary": 1.2,        # ~500-600 words
    "scope_of_work": 1.5,            # ~600-750 words
    "pricing_table": 0.4,            # ~150-200 words (mostly table)
    "competitive_positioning": 0.8,  # ~350-400 words
    "timeline": 0.4,                 # ~150-200 words
    "terms": 0.5,                    # ~200-250 words
    "next_steps": 0.3,              # ~100-150 words
    "strategic_context_intro": 0.5,
    "proposed_solution": 1.5,
    "investment_intro": 0.4,
}


def section_word_budget(section_key: str, target_total_pages: int = 10) -> Tuple[int, int]:
    """Returns a (min_words, max_words) range for a section based on its key."""
    weight = SECTION_WEIGHTS.get(section_key, 1.0)
    target_words = int(WORDS_PER_PAGE * weight)
    min_words = int(target_words * 0.7)
    max_words = int(target_words * 1.3)
    return (min_words, max_words)
