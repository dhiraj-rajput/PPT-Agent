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
    wizard_config: Optional[str] = None,
    parsed_rfp_json_path: Optional[str] = None,
) -> str:
    """
    parsed_rfp_json_path: if the caller already ran parse_uploaded_rfp for
    this exact RFP (e.g. the /rfp-respond/analyze endpoint, which runs parse
    + outline + clarifying-questions ahead of generation so the wizard can
    show real, RFP-specific questions), pass the path to that cached JSON
    here to skip re-parsing entirely. Re-parsing a large tender can mean
    dozens of chunked LLM calls; there is no reason to pay that cost twice
    for the same upload.
    """
    from documents.bidforge.parse import parse_uploaded_rfp
    from documents.bidforge.inventory import analyze_inventory
    from documents.bidforge.competitor_intel import gather_competitor_intel
    from documents.bidforge.summarise import summarise_pricing_strategy
    from documents.bidforge.document_generator import generate_final_document

    if parsed_rfp_json_path and Path(parsed_rfp_json_path).exists():
        import json as _json
        print(f"\nStep 1: Reusing cached RFP analysis from {parsed_rfp_json_path} (already parsed during the pre-generation wizard)...")
        parsed_rfp = _json.loads(Path(parsed_rfp_json_path).read_text(encoding="utf-8"))
    else:
        print("\nStep 1: Parsing uploaded RFP document...")
        parsed_rfp = parse_uploaded_rfp(rfp_file_path, solicitation_number)

    # The inventory/competitor-pricing stages assume a product-catalog RFP
    # (buyer wants specific priced SKUs matched against our catalog). For a
    # capability-based tender (construction/EPC/engineering/services, lump
    # -sum or schedule-of-rates bidding) that model doesn't apply and forcing
    # it in produces irrelevant "our_price"/"competitor price" noise that has
    # nothing to do with how the RFP is actually evaluated. Skip both stages
    # for that RFP type; document_generator.py handles empty inventory/
    # competitor_intel dicts fine (they're informational context, not a hard
    # dependency).
    rfp_type = parsed_rfp.get("rfp_type", "capability_tender")
    if rfp_type == "capability_tender":
        print(f"\nStep 2: RFP classified as '{rfp_type}' — skipping product-catalog inventory/competitor "
              f"pricing matching (not applicable to a capability-based tender).")
        inventory = {"items": [], "overall_summary": "Not applicable -- capability-based tender, not a product-catalog RFP."}
        competitor_intel = {"items": []}
    else:
        print("\nStep 2: Exploring — checking inventory against requirements...")
        inventory = analyze_inventory(parsed_rfp)

        print("\nStep 3: Exploring — gathering competitor / market pricing intelligence...")
        competitor_intel = gather_competitor_intel(parsed_rfp, inventory)

    print("\nStep 4: Synthesizing pricing strategy...")
    strategy = summarise_pricing_strategy(parsed_rfp, inventory, competitor_intel)

    print("\nStep 5: Generating final proposal document...")
    final_path = generate_final_document(
        parsed_rfp, inventory, competitor_intel, strategy, output_name, template_path, wizard_config
    )

    print(f"\nStep 6: Done. Output: {final_path}")
    return final_path
