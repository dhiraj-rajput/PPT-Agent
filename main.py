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
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from utils.helpers import setup_logger
from utils.db_client import ensure_all_indexes, close_connection

logger = setup_logger("main")


def print_summary(result: dict) -> None:
    """Print a clean summary of the pipeline result."""
    profile = result.get("combined_profile") or {}
    errors = result.get("errors", [])

    print("\n" + "=" * 60)
    print("  PPT-Agent — Company Intelligence Profile")
    print("=" * 60)
    print(f"  Company     : {profile.get('company_name', 'N/A')}")
    print(f"  Slug        : {profile.get('company_slug', 'N/A')}")
    print(f"  Website     : {profile.get('website_url', 'N/A')}")
    print(f"  LinkedIn    : {profile.get('linkedin_url', 'N/A')}")
    print(f"  Industry    : {profile.get('industry', 'N/A')}")
    print(f"  HQ          : {profile.get('headquarters', 'N/A')}")
    print(f"  Data sources: {', '.join(profile.get('data_sources', []))}")
    print(f"  Errors      : {len(errors)}")
    print("=" * 60)

    if profile.get("executive_summary"):
        print(f"\n📋 Executive Summary:\n{profile['executive_summary']}\n")

    if profile.get("key_differentiators"):
        print("🎯 Key Differentiators:")
        for d in profile["key_differentiators"][:3]:
            print(f"   • {d}")

    if profile.get("external_news"):
        print("\n📰 External News & RFP Insights:")
        for n in profile["external_news"][:4]:
            print(f"   • {n.get('title')} ({n.get('url')})")
            snippet = n.get('snippet', '')
            if snippet:
                truncated = snippet[:110] + "..." if len(snippet) > 110 else snippet
                print(f"     \"{truncated}\"")

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
        from orchestrator import run_pipeline
        logger.info(f"Running pipeline for input: '{args.input}'")
        result = run_pipeline(args.input)
    except Exception as e:
        logger.error(f"Pipeline failed with critical error: {e}", exc_info=True)
        print(f"\n❌ Pipeline failed: {e}")
        sys.exit(1)
    finally:
        close_connection()

    # --- Output ---
    if args.output_json:
        print(json.dumps(result.get("combined_profile", {}), indent=2, default=str))
    else:
        print_summary(result)

    # Exit with code 1 if there were any errors
    if result.get("errors"):
        sys.exit(0)  # Still 0 — errors are non-fatal warnings


if __name__ == "__main__":
    main()
