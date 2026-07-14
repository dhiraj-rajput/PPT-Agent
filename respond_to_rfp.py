"""
respond_to_rfp.py
------------------
CLI entry point for generating a full RFP response document.

Two modes:
  --mode prime       → Orbit Avanya responds directly to the government agency
                       Uses Ollama LLM (gemma4:31b-cloud) for section generation
  --mode subcontract → Orbit Avanya sends a teaming proposal to the prime winner
                       Rule-based, uses pitch_data JSON + winner company profile

Usage:
    # Respond as prime contractor
    python respond_to_rfp.py --solicitation N00178-26-R-3001 --mode prime

    # Send teaming proposal to winner
    python respond_to_rfp.py --solicitation N00178-26-R-3001 --mode subcontract --winner "Guidehouse LLP"

    # Full pipeline — also run company scraping first
    python respond_to_rfp.py --solicitation N00178-26-R-3001 --mode prime --scrape

Output:
    output/pdf/{solicitation}_{mode}_response.pdf
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

# Reconfigure stdout/stderr to use UTF-8 to avoid encoding errors on Windows console
if hasattr(sys.stdout, "reconfigure"):
    getattr(sys.stdout, "reconfigure")(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    getattr(sys.stderr, "reconfigure")(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.rfp_parser import RFPParser
from utils.pitch_compiler import PitchCompiler
from utils.rfp_response_generator import RFPResponseGenerator
from utils.rfp_response_pdf import generate_rfp_response_pdf
from utils.helpers import setup_logger
from utils.db_client import get_collection, close_connection

logger = setup_logger("respond_to_rfp")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_solicitation_winner(solicitation_number: str) -> str:
    """Query MongoDB 'rfps' collection for the award winner."""
    try:
        col = get_collection("rfps")
        rfp = col.find_one({"solicitation_number": solicitation_number})
        if rfp:
            awardee = rfp.get("award", {}).get("awardee_name")
            if awardee and awardee.lower() not in ("unknown", "") and awardee.strip():
                return awardee
    except Exception as e:
        logger.warning(f"Could not query winner from DB: {e}")
    return "Unknown"


def _load_winner_profile(winner_name: str) -> dict:
    """Load the compacted winner profile from MongoDB or output/json/."""
    try:
        col = get_collection("company_profiles")
        profile = col.find_one({"company_name": {"$regex": winner_name, "$options": "i"}})
        if profile:
            profile.pop("_id", None)
            logger.info(f"Loaded winner profile from MongoDB: {winner_name}")
            return profile
    except Exception as e:
        logger.warning(f"Could not load winner profile from DB: {e}")

    # Try disk
    json_dir = PROJECT_ROOT / "output" / "json"
    slug = winner_name.lower().replace(" ", "_").replace(",", "").replace(".", "")[:30]
    for path in json_dir.glob(f"*{slug[:10]}*_profile.json"):
        try:
            with open(path, encoding="utf-8") as f:
                logger.info(f"Loaded winner profile from disk: {path}")
                return json.load(f)
        except Exception:
            pass

    logger.warning(f"No profile found for winner: {winner_name}. Using empty profile.")
    return {"company_name": winner_name}


def _load_pitch_data(solicitation_number: str) -> dict:
    """Load existing pitch_data JSON from output/proposals/."""
    proposals_dir = PROJECT_ROOT / "output" / "proposals"
    path = proposals_dir / f"{solicitation_number}_pitch_data.json"
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                logger.info(f"Loaded pitch data from: {path}")
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load pitch data: {e}")
    return {}


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_prime_mode(args: argparse.Namespace) -> str:
    """
    Mode A — Orbit Avanya as prime contractor.
    Generates an LLM-powered full RFP response document.
    """
    sol_num = args.solicitation

    print(f"\n{'=' * 70}")
    print(f"  PRIME CONTRACTOR RFP RESPONSE")
    print(f"  Solicitation: {sol_num}")
    print(f"{'=' * 70}\n")

    # 1. Parse RFP documents
    print("Step 1: Parsing RFP documents...")
    rfp_dir = PROJECT_ROOT / "downloads" / "opportunities" / sol_num / "rfp_docs"
    if not rfp_dir.exists():
        print(f"  ⚠  RFP directory not found: {rfp_dir}")
        print("     Proceeding with minimal RFP data...")
        rfp_data = {
            "metadata": {
                "solicitation_number": sol_num,
                "issuing_agency": args.agency or "Issuing Agency",
                "project_title":  args.title or "IT Services",
            },
            "identified_components": {"technical": [], "security": []},
        }
    else:
        rfp_parser = RFPParser(sol_num, project_root=str(PROJECT_ROOT))
        pdf_texts  = rfp_parser.extract_text_from_pdfs()
        rfp_data   = rfp_parser.parse_requirements(pdf_texts) if pdf_texts else {
            "metadata": {"solicitation_number": sol_num},
            "identified_components": {"technical": [], "security": []},
        }

    # Clean existing generated documents for this mode
    pdf_out_dir = PROJECT_ROOT / "output" / "pdf"
    if pdf_out_dir.exists():
        for old_file in pdf_out_dir.glob(f"{sol_num}_prime_proposal.*"):
            try:
                old_file.unlink()
                print(f"  Cleared old generated file: {old_file.name}")
            except Exception:
                pass

    # Extract agency / title from RFP data
    meta        = rfp_data.get("metadata", {})
    agency_name = args.agency  or meta.get("issuing_agency", "Issuing Agency")
    proj_title  = args.title   or meta.get("project_title",  "Technical & Management Proposal")
    print(f"  ✓ Agency: {agency_name}")
    print(f"  ✓ Title:  {proj_title}")

    # 2. Load winner/competitor profile (optional — enriches the prime response)
    optimized_profile = None
    winner_name = args.winner or _find_solicitation_winner(sol_num)
    if winner_name and winner_name.lower() != "unknown":
        print(f"\nStep 2: Loading competitor profile for '{winner_name}'...")
        optimized_profile = _load_winner_profile(winner_name)
        print(f"  ✓ Profile loaded.")
    else:
        print("\nStep 2: No competitor profile found — skipping.")

    # 3. Generate sections via Ollama LLM
    print("\nStep 3: Generating RFP response sections via Ollama LLM...")
    print(f"  Model: gemma4:31b-cloud")
    gen = RFPResponseGenerator(project_root=str(PROJECT_ROOT))
    sections = gen.generate_prime_sections(
        rfp_data=rfp_data,
        optimized_profile=optimized_profile,
        solicitation_number=sol_num,
    )
    print(f"  ✓ Sections generated: {list(sections.keys())[:5]}...")

    # 4. Generate DOCX-styled PDF
    print("\nStep 4: Generating DOCX-styled PDF...")
    pdf_path = generate_rfp_response_pdf(
        solicitation_number=sol_num,
        mode="prime",
        sections=sections,
        agency_name=agency_name,
        proposal_title=proj_title,
        project_root=str(PROJECT_ROOT),
    )
    print(f"  ✓ PDF saved to: {pdf_path}")

    return pdf_path


def run_subcontract_mode(args: argparse.Namespace) -> str:
    """
    Mode B — Orbit Avanya as subcontractor.
    Rule-based generation from pitch_data JSON + winner profile.
    """
    sol_num = args.solicitation

    print(f"\n{'=' * 70}")
    print(f"  SUBCONTRACT TEAMING PROPOSAL")
    print(f"  Solicitation: {sol_num}")
    print(f"{'=' * 70}\n")

    # 1. Resolve winner name
    winner_name = args.winner or _find_solicitation_winner(sol_num)
    if not winner_name or winner_name.lower() == "unknown":
        winner_name = "Guidehouse LLP"
        print(f"  ⚠ Winner not specified — defaulting to '{winner_name}'")
    print(f"  Prime/Winner: {winner_name}")

    # 2. Parse RFP
    print("\nStep 1: Parsing RFP documents...")
    rfp_dir = PROJECT_ROOT / "downloads" / "opportunities" / sol_num / "rfp_docs"
    if rfp_dir.exists():
        rfp_parser = RFPParser(sol_num, project_root=str(PROJECT_ROOT))
        pdf_texts  = rfp_parser.extract_text_from_pdfs()
        rfp_data   = rfp_parser.parse_requirements(pdf_texts) if pdf_texts else {
            "metadata": {"solicitation_number": sol_num, "issuing_agency": args.agency or "Agency"},
            "identified_components": {"technical": [], "security": []},
        }
        print(f"  ✓ RFP parsed.")
    else:
        print(f"  ⚠ RFP documents directory not found. Using minimal data.")
        rfp_data = {
            "metadata": {
                "solicitation_number": sol_num,
                "issuing_agency": args.agency or "Issuing Agency",
                "project_title":  args.title or "IT Services",
            },
            "identified_components": {"technical": [], "security": []},
        }

    # Clean existing generated documents for this mode
    pdf_out_dir = PROJECT_ROOT / "output" / "pdf"
    if pdf_out_dir.exists():
        for old_file in pdf_out_dir.glob(f"{sol_num}_subcontract_proposal.*"):
            try:
                old_file.unlink()
                print(f"  Cleared old generated file: {old_file.name}")
            except Exception:
                pass

    # 3. Load or compile pitch data
    print("\nStep 2: Loading pitch data...")
    pitch_data = _load_pitch_data(sol_num)
    cached_winner = pitch_data.get("prime_contractor", {}).get("company_name", "") if pitch_data else ""
    if not pitch_data or (winner_name and cached_winner.lower() != winner_name.lower()):
        print(f"  No valid pitch data found for '{winner_name}' — compiling now...")
        compiler   = PitchCompiler(project_root=str(PROJECT_ROOT))
        pitch_data = compiler.compile_teaming_proposal(
            rfp_data=rfp_data,
            winner_name=winner_name,
            workshare_pct=args.workshare,
        )
        print("  ✓ Pitch data compiled.")
    else:
        print(f"  ✓ Loaded from disk (Prime: {cached_winner}).")

    # 4. Load winner profile
    print(f"\nStep 3: Loading winner company profile for '{winner_name}'...")
    winner_profile = _load_winner_profile(winner_name)
    print("  ✓ Profile ready.")

    # 5. Build sections (rule-based)
    print("\nStep 4: Building document sections (rule-based)...")
    gen = RFPResponseGenerator(project_root=str(PROJECT_ROOT))
    sections = gen.generate_subcontract_sections(
        rfp_data=rfp_data,
        pitch_data=pitch_data,
        winner_profile=winner_profile,
    )
    print(f"  ✓ Sections built: {list(sections.keys())[:5]}...")

    # 6. Generate PDF
    meta        = rfp_data.get("metadata", {})
    agency_name = args.agency or meta.get("issuing_agency", "Issuing Agency")
    proj_title  = args.title  or meta.get("project_title",  "Subcontractor Teaming Proposal")

    print("\nStep 5: Generating DOCX-styled PDF...")
    pdf_path = generate_rfp_response_pdf(
        solicitation_number=sol_num,
        mode="subcontract",
        sections=sections,
        agency_name=agency_name,
        proposal_title=proj_title,
        winner_name=winner_name,
        project_root=str(PROJECT_ROOT),
    )
    print(f"  ✓ PDF saved to: {pdf_path}")

    return pdf_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="respond_to_rfp",
        description="OrbitAvanya Tech — RFP Response Document Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python respond_to_rfp.py --solicitation N00178-26-R-3001 --mode prime
  python respond_to_rfp.py --solicitation 36C24626Q0420 --mode subcontract --winner "Guidehouse LLP"
  python respond_to_rfp.py --solicitation DHS-2026-RFP-0043 --mode prime --agency "DHS" --title "IT Modernization Proposal"
        """,
    )

    parser.add_argument(
        "--solicitation", "-s",
        type=str,
        required=True,
        help="Solicitation number (e.g. N00178-26-R-3001)",
    )
    parser.add_argument(
        "--mode", "-m",
        type=str,
        choices=["prime", "subcontract"],
        default="prime",
        help="Response mode: 'prime' (respond to agency) or 'subcontract' (teaming to winner)",
    )
    parser.add_argument(
        "--winner", "-w",
        type=str,
        default=None,
        help="Prime contractor name. Looked up from DB if not specified.",
    )
    parser.add_argument(
        "--workshare",
        type=float,
        default=15.0,
        help="Proposed work share percentage for subcontract mode (10.0–20.0, default: 15.0)",
    )
    parser.add_argument(
        "--agency",
        type=str,
        default=None,
        help="Override issuing agency name in the PDF",
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Override proposal title in the PDF",
    )

    args = parser.parse_args()

    # Validate workshare
    if not (10.0 <= args.workshare <= 20.0):
        print(f"❌ Error: --workshare must be between 10.0 and 20.0 (got {args.workshare})")
        sys.exit(1)

    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║      OrbitAvanya Tech LLP — RFP Response Generator                  ║
║      Mode: {args.mode.upper():<58s}║
║      Solicitation: {args.solicitation:<50s}║
╚══════════════════════════════════════════════════════════════════════╝""")

    try:
        if args.mode == "prime":
            pdf_path = run_prime_mode(args)
        else:
            pdf_path = run_subcontract_mode(args)

        print(f"\n{'=' * 70}")
        print(f"  ✅ SUCCESS")
        print(f"  PDF: {pdf_path}")
        print(f"  Mode: {args.mode.upper()}")
        print(f"  Solicitation: {args.solicitation}")
        print(f"  Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'=' * 70}\n")

    except KeyboardInterrupt:
        print("\n⚠ Interrupted.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    finally:
        try:
            close_connection()
        except Exception:
            pass


if __name__ == "__main__":
    main()
