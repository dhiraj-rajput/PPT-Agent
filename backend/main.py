"""
main.py
-------
CLI entry point for the PPT-Agent pipeline.

Runs the full LangGraph orchestration pipeline from any input format:
  - Company website URL  →  crawl site + scrape LinkedIn
  - Company name         →  discover URLs + crawl site + scrape LinkedIn
  - LinkedIn URL         →  scrape LinkedIn + (optionally) crawl website

MongoDB indexes are created on first run automatically.

Usage:
    python main.py "https://infosys.com"
    python main.py "Infosys Limited"
    python main.py "https://linkedin.com/company/infosys"
    python main.py "Infosys" --no-website        # skip website crawl
    python main.py "Infosys" --force             # force re-scrape even if cached
"""

import argparse
import json
import sys

# Reconfigure stdout/stderr to use UTF-8 to avoid encoding errors on Windows console
try:
    if hasattr(sys.stdout, 'reconfigure'):
        getattr(sys.stdout, 'reconfigure')(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        getattr(sys.stderr, 'reconfigure')(encoding='utf-8')
except Exception:
    pass

from utils.helpers import setup_logger
from utils.db_client import ensure_all_indexes, close_connection

logger = setup_logger("main")


def print_summary(result: dict) -> None:
    """Print a clean summary of the pipeline result."""
    # Prefer the rich optimized_profile; fall back to combined_profile if compactor failed
    optimized = result.get("optimized_profile") or {}
    profile = result.get("combined_profile") or {}
    errors = result.get("errors", [])

    # Use optimized fields where available, combined as fallback
    company_name = optimized.get("company_name") or profile.get("company_name", "N/A")
    website = optimized.get("website") or profile.get("website_url", "N/A")
    industry = optimized.get("industry") or profile.get("industry", "N/A")
    hq = optimized.get("headquarters") or profile.get("headquarters", "N/A")
    employee_count = optimized.get("employee_count") or profile.get("company_size", "N/A")
    founded = optimized.get("founded_year") or profile.get("founded_year", "N/A")
    sources = optimized.get("sources_used") or profile.get("data_sources", [])

    print("\n" + "=" * 70)
    print("  PPT-Agent — Competitor Intelligence Profile")
    print("=" * 70)
    print(f"  Company       : {company_name}")
    print(f"  Website       : {website}")
    print(f"  Industry      : {industry}")
    print(f"  HQ            : {hq}")
    print(f"  Employees     : {employee_count}")
    print(f"  Founded       : {founded}")
    print(f"  Data sources  : {', '.join(sources) if sources else 'N/A'}")
    print(f"  Errors        : {len(errors)}")
    print("=" * 70)

    # Business description
    description = optimized.get("description") or profile.get("about_text") or ""
    if description:
        truncated = description[:250] + "..." if len(description) > 250 else description
        print(f"\n📋 About:\n   {truncated}\n")

    # Business model
    business_model = optimized.get("business_model") or ""
    if business_model:
        print(f"💼 Business Model:\n   {business_model}\n")

    # Products & Services
    products = optimized.get("products") or profile.get("products", [])
    services = optimized.get("services") or profile.get("services", [])
    if products:
        print("🛍️  Products:")
        for p in products[:6]:
            print(f"   • {p}")
    if services:
        print("⚙️  Services:")
        for s in services[:6]:
            print(f"   • {s}")

    # Competitors — the key competitive intelligence
    competitors = optimized.get("competitors") or profile.get("competitors", [])
    if competitors:
        print("\n⚔️  Competitors:")
        for c in competitors[:6]:
            print(f"   • {c}")

    # RFP Strengths
    rfp_strengths = optimized.get("rfp_strengths") or profile.get("key_differentiators", [])
    if rfp_strengths:
        print("\n🎯 RFP Strengths:")
        for s in rfp_strengths[:5]:
            print(f"   • {s}")

    # Financial Highlights
    financial = optimized.get("financial_highlights") or []
    if financial:
        print("\n💰 Financial Highlights:")
        for f in financial[:4]:
            print(f"   • {f}")

    # Recent News
    recent_news = optimized.get("recent_news") or []
    external_news = profile.get("external_news") or result.get("external_news") or []
    if recent_news:
        print("\n📰 Recent News:")
        for n in recent_news[:4]:
            print(f"   • {n}")
    elif external_news:
        print("\n📰 External News & RFP Insights:")
        for n in external_news[:4]:
            print(f"   • {n.get('title')} ({n.get('url', '')})")
            snippet = n.get("snippet", "")
            if snippet:
                truncated = snippet[:100] + "..." if len(snippet) > 100 else snippet
                print(f"     \"{truncated}\"")

    # Value proposition
    vp = optimized.get("value_proposition") or profile.get("executive_summary") or ""
    if vp:
        truncated = vp[:200] + "..." if len(vp) > 200 else vp
        print(f"\n✨ Value Proposition:\n   {truncated}")

    if errors:
        print(f"\n⚠️  Non-fatal errors ({len(errors)}):")
        for e in errors:
            print(f"   • {e}")

    print()


def main():
    parser = argparse.ArgumentParser(
        prog="ppt-agent",
        description="PPT-Agent: AI-powered company intelligence pipeline",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "input",
        type=str,
        help=(
            "Company website URL, LinkedIn URL, or company name.\n"
            "Examples:\n"
            "  https://infosys.com\n"
            "  https://linkedin.com/company/infosys\n"
            "  \"Infosys Limited\""
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force re-scrape even if data exists in MongoDB cache.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        dest="output_json",
        help="Print the full result as JSON instead of a summary.",
    )
    parser.add_argument(
        "--no-indexes",
        action="store_true",
        default=False,
        help="Skip MongoDB index creation on startup.",
    )

    args = parser.parse_args()

    # --- Setup ---
    if not args.no_indexes:
        try:
            ensure_all_indexes()
        except Exception as e:
            logger.warning(f"Could not create MongoDB indexes (is MongoDB running?): {e}")

    # --- Run pipeline ---
    try:
        from pipeline.orchestrator import run_pipeline
        logger.info(f"Running pipeline for input: '{args.input}' (force={args.force})")
        result = run_pipeline(args.input, force=args.force)
    except Exception as e:
        logger.error(f"Pipeline failed with critical error: {e}", exc_info=True)
        print(f"\n❌ Pipeline failed: {e}")
        sys.exit(1)
    finally:
        close_connection()

    # --- Output ---
    if args.output_json:
        # Prefer the rich optimized_profile; fall back to combined_profile
        output_data = result.get("optimized_profile") or result.get("combined_profile") or {}
        print(json.dumps(output_data, indent=2, default=str))
    else:
        print_summary(result)

    # Exit with code 1 if there were any errors
    if result.get("errors"):
        sys.exit(0)  # Still 0 — errors are non-fatal warnings


if __name__ == "__main__":
    main()
