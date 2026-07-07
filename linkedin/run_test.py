"""
linkedin/run_test.py
--------------------
Interactive test runner for the LinkedIn module.

Supports two modes:
  1. Real Scrape: Runs the active 3-layer scraper, cleans, extracts BI,
     and saves to local MongoDB. Requires .env configuration.
  2. Offline Simulation: Simulates the pipeline using realistic raw data,
     allowing you to test structuring, cleaning, BI profiling, and MongoDB
     storage end-to-end without needing any API keys.

Usage:
    # Activate virtual environment first:
    # .venv\\Scripts\\activate

    # Run in simulation mode (No keys required):
    python linkedin/run_test.py --simulated

    # Run in live mode (Requires .env filled with keys):
    python linkedin/run_test.py --live "Infosys"
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

# Add the project root to sys.path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# Load environment variables before importing settings
load_dotenv()

from config.settings import settings
from linkedin import scrape_company, LinkedInStorage, LinkedInCompanyData
from linkedin.data_cleaner import DataCleaner
from linkedin.bi_extractor import BIExtractor
from utils.db_client import get_database, ensure_indexes, close_connection
from utils.helpers import safe_json_dumps, setup_logger

logger = setup_logger(__name__)


def verify_mongodb_connection() -> bool:
    """Verifies that the local MongoDB instance is running and reachable."""
    try:
        db = get_database()
        db.command("ping")
        return True
    except Exception as e:
        logger.error(
            f"Could not connect to MongoDB. Make sure MongoDB is running locally on port 27017.\n"
            f"Error details: {e}"
        )
        return False


async def run_simulation():
    """Runs a simulated end-to-end pipeline run to test storage, cleaning, and BI parsing."""
    logger.info("=== Running Offline Pipeline Simulation ===")

    if not verify_mongodb_connection():
        return

    # Ensure index configurations exist
    ensure_indexes()

    company_slug = "acme-corp"
    logger.info(f"Simulating pipeline for: '{company_slug}'")

    # Create dummy data matching unstructured output from crawlers
    simulated_raw_identity = {
        "company_name": "Acme Corp 🔥",
        "linkedin_url": "https://www.linkedin.com/company/acme-corp",
        "company_slug": "acme-corp",
        "website_url": "acme.com",
        "tagline": "Building the future of rocket-powered roller skates! 🚀",
        "industry": "Aerospace & Defense",
        "company_size_range": "201-500 employees",
        "followers_count": 12500,
    }

    simulated_raw_about = (
        "Join to view full profile. Already on LinkedIn? Sign in.\n"
        "Acme Corp is a globally recognized manufacturing conglomerate founded in 1949.\n"
        "We design and build customized rocket launchers, anvil delivery systems, and magnetic bird seed.\n"
        "Our mission is to help desert predators capture elusive road runners through advanced technology.\n"
        "Key Office Locations:\n"
        "HQ: 123 Desert Road, Mojave, USA\n"
        "Regional: 456 Canyon Way, Phoenix, USA"
    )

    # Let's write the simulated raw data to MongoDB first
    storage = LinkedInStorage()

    # Build Pydantic model manually from simulated parts
    from linkedin.models import CompanyIdentity, CompanyDescription, EmployeeInsights, LeadershipMember, CompanyPost, JobPosting, CompanyLocation

    identity = CompanyIdentity(**simulated_raw_identity)
    description = CompanyDescription(
        about_text=simulated_raw_about,
        mission_statement="Help desert predators capture road runners.",
        value_proposition="Customized machinery for coyote-roadrunner interactions.",
        target_customer_segments=["Predators", "Hunters", "Coyotes"],
        geographies_served=["USA", "North America"]
    )

    insights = EmployeeInsights(
        total_employee_count=350,
        employees_on_linkedin_count=320,
        employee_growth_percentage_1_year=12.5,
        top_skills_listed=["Rocketry", "Explosives", "Anvil Dropping", "Product Design"],
        top_universities_attended=["Desert State University", "Coyote Academy"]
    )

    leaders = [
        LeadershipMember(
            full_name="Wile E. Coyote",
            job_title="Chief Technology Officer & Field Tester",
            linkedin_profile_url="https://www.linkedin.com/in/wile-e-coyote"
        )
    ]

    posts = [
        CompanyPost(
            post_text="Excited to announce our new Jet-Powered Pogo Stick! 💥 Check it out at acme.com/pogo. Join to view full profile.",
            reactions_count=450,
            comments_count=82,
            reshares_count=12
        )
    ]

    jobs = [
        JobPosting(
            job_title="Lead Rocket Propulsion Engineer",
            job_location="Mojave, CA",
            employment_type="Full-time",
            experience_level="Mid-Senior level",
            key_skills_required=["Propulsion", "Explosives", "Safety Avoidance"]
        )
    ]

    locations = [
        CompanyLocation(
            full_address="123 Desert Road, Mojave, USA",
            city="Mojave",
            country="USA",
            is_headquarters=True
        )
    ]

    raw_company_data = LinkedInCompanyData(
        company_slug=company_slug,
        identity=identity,
        description=description,
        leadership_team=leaders,
        employee_insights=insights,
        recent_posts=posts,
        job_postings=jobs,
        office_locations=locations,
        scraped_at=datetime.now(timezone.utc),
        scrape_layers_used=["simulation"],
        source_urls_scraped=["https://www.linkedin.com/company/acme-corp"]
    )

    logger.info("Step 1: Raw structured data built. Running DataCleaner...")
    cleaner = DataCleaner()
    cleaned_company_data, quality_score = cleaner.clean(raw_company_data)

    # Let's inspect the cleaning result
    identity = cleaned_company_data.identity
    if identity is not None:
        logger.info(f"Cleaned Company Name: '{identity.company_name}' (No emoji!)")
        logger.info(f"Cleaned Tagline: '{identity.tagline}' (No emoji!)")
    posts = cleaned_company_data.recent_posts
    if posts:
        logger.info(f"Cleaned Post: '{posts[0].post_text}' (No boilerplate!)")
    logger.info(f"Data Quality Score: {quality_score:.2f}")

    # Check if OpenRouter key is set. If so, generate the BI Profile. If not, generate a mock one.
    bi_profile = None
    if settings.OPENROUTER_API_KEY and settings.OPENROUTER_API_KEY != "your_openrouter_api_key_here":
        logger.info("Step 2: OpenRouter API key detected. Extracting BI Profile using LLM...")
        bi_extractor = BIExtractor()
        bi_profile = await bi_extractor.extract_bi_profile(cleaned_company_data)

    from linkedin.models import BIProfile, TechStackProfile, BusinessChallenge, CompetitorMention, StrategicInitiative, GrowthSignal
    mock_bi = BIProfile(
        key_differentiators=["Customized bespoke tactical products", "Niche user targeting (predators)"],
        competitive_advantages=["70+ years of product blueprint repository", "Unmatched field test iterations"],
        identified_competitors=[
            CompetitorMention(competitor_name="Roadrunner Systems Inc", relationship_type="Direct Competitor", source="inferred")
        ],
        strategic_initiatives=[
            StrategicInitiative(
                initiative_name="Propulsion Safety Upgrades",
                description="Redesigning rocketry fuses to prevent premature detonation on the coyote field tester.",
                evidence="scraped job listing looking for Lead Rocket Propulsion Engineer",
                priority_level="Critical"
            )
        ],
        growth_signals=[
            GrowthSignal(
                signal_type="Product Launch",
                description="Jet-Powered Pogo Stick launch announcement",
                source="posts",
                significance="High"
            )
        ],
        business_challenges=[
            BusinessChallenge(
                challenge_area="Talent Acquisition",
                description="Need specialized rocketry engineers in remote desert locations.",
                evidence="Active hiring for rocketry in Mojave",
                opportunity_for_us="Provide remote engineering recruiting services."
            )
        ],
        digital_transformation_status="In Progress",
        ai_adoption_level="Exploring",
        company_maturity_stage="Mature Enterprise",
        executive_summary="Acme Corp is a legacy desert equipment manufacturer pivoting towards modern safety standards.",
        sales_talking_points=[
            "Mention recent Jet-Powered Pogo Stick launch success.",
            "Reference the critical need for safer rocketry engineering fuses."
        ],
        recommended_approach="Focus outreach on Wile E. Coyote around rocket safety engineering support."
    )

    if bi_profile and bi_profile.executive_summary:
        cleaned_company_data.bi_profile = bi_profile
        logger.info("BI Profile successfully generated using OpenRouter!")
    else:
        if settings.OPENROUTER_API_KEY and settings.OPENROUTER_API_KEY != "your_openrouter_api_key_here":
            logger.warning("OpenRouter extraction failed or rate-limited. Falling back to simulated offline BI Profile...")
        else:
            logger.info("Step 2: OPENROUTER_API_KEY is not set. Generating mock BI Profile offline...")
        cleaned_company_data.bi_profile = mock_bi
        logger.info("Mock BI Profile attached!")

    logger.info("Step 3: Storing final profile in MongoDB...")
    doc_id = storage.save_structured_company_data(cleaned_company_data)
    logger.info(f"Saved to MongoDB structured_linkedin collection under document ID: {doc_id}")

    # Read back to verify
    retrieved = storage.get_structured_company_data(company_slug)
    if retrieved is not None:
        identity_ret = retrieved.identity
        if identity_ret is not None:
            logger.info(f"Successfully retrieved '{identity_ret.company_name}' from database.")
        bi_ret = retrieved.bi_profile
        if bi_ret is not None:
            logger.info(f"Executive Summary: {bi_ret.executive_summary}")
            logger.info(f"Key Differentiators: {bi_ret.key_differentiators}")

    close_connection()
    logger.info("=== Simulation Complete ===")


async def run_live(company_input: str):
    """Runs a real live scrape, clean, BI extraction, and save process."""
    logger.info("=== Running Live Pipeline ===")

    if not verify_mongodb_connection():
        return

    # Check that keys are configured
    if not settings.OPENROUTER_API_KEY or settings.OPENROUTER_API_KEY == "your_openrouter_api_key_here":
        logger.error("OPENROUTER_API_KEY is not set. Please add it to your .env file to run a live scrape.")
        return

    if not settings.TAVILY_API_KEY or settings.TAVILY_API_KEY == "your_tavily_api_key_here":
        logger.warning(
            "TAVILY_API_KEY is not set. Real-time name resolution is disabled. "
            "Please pass a direct LinkedIn URL or slug."
        )

    # Initialize DB indexes
    ensure_indexes()

    try:
        company_data = await scrape_company(company_input, force_rescrape=True)

        logger.info("\n--- Live Data Scraped and Enriched ---")

        # Safely access identity fields — LLM may have failed if rate-limited
        if company_data.identity:
            logger.info(f"Company Name : {company_data.identity.company_name}")
            logger.info(f"Industry     : {company_data.identity.industry}")
            logger.info(f"Size         : {company_data.identity.company_size_range}")
            logger.info(f"HQ           : {company_data.identity.headquarters_location}")
        else:
            logger.warning(
                "Identity data is empty — LLM structuring was likely rate-limited. "
                "Raw data has been saved to MongoDB. Re-run when rate limits clear."
            )

        logger.info(f"Quality Score: {company_data.data_quality_score}")
        logger.info(f"Posts scraped: {len(company_data.recent_posts)}")
        logger.info(f"Jobs scraped : {len(company_data.job_postings)}")
        logger.info(f"Leaders found: {len(company_data.leadership_team)}")
        logger.info(f"Layers used  : {company_data.scrape_layers_used}")

        if company_data.bi_profile and company_data.bi_profile.executive_summary:
            logger.info("\n--- BI Profile ---")
            logger.info(f"Executive Summary  : {company_data.bi_profile.executive_summary}")
            logger.info(f"Maturity Stage     : {company_data.bi_profile.company_maturity_stage}")
            logger.info(f"AI Adoption        : {company_data.bi_profile.ai_adoption_level}")
            logger.info(f"Key Differentiators: {company_data.bi_profile.key_differentiators}")
            logger.info(f"Initiatives        : {[i.initiative_name for i in company_data.bi_profile.strategic_initiatives]}")
            logger.info(f"Challenges         : {[c.challenge_area for c in company_data.bi_profile.business_challenges]}")
            logger.info(f"Sales Talking Points: {company_data.bi_profile.sales_talking_points}")
        else:
            logger.warning(
                "BI Profile is empty — LLM was rate-limited. "
                "Raw data is in MongoDB. Re-run later to trigger BI extraction."
            )

    except Exception as e:
        logger.error(f"Live scrape failed: {e}", exc_info=True)
    finally:
        close_connection()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PPT-Agent LinkedIn Module Test Runner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--simulated", action="store_true", help="Run offline pipeline simulation (no keys required)"
    )
    group.add_argument(
        "--live", type=str, help="Run live scrape (requires API keys in .env, specify company name/URL/slug)"
    )

    args = parser.parse_args()

    if args.simulated:
        asyncio.run(run_simulation())
    elif args.live:
        asyncio.run(run_live(args.live))
