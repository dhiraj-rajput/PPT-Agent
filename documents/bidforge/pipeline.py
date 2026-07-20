"""
bidforge/pipeline.py
---------------------
Orchestrates the full BidForge pipeline: Parse -> Explore (inventory +
competitor, sequential here for simplicity/log-clarity) -> Summarise -> Generate.

Prints "Step N: ..." lines (same convention respond_to_rfp.py already uses)
so api/routes/rfp_respond.py can scrape progress from the subprocess output the
same way api/routes/proposals.py does for the existing pipelines.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from utils.helpers import setup_logger

logger = setup_logger(__name__)


def run_bidforge_pipeline(
    rfp_file_path: str,
    output_name: str,
    solicitation_number: str = "",
    template_path: Optional[str] = None,
) -> str:
    from documents.bidforge.parse import parse_uploaded_rfp
    from documents.bidforge.inventory import analyze_inventory
    from documents.bidforge.competitor_intel import gather_competitor_intel
    from documents.bidforge.summarise import summarise_pricing_strategy
    from documents.bidforge.document_generator import generate_final_document

    print("\nStep 1: Parsing uploaded RFP document...")
    parsed_rfp = parse_uploaded_rfp(rfp_file_path, solicitation_number)

    print("\nStep 2: Exploring — checking inventory against requirements...")
    inventory = analyze_inventory(parsed_rfp)

    print("\nStep 3: Exploring — gathering competitor / market pricing intelligence...")
    competitor_intel = gather_competitor_intel(parsed_rfp, inventory)

    print("\nStep 4: Synthesizing pricing strategy...")
    strategy = summarise_pricing_strategy(parsed_rfp, inventory, competitor_intel)

    print("\nStep 5: Generating final proposal document...")
    final_path = generate_final_document(
        parsed_rfp, inventory, competitor_intel, strategy, output_name, template_path
    )

    print(f"\nStep 6: Done. Output: {final_path}")
    return final_path
