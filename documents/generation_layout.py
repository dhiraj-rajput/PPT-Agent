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
    "executive_summary": 1.2,
    "scope_of_work": 1.5,
    "pricing_table": 0.4,
    "competitive_positioning": 0.8,
    "timeline": 0.4,
    "terms": 0.5,
    "next_steps": 0.3,
    "strategic_context_intro": 0.5,
    "strategic_context": 0.8,
    "proposed_solution": 1.5,
    "investment_intro": 0.4,
    "company_profile": 0.8,
    "past_performance": 0.8,
    "technical_approach": 1.2,
    "management_plan": 0.8,
    "appendix": 0.5,
}

_TOTAL_WEIGHT = sum(SECTION_WEIGHTS.values())


def section_word_budget(section_key: str, target_total_pages: int = 10) -> Tuple[int, int]:
    """
    Returns a (min_words, max_words) range for a section.
    
    Now correctly uses target_total_pages to proportion word budgets
    across sections based on their relative weights.
    """
    weight = SECTION_WEIGHTS.get(section_key, 1.0)
    # Proportional allocation: this section's share of total pages
    section_pages = (weight / _TOTAL_WEIGHT) * target_total_pages
    target_words = int(WORDS_PER_PAGE * section_pages)
    # Clamp to reasonable minimum
    target_words = max(target_words, 80)
    min_words = int(target_words * 0.75)
    max_words = int(target_words * 1.35)
    return (min_words, max_words)


def estimate_section_pages(section_key: str, word_count: int) -> float:
    """Estimate how many pages a section with given word count will occupy."""
    return max(0.5, word_count / WORDS_PER_PAGE)


def total_document_pages(sections: Dict[str, int]) -> float:
    """Estimate total pages given a dict of {section_key: word_count}."""
    return sum(estimate_section_pages(k, v) for k, v in sections.items())
