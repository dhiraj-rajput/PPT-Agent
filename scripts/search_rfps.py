"""
search_rfps.py
--------------
Command-line utility to search for RFPs (contract opportunities) on SAM.gov,
extract competitor and bid intelligence, and profile the competitors.

Usage:
    python search_rfps.py --query "analytics" --days 90
    python search_rfps.py --query "data warehousing" --limit-competitors 2 --use-mock
"""

import argparse
import json
import sys
from datetime import datetime, timezone

# Reconfigure stdout/stderr to use UTF-8 to avoid encoding errors on Windows console
if hasattr(sys.stdout, 'reconfigure'):
    getattr(sys.stdout, 'reconfigure')(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    getattr(sys.stderr, 'reconfigure')(encoding='utf-8')

from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.sam_gov.opportunities import SAMOpportunitiesClient
from app.sam_gov.sam_client import SAMEntityClient
from app.sam_gov.competitors import CompetitorExtractor
from app.sam_gov.competitor_profiler import CompetitorProfiler
from config.settings import settings
from utils.db_client import ensure_all_indexes, close_connection, get_collection
from utils.helpers import setup_logger

logger = setup_logger("search_rfps")


def print_rfp_report(rfp: dict) -> None:
    """Prints a clean summary of the structured RFP opportunity."""
    print("\n" + "=" * 80)
    print(f"  RFP Profile: {rfp['title']}")
    print("=" * 80)
    print(f"  Solicitation # : {rfp['solicitation_number']}")
    print(f"  Notice Type    : {rfp['type']}")
    print(f"  Agency (Issuer): {rfp['agency']} ({rfp['sub_agency']})")
    print(f"  Office         : {rfp['office']}")
    print(f"  Posted Date    : {rfp['posted_date']}")
    print(f"  Deadline Date  : {rfp['deadline']}")
    print(f"  NAICS Code     : {rfp['naics']}")
    print(f"  Set-Aside      : {rfp['set_aside']}")
    print(f"  Place of Perf. : {rfp['place_of_performance']}")
    
    if rfp.get("pocs"):
        print("  Contacts       :")
        for poc in rfp["pocs"]:
            print(f"    • {poc['name']} | {poc['email']} | {poc['phone']}")
            
    if rfp.get("award"):
        aw = rfp["award"]
        print("\n  🏆 WINNING CONTRACT & AWARD DETAILS  :")
        print(f"    • Awardee Name : {aw['awardee_name']}")
        print(f"    • Awardee UEI  : {aw['awardee_uei']}")
        print(f"    • Awardee CAGE : {aw['awardee_cage']}")
        print(f"    • Award Date   : {aw['date']}")
        print(f"    • Award Number : {aw['award_number']}")

    if rfp.get("rfp_documents"):
        print("\n  📂 RFP Documents (Downloaded Locally):")
        for doc in rfp["rfp_documents"]:
            print(f"    • {doc['filename']} ({doc['status']})")
            if doc.get("local_path"):
                print(f"      Path: {doc['local_path']}")

    if rfp.get("proposal_documents"):
        print("\n  📜 Winner Proposal / Submitted Documents (Downloaded Locally):")
        for doc in rfp["proposal_documents"]:
            print(f"    • {doc['filename']} ({doc['status']})")
            if doc.get("local_path"):
                print(f"      Path: {doc['local_path']}")

    print("-" * 80)
    desc = rfp.get("description", "")
    if desc:
        truncated = desc[:400] + "..." if len(desc) > 400 else desc
        # Remove HTML tags if present in description
        import re
        clean_desc = re.sub(r'<[^>]*>', '', truncated)
        print(f"📋 Description:\n  {clean_desc.strip()}")
    print("=" * 80 + "\n")


def print_competitors_report(competitors: list, rfp: dict) -> None:
    """Prints a report of discovered bidders, highlighting the winner and their proposal files."""
    print("=" * 80)
    print("  🏆 Winning Contractor & Bid Details")
    print("=" * 80)
    
    award = rfp.get("award")
    if award:
        print(f"  Winner Name    : {award['awardee_name']}")
        print(f"  Award Date     : {award['date']}")
        print(f"  Contract #     : {award['award_number']}")
        
        # Display proposal documents that were downloaded
        prop_docs = rfp.get("proposal_documents") or []
        if prop_docs:
            print("  Proposal Files downloaded locally:")
            for doc in prop_docs:
                print(f"    • {doc['filename']}")
                if doc.get("local_path"):
                    print(f"      Path: {doc['local_path']}")
        else:
            print("  Proposal Files : None found in award attachments.")
    else:
        print("  Winner Info    : No award details found (RFP may still be active/unawarded).")
        
    print("\n" + "=" * 80)
    print("  👥 Other Competing Bidders")
    print("=" * 80)
    
    winner_name = award["awardee_name"].lower() if award else ""
    other_bidders = []
    for c in competitors:
        c_name = c["company_name"].lower()
        if winner_name and (winner_name in c_name or c_name in winner_name):
            continue
        other_bidders.append(c)
        
    if not other_bidders:
        print("  No other competing bidders discovered in public logs.")
    else:
        for idx, comp in enumerate(other_bidders, 1):
            print(f"  {idx}. {comp['company_name']}")
            print(f"     • Tech Rating    : {comp['technical_rating']}")
            print(f"     • Protest Status : {comp['protest_status']}")
            print(f"     • Source URL     : {comp['source_url']}")
            sw = comp.get("strengths_weaknesses", "")
            if sw:
                print(f"     • Bid Details    : {sw}")
            print("-" * 40)
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        prog="search_rfps",
        description="Search SAM.gov RFPs and analyze competitor proposals",
    )
    parser.add_argument(
        "--query",
        type=str,
        required=True,
        help="Search term for SAM.gov opportunities (e.g. 'analytics').",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Number of lookback days to search (default: 90).",
    )
    parser.add_argument(
        "--limit-competitors",
        type=int,
        default=3,
        help="Maximum number of competitors to actively profile (default: 3).",
    )
    parser.add_argument(
        "--naics",
        type=str,
        default=None,
        help="Optional NAICS code filter.",
    )
    parser.add_argument(
        "--use-mock",
        action="store_true",
        help="Force mock mode without using live API keys.",
    )
    parser.add_argument(
        "--auto-select",
        action="store_true",
        default=True,
        help="Automatically select the first matching opportunity.",
    )
    parser.add_argument(
        "--select-idx",
        type=int,
        default=None,
        help="Index of the opportunity to select (1-based index).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Profile and scrape ALL matching opportunities instead of just one.",
    )

    args = parser.parse_args()

    # Ensure MongoDB indexes exist
    try:
        ensure_all_indexes()
    except Exception as e:
        logger.warning(f"Could not connect to MongoDB (is MongoDB running?): {e}")

    print("\n" + "*" * 80)
    print("  PPT-Agent — SAM.gov RFP & Competitor Intelligence Pipeline")
    print("*" * 80 + "\n")

    # 1. Search SAM.gov
    opp_client = SAMOpportunitiesClient()
    use_mock_flag = args.use_mock or settings.FORCE_MOCK_SAM_GOV or not opp_client.is_live()
    
    opportunities = opp_client.search_opportunities(
        query=args.query,
        posted_days=args.days,
        naics_code=args.naics,
        use_mock=use_mock_flag
    )

    if not opportunities:
        print(f"❌ No matching opportunities found on SAM.gov for query: '{args.query}'")
        sys.exit(0)

    print(f"✓ Found {len(opportunities)} matching opportunities on SAM.gov.\n")

    # Display list of matching opportunities
    for idx, opp in enumerate(opportunities, 1):
        sol_num = opp.get("solicitationNumber") or opp.get("solnum") or "N/A"
        title = opp.get("title") or "Unnamed"
        agency = opp.get("department") or opp.get("agencyName") or opp.get("fullParentPathName") or "N/A"
        if "." in agency:
            agency = agency.split(".")[0]
        opp_type = opp.get("type") or "Notice"
        
        # Display the winner directly in the list if available
        award = opp.get("award")
        winner_suffix = ""
        if award and isinstance(award, dict):
            awardee = award.get("awardee") or {}
            winner_name = awardee.get("legalBusinessName") or awardee.get("name") or "Unknown"
            winner_suffix = f" (Winner: {winner_name})"
            
        print(f"  [{idx}] {sol_num} — {title}{winner_suffix}")
        print(f"      Type: {opp_type} | Agency: {agency}")
        print("-" * 50)

    if args.all:
        print(f"\n→ Run Mode: --all. Profiling ALL {len(opportunities)} opportunities sequentially...\n")
        for idx, opp in enumerate(opportunities, 1):
            print(f"\n" + "=" * 80)
            print(f"  💼 OPPORTUNITY {idx} OF {len(opportunities)}")
            print("=" * 80)
            try:
                profile_single_opportunity(opp, opp_client, use_mock_flag, args.limit_competitors)
            except Exception as e:
                logger.error(f"Failed processing opportunity {opp.get('solicitationNumber')}: {e}", exc_info=True)
    else:
        # 2. Select opportunity
        selected_idx = 0  # Default to first one
        if args.select_idx is not None:
            selected_idx = args.select_idx - 1
        elif not args.auto_select and sys.stdin.isatty():
            try:
                choice = input(f"\nSelect an opportunity to analyze (1-{len(opportunities)}) [default 1]: ").strip()
                if choice:
                    selected_idx = int(choice) - 1
            except Exception:
                pass

        if selected_idx < 0 or selected_idx >= len(opportunities):
            selected_idx = 0

        selected_opp = opportunities[selected_idx]
        profile_single_opportunity(selected_opp, opp_client, use_mock_flag, args.limit_competitors)

    print("✓ Analysis complete. All structured records are saved in MongoDB collections:")
    print("  - 'rfps': RFP solicitation metadata, competitor lists, and bid details.")
    print("  - 'company_profiles': Full business intelligence profiles of the bidders.")

    close_connection()


def profile_single_opportunity(selected_opp: dict, opp_client: SAMOpportunitiesClient, use_mock_flag: bool, limit_competitors: int) -> None:
    sol_num = selected_opp.get("solicitationNumber") or selected_opp.get("solnum") or "unknown"
    print(f"\n→ Selecting Opportunity: {sol_num} for detailed profiling...\n")

    # 3. Structure RFP profile
    rfp_profile = opp_client.structure_rfp_profile(selected_opp)
    
    # 4. Discover competitors & bid details (moved up to allow winner tracing)
    extractor = CompetitorExtractor()
    print("🔍 Discovering bidders and proposal details from public logs & search...")
    competitors = extractor.find_competitors_and_bids(
        solicitation_number=rfp_profile["solicitation_number"],
        use_mock=use_mock_flag
    )

    # Try to trace the winner from the competitors list if SAM.gov has it as Unknown
    award = rfp_profile.get("award")
    if not award or not award.get("awardee_name") or award.get("awardee_name") == "Unknown":
        winner_comp = None
        for comp in competitors:
            if comp.get("protest_status") == "Awardee":
                winner_comp = comp
                break
        
        # Fallback context match
        if not winner_comp:
            for comp in competitors:
                details = comp.get("strengths_weaknesses", "").lower()
                if "awarded" in details or "winner" in details or "won" in details:
                    winner_comp = comp
                    break
        
        if winner_comp:
            rfp_profile["award"] = {
                "awardee_name": winner_comp["company_name"],
                "awardee_uei": "",
                "awardee_cage": "",
                "amount": winner_comp["bid_amount"],
                "date": "N/A",
                "award_number": "N/A"
            }
            logger.info(f"Dynamically traced winning contractor: {winner_comp['company_name']}")

    # Save RFP profile to MongoDB 'rfps' collection
    try:
        rfp_col = get_collection("rfps")
        rfp_col.update_one(
            {"solicitation_number": rfp_profile["solicitation_number"]},
            {"$set": rfp_profile},
            upsert=True
        )
        logger.info(f"RFP details saved to MongoDB 'rfps' collection.")
    except Exception as e:
        logger.warning(f"Could not save RFP details to MongoDB: {e}")

    # Print structured RFP details
    print_rfp_report(rfp_profile)
    
    # Print competitors report
    print_competitors_report(competitors, rfp_profile)

    # 5. Call the other agents (Linkedin, Website, Google Search) to profile the winning company and competitors
    award = rfp_profile.get("award")
    if award and award.get("awardee_name") and award.get("awardee_name") != "Unknown":
        winner_name = award["awardee_name"]
        print("\n" + "=" * 80)
        print(f"  🏆 PROFILING WINNING CONTRACTOR: {winner_name}")
        print("=" * 80)
        
        if use_mock_flag:
            print("  [Mock Mode] Loading mock company profile for winner...")
            winner_profiler = CompetitorProfiler(limit=1)
            winner_profiles = winner_profiler.profile_competitors([{"company_name": winner_name}], use_mock=True)
            if winner_profiles:
                p = winner_profiles[0]
                print(f"  Company    : {p.get('company_name')}")
                print(f"  Website    : {p.get('website')}")
                print(f"  Industry   : {p.get('industry')}")
                print(f"  Products   : {', '.join(p.get('products', []))}")

            # Run proposal compiler & PDF generator fast-path for mock mode
            try:
                from pathlib import Path
                from documents.rfp_response.rfp_parser import RFPParser
                from documents.rfp_response.pitch_compiler import PitchCompiler
                from documents.rfp_response.pdf_generator import PDFGenerator

                proj_root = Path(__file__).resolve().parent.parent
                print("\n  [Mock Mode] Generating mock B2B proposal JSON & PDF...")
                rfp_parser = RFPParser(rfp_profile["solicitation_number"], project_root=str(proj_root))
                pdf_texts = rfp_parser.extract_text_from_pdfs()
                if pdf_texts:
                    rfp_data = rfp_parser.parse_requirements(pdf_texts)
                    compiler = PitchCompiler(project_root=str(proj_root))
                    proposal = compiler.compile_teaming_proposal(
                        rfp_data=rfp_data,
                        winner_name=winner_name,
                        workshare_pct=15.0
                    )
                    pdf_gen = PDFGenerator(project_root=str(proj_root))
                    pdf_path = pdf_gen.generate_pdf(rfp_profile["solicitation_number"])
                    match_pdf_path = pdf_gen.generate_product_match_report(rfp_profile["solicitation_number"])
                    print(f"✓ [Mock Mode] Teaming proposal PDF saved to: {pdf_path}")
                    print(f"✓ [Mock Mode] Product Match Report PDF saved to: {match_pdf_path}")
                else:
                    print("⚠️ [Mock Mode] No solicitation PDFs found to compile mock proposal.")
            except Exception as e:
                logger.warning(f"Failed to generate mock proposal PDF: {e}")
        else:
            print("⚡ Launching full scraping pipeline (LinkedIn, Website, Search agents) for the winner...")
            try:
                from pipeline.orchestrator import run_pipeline
                from main import print_summary
                
                # Execute the full LangGraph scraping/agent pipeline on the winning company
                winner_result = run_pipeline(winner_name, solicitation_number=rfp_profile["solicitation_number"])
                
                # Print the summarized results from the scrapers/agents
                print_summary(winner_result)
                
                # Also save the optimized profile to MongoDB cache under company_profiles
                optimized = winner_result.get("optimized_profile") or winner_result.get("combined_profile") or {}
                if optimized:
                    try:
                        col = get_collection("company_profiles")
                        slug = winner_result.get("company_slug") or optimized.get("company_slug")
                        if not slug and (optimized.get("website") or optimized.get("website_url")):
                            from pipeline.models.compactor import _domain_key
                            web_val = str(optimized.get("website") or optimized.get("website_url") or "")
                            slug = _domain_key(web_val)
                        
                        if slug:
                            col.update_one(
                                {"company_slug": slug},
                                {
                                    "$set": {
                                        "legal_name": winner_name
                                    },
                                    "$addToSet": {
                                        "aliases": winner_name
                                    }
                                }
                            )
                            logger.info(f"Successfully mapped GSA legal name '{winner_name}' as alias in winner profile.")
                        else:
                            # Fallback if no slug resolved
                            col.update_one(
                                {"company_name": winner_name},
                                {
                                    "$set": {
                                        "company_name": winner_name,
                                        "website": optimized.get("website") or optimized.get("website_url") or "N/A",
                                        "industry": optimized.get("industry") or "N/A",
                                        "hq_location": optimized.get("headquarters") or "N/A",
                                        "products": optimized.get("products") or [],
                                        "last_updated": datetime.now(tz=timezone.utc).isoformat()
                                    }
                                },
                                upsert=True
                            )
                            logger.info(f"Saved winner's company profile to MongoDB.")
                    except Exception as e:
                        logger.warning(f"Could not cache scraped winner profile: {e}")
            except Exception as e:
                logger.error(f"Failed to profile winning contractor '{winner_name}': {e}", exc_info=True)


if __name__ == "__main__":
    main()
