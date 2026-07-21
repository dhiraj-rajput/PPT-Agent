"""
documents/layout_planner.py
----------------------------
Intelligent page layout planning engine for professional document generation.

Prevents orphan/widow lines, empty pages, and mis-paginated content by
pre-calculating page assignments before document rendering.

Key concepts:
- Orphan: First line of a paragraph alone at the bottom of a page
- Widow: Last line of a paragraph alone at the top of a new page
- Min lines rule: At least 3 lines of content must appear together
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Page geometry constants (Letter size, in lines)
# --------------------------------------------------------------------------

# Letter page: 8.5" x 11", margins 0.75" top/bottom, header 0.4", footer 0.35"
# Usable height: ~9.5 inches at 72pt/inch = ~684pt
# Default body font: 11pt with 1.15 line spacing => ~12.65pt/line
# Available lines per page: 684 / 12.65 ≈ 54 lines
LINES_PER_PAGE = 54

# Words per line (average for 11pt, ~6.5" text width)
WORDS_PER_LINE = 12

# Minimum lines that must appear together (orphan/widow control)
MIN_LINES_TOGETHER = 3

# Lines consumed by section headings (title + spacing)
SECTION_HEADING_LINES = 3

# Lines consumed by subheadings
SUBHEADING_LINES = 2

# Minimum lines remaining on a page before we force a page break for a section
MIN_LINES_FOR_NEW_SECTION = 8

# Lines consumed by a table row
TABLE_ROW_LINES = 1.5  # approximate

# A table with this many or more rows gets its own page break
LARGE_TABLE_ROW_THRESHOLD = 6


@dataclass
class ContentBlock:
    """Represents a single renderable unit of content."""
    type: str  # 'paragraph', 'subheading', 'bullets', 'numbered', 'table', 'signature', 'spacer'
    content: Any  # The block dict from the section config
    estimated_lines: int = 1
    page_break_before: bool = False

    def __post_init__(self):
        if self.estimated_lines <= 0:
            self.estimated_lines = 1


@dataclass
class PageAssignment:
    """Tracks which content blocks go on each page."""
    page_number: int
    blocks: List[ContentBlock] = field(default_factory=list)
    lines_used: int = 0

    @property
    def lines_remaining(self) -> int:
        return max(0, LINES_PER_PAGE - self.lines_used)

    @property
    def is_nearly_full(self) -> bool:
        return self.lines_remaining < MIN_LINES_TOGETHER + 1


class LayoutPlanner:
    """
    Pre-calculates page assignments for document content blocks.
    Enforces orphan/widow rules and prevents empty or near-empty pages.
    """

    def __init__(self):
        self.pages: List[PageAssignment] = []
        self._current_page = PageAssignment(page_number=1)
        self.pages.append(self._current_page)

    def _new_page(self) -> PageAssignment:
        """Add a new page and make it current."""
        page = PageAssignment(page_number=len(self.pages) + 1)
        self.pages.append(page)
        self._current_page = page
        return page

    def _add_block(self, block: ContentBlock) -> None:
        """Add a block to the current page, starting a new page if needed."""
        if block.page_break_before:
            if self._current_page.lines_used > 0:
                self._new_page()

        # Check if block fits on current page
        if self._current_page.lines_used + block.estimated_lines > LINES_PER_PAGE:
            # Check orphan rule: don't leave < MIN_LINES_TOGETHER on current page
            remaining = self._current_page.lines_remaining
            if remaining < MIN_LINES_TOGETHER:
                self._new_page()
            else:
                # Split: put what fits on current page, rest on next
                # For simplicity, if the block is a paragraph/bullets, split
                # For tables, move the whole block to next page
                if block.type in ('table',) or block.estimated_lines > LINES_PER_PAGE // 2:
                    self._new_page()
                else:
                    # Allow overflow — Word/LibreOffice will handle natural wrap
                    pass

        self._current_page.blocks.append(block)
        self._current_page.lines_used += block.estimated_lines

    def plan_section(self, section: Dict[str, Any]) -> List[ContentBlock]:
        """
        Plan the layout for a section, returning content blocks with
        page_break_before flags set appropriately.
        """
        planned_blocks: List[ContentBlock] = []

        # Section heading
        heading_block = ContentBlock(
            type='section_heading',
            content={'text': section.get('title', '')},
            estimated_lines=SECTION_HEADING_LINES,
            page_break_before=section.get('page_break_before', False),
        )

        # Check if there's enough room for heading + at least MIN_LINES_FOR_NEW_SECTION more
        if (not heading_block.page_break_before and
                self._current_page.lines_remaining < MIN_LINES_FOR_NEW_SECTION):
            heading_block.page_break_before = True

        planned_blocks.append(heading_block)
        self._add_block(heading_block)

        # Process content blocks
        for block_dict in section.get('blocks', []):
            estimated = self._estimate_block_lines(block_dict)
            cb = ContentBlock(
                type=block_dict.get('type', 'paragraph'),
                content=block_dict,
                estimated_lines=estimated,
                page_break_before=False,
            )

            # Large table: force page break before
            if cb.type == 'table':
                rows = block_dict.get('rows', [])
                if len(rows) >= LARGE_TABLE_ROW_THRESHOLD:
                    if self._current_page.lines_used > SECTION_HEADING_LINES:
                        cb.page_break_before = True

            # Subheading: don't leave it at page bottom (widow)
            if cb.type == 'subheading':
                if self._current_page.lines_remaining < SUBHEADING_LINES + MIN_LINES_TOGETHER:
                    cb.page_break_before = True

            planned_blocks.append(cb)
            self._add_block(cb)

        return planned_blocks

    def _estimate_block_lines(self, block: Dict[str, Any]) -> int:
        """Estimate how many lines a content block will consume."""
        btype = block.get('type', 'paragraph')

        if btype == 'paragraph':
            text = str(block.get('text', ''))
            words = len(text.split())
            lines = math.ceil(words / WORDS_PER_LINE) + 1  # +1 for spacing
            return max(2, lines)

        elif btype == 'subheading':
            return SUBHEADING_LINES

        elif btype in ('bullets', 'numbered'):
            items = block.get('items', [])
            total_lines = 0
            for item in items:
                words = len(str(item).split())
                total_lines += math.ceil(words / WORDS_PER_LINE) + 1
            return max(len(items), total_lines)

        elif btype == 'table':
            headers = block.get('headers', [])
            rows = block.get('rows', [])
            return int((len(rows) + 1) * TABLE_ROW_LINES) + 2  # +2 for spacing

        elif btype == 'signature':
            return 5

        elif btype == 'spacer':
            return 1

        return 2

    def get_total_pages(self) -> int:
        """Return the estimated total number of pages."""
        return len(self.pages)

    def get_page_summary(self) -> List[Dict[str, Any]]:
        """Return a human-readable summary of page assignments."""
        summary = []
        for page in self.pages:
            summary.append({
                'page': page.page_number,
                'lines_used': page.lines_used,
                'lines_remaining': page.lines_remaining,
                'block_count': len(page.blocks),
                'block_types': [b.type for b in page.blocks],
            })
        return summary


def plan_document_layout(sections: List[Dict[str, Any]]) -> Tuple[LayoutPlanner, List[Dict[str, Any]]]:
    """
    Plan the layout for an entire document.
    
    Returns:
        (planner, enriched_sections) where enriched_sections has page_break_before
        flags updated based on layout planning.
    """
    planner = LayoutPlanner()
    enriched_sections = []

    for i, section in enumerate(sections):
        planned_blocks = planner.plan_section(section)
        enriched_section = dict(section)
        # Update page_break_before based on planning
        if planned_blocks and planned_blocks[0].page_break_before:
            enriched_section['page_break_before'] = True
        enriched_sections.append(enriched_section)

    logger.info(
        f"[LayoutPlanner] Document planned: {planner.get_total_pages()} pages, "
        f"{len(sections)} sections"
    )
    return planner, enriched_sections
