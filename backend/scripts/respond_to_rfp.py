"""
scripts/respond_to_rfp.py
-------------------------
CLI entry point for proposal generation supporting prime, subcontract, partnership, and bidforge modes.
Refactored to route everything through ProposalGenerator.
"""

import argparse
import sys
import logging
from pathlib import Path
from datetime import datetime

# Setup stdout UTF-8
if hasattr(sys.stdout, "reconfigure"):
    getattr(sys.stdout, "reconfigure")(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from documents.rfp_response.rfp_parser import RFPParser
from documents.unified_generator import ProposalGenerator
from utils.helpers import setup_logger
from utils.db_client import get_collection, close_connection

logger = setup_logger("respond_to_rfp")

def _find_winner(solicitation: str) -> str:
    try:
        col = get_collection("rfps")
        rfp = col.find_one({"solicitation_number": solicitation})
        if rfp:
            return rfp.get("award", {}).get("awardee_name", "Unknown")
    except Exception:
        pass
    return "Unknown"

def _load_profile(company_name: str) -> dict:
    try:
        col = get_collection("company_profiles")
        import re
        doc = col.find_one({"company_name": {"$regex": re.escape(company_name), "$options": "i"}})
        if doc:
            doc.pop("_id", None)
            return doc
    except Exception:
        pass
    return {"company_name": company_name}

def main():
    parser = argparse.ArgumentParser(description="OrbitAvanya Proposal Generator CLI")
    parser.add_argument("--solicitation", "-s", type=str, default=None)
    parser.add_argument("--mode", "-m", type=str, choices=["prime", "subcontract", "partnership"], default="prime")
    parser.add_argument("--winner", "-w", type=str, default=None)
    parser.add_argument("--workshare", type=float, default=15.0)

    args = parser.parse_args()

    if args.mode != "partnership" and not args.solicitation:
        print("Error: --solicitation is required for prime and subcontract modes.")
        sys.exit(1)
    if args.mode == "partnership" and not args.winner:
        print("Error: --winner is required for partnership mode.")
        sys.exit(1)

    sol_num = args.solicitation or "N/A"
    out_dir = PROJECT_ROOT / "output" / "pdf"
    out_dir.mkdir(parents=True, exist_ok=True)
    output_pdf = str(out_dir / f"{sol_num}_{args.mode}_proposal.pdf")

    generator = ProposalGenerator(project_root=str(PROJECT_ROOT))
    rfp_data = {}

    if args.mode in ("prime", "subcontract"):
        parser_obj = RFPParser(sol_num, project_root=str(PROJECT_ROOT))
        pdf_texts = parser_obj.extract_text_from_pdfs()
        rfp_data = parser_obj.parse_requirements(pdf_texts)

    winner_name = args.winner or _find_winner(sol_num)
    winner_profile = _load_profile(winner_name) if winner_name != "Unknown" else {}

    print(f"\nGenerating {args.mode.upper()} proposal for {sol_num}...")
    pdf_path = generator.generate(
        mode=args.mode,
        rfp_data=rfp_data,
        output_path=output_pdf,
        winner_name=winner_name,
        winner_profile=winner_profile,
        partner_profile=winner_profile,
        workshare=args.workshare
    )

    print(f"SUCCESS: Generated proposal PDF at {pdf_path}")

if __name__ == "__main__":
    main()
