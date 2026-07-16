#!/usr/bin/env python3
"""
generate_pitch.py
------------------
CLI orchestrator to extract requirements from RFP PDF documents,
query MongoDB for the winning contractor profile (e.g. Guidehouse LLP),
load our company data from the 'orbit-avanya' collection,
and compile a structured subcontracting/teaming pitch JSON.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Reconfigure stdout/stderr to use UTF-8 to avoid encoding errors on Windows console
if hasattr(sys.stdout, 'reconfigure'):
    getattr(sys.stdout, 'reconfigure')(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    getattr(sys.stderr, 'reconfigure')(encoding='utf-8')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.rfp_parser import RFPParser
from utils.pitch_compiler import PitchCompiler
from utils.pdf_generator import PDFGenerator
from utils.helpers import setup_logger
from utils.db_client import get_collection, close_connection

logger = setup_logger("generate_pitch")

def find_solicitation_winner(solicitation_number: str) -> str:
    """Queries MongoDB 'rfps' collection to find the winner of the solicitation."""
    try:
        col = get_collection("rfps")
        rfp = col.find_one({"solicitation_number": solicitation_number})
        if rfp:
            awardee = rfp.get("award", {}).get("awardee_name")
            if awardee and awardee.lower() != "unknown" and awardee.strip():
                return awardee
    except Exception as e:
        logger.warning(f"Failed to query solicitation winner from DB: {e}")
    return "Unknown"

def main():
    parser = argparse.ArgumentParser(
        prog="generate_pitch",
        description="Orbit Avanya Subcontracting Teaming Pitch Synthesizer"
    )
    parser.add_argument(
        "--solicitation",
        type=str,
        default="DHS-2026-RFP-0043",
        help="Solicitation number to target (default: DHS-2026-RFP-0043)"
    )
    parser.add_argument(
        "--winner",
        type=str,
        default=None,
        help="Explicitly specify the winning contractor/prime name (e.g. 'Guidehouse LLP')"
    )
    parser.add_argument(
        "--workshare",
        type=float,
        default=15.0,
        help="Proposed work share percentage, e.g. 10.0 to 20.0 (default: 15.0)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Custom output file path for JSON"
    )

    args = parser.parse_args()

    # Input validation
    if not (10.0 <= args.workshare <= 20.0):
        print("❌ Error: Proposed workshare percentage must be between 10.0% and 20.0% as per specifications.")
        sys.exit(1)

    print("\n" + "=" * 80)
    print(f"  Orbit Avanya Teaming Pitch Synthesizer  ")
    print(f"  Target RFP: {args.solicitation} | Work Share: {args.workshare}%")
    print("=" * 80 + "\n")

    # 1. Resolve Winner/Prime name
    winner_name = args.winner
    if not winner_name:
        winner_name = find_solicitation_winner(args.solicitation)
        
    if not winner_name or winner_name.lower() == "unknown":
        if args.solicitation == "DHS-2026-RFP-0043":
            winner_name = "Guidehouse LLP"
        elif args.solicitation == "36C24626Q0420":
            # Bid is open, default to a prime partner for testing
            winner_name = "Guidehouse LLP"
        else:
            winner_name = "Guidehouse LLP"
            
    print(f"✓ Prime Contractor (Winner) selected: '{winner_name}'")

    # 2. Check if RFP documents directory exists
    rfp_dir = PROJECT_ROOT / "downloads" / "opportunities" / args.solicitation / "rfp_docs"
    if not rfp_dir.exists():
        print(f"❌ Error: Solicitation documents directory not found: {rfp_dir}")
        print("Please check that the solicitation files are downloaded.")
        sys.exit(1)

    # 3. Extract and Parse RFP PDF files
    print("\nStep 1: Extracting text and parsing RFP PDF documents...")
    try:
        rfp_parser = RFPParser(args.solicitation, project_root=str(PROJECT_ROOT))
        pdf_texts = rfp_parser.extract_text_from_pdfs()
        
        if not pdf_texts:
            print("❌ Error: No text could be extracted from the RFP PDFs.")
            sys.exit(1)
            
        rfp_data = rfp_parser.parse_requirements(pdf_texts)
        print("✓ Extraction and requirement parsing complete.")
        print(f"  - Files parsed: {list(pdf_texts.keys())}")
        print(f"  - Technical Requirements matched: {rfp_data['identified_components']['technical']}")
        print(f"  - Security requirements matched: {rfp_data['identified_components']['security']}")
    except Exception as e:
        logger.error(f"Failed to parse RFP: {e}", exc_info=True)
        print(f"❌ Failed to parse RFP PDF files: {e}")
        sys.exit(1)

    # 4. Compile teaming proposal
    print("\nStep 2: Combining profiles and synthesizing teaming pitch...")
    try:
        compiler = PitchCompiler(project_root=str(PROJECT_ROOT))
        proposal = compiler.compile_teaming_proposal(
            rfp_data=rfp_data,
            winner_name=winner_name,
            workshare_pct=args.workshare
        )
        
        # Override output destination if custom path is passed
        if args.output:
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(proposal, f, indent=2, ensure_ascii=False)
            print(f"✓ Saved custom output to: {out_path}")
            
        print("✓ Teaming pitch data synthesized successfully.")
        
        # Generate PDF proposal & Product Match Report
        print("\nStep 3: Compiling proposal & product match report PDF documents...")
        pdf_gen = PDFGenerator(project_root=str(PROJECT_ROOT))
        pdf_gen.generate_pdf(args.solicitation)
        pdf_gen.generate_product_match_report(args.solicitation)
    except Exception as e:
        logger.error(f"Failed to compile PDF reports: {e}", exc_info=True)
        print(f"❌ PDF compilation failed: {e}")
        sys.exit(1)
    finally:
        # Close MongoDB connection
        try:
            close_connection()
        except Exception:
            pass

    # 5. Display Synthesis Summary
    print("\n" + "=" * 80)
    print("  TEAMING PROPOSAL COMPILATION SUMMARY")
    print("=" * 80)
    print(f"  Solicitation #    : {proposal['metadata']['solicitation_number']}")
    print(f"  Project Title     : {proposal['metadata']['project_title']}")
    print(f"  Issuing Agency    : {proposal['metadata']['issuing_agency']}")
    print(f"  Prime Contractor  : {proposal['prime_contractor']['company_name']}")
    print(f"  Prime Headquarters: {proposal['prime_contractor']['headquarters']}")
    print(f"  Subcontractor     : {proposal['subcontractor']['company_name']}")
    print(f"  Our Proposed Stack: {proposal['subcontractor']['product_name']} ({proposal['subcontractor']['industry_domain']})")
    print(f"  Work Share        : {proposal['proposal_settings']['proposed_workshare_pct']}%")
    print("-" * 80)
    
    print("\n🔒 Technical Capability Alignment:")
    for align in proposal["alignment_matrices"]["technical_capabilities"]:
        print(f"  • {align['rfp_required_capability']} ➔ {align['our_matched_capability']}")
        print(f"    Details: {align['how_it_aligns']}")
        
    print("\n🔑 Security & Compliance Alignment:")
    for align in proposal["alignment_matrices"]["security_compliance"]:
        print(f"  • {align['rfp_security_requirement']} ➔ {align['our_matched_standard']}")
        print(f"    Details: {align['how_it_aligns']}")

    print("\n📋 Subcontractor Work Share Breakdown:")
    for task in proposal["alignment_matrices"]["subcontractor_work_share_breakdown"]:
        print(f"  • {task['task']}: {task['proposed_share']}% share")
        
    print("\n✉️ Pitch Email Outreach Snippet:")
    print(f"  Subject: {proposal['pitch_outreach']['subject']}")
    print(f"  {proposal['pitch_outreach']['narrative'][:300]}...")
    print("=" * 80 + "\n")
    
    output_path = PROJECT_ROOT / "output" / "proposals" / f"{args.solicitation}_pitch_data.json"
    pdf_output_path = PROJECT_ROOT / "output" / "pdf" / f"{args.solicitation}_pitch_proposal.pdf"
    match_pdf_output_path = PROJECT_ROOT / "output" / "pdf" / f"{args.solicitation}_product_match_report.pdf"
    print(f"✓ Teaming pitch proposal JSON saved to: {output_path}")
    print(f"✓ Teaming pitch proposal PDF saved to: {pdf_output_path}")
    print(f"✓ Product match report PDF saved to: {match_pdf_output_path}")
    print("✓ Run completed successfully.")

if __name__ == "__main__":
    main()
