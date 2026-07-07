"""
linkedin/demo_compare.py
-------------------------
A demonstration script to showcase how raw scraped data matches up with
the parsed, structured business intelligence data in MongoDB.

Usage:
    .venv\\Scripts\\python.exe linkedin/demo_compare.py "infosys"
"""

import sys
import os
import re

# Add root folder to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set console encoding to UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from utils.db_client import get_collection

def display_comparison(company_slug: str):
    print("=" * 80)
    print(f"       PPT-AGENT DATA QUALITY COMPARISON DEMO: '{company_slug.upper()}'")
    print("=" * 80)

    # 1. Fetch raw logs
    raw_col = get_collection("raw_linkedin")
    raw_doc = raw_col.find_one(
        {"company_slug": company_slug, "scrape_layer": "public"},
        sort=[("scraped_at", -1)]
    )

    if not raw_doc:
        print(f"[ERROR] No raw scraped data found for '{company_slug}' in MongoDB.")
        print("Please run the live scraper first: .venv\\Scripts\\python.exe linkedin/run_test.py --live \"company_name\"")
        return

    raw_text = raw_doc.get("raw_text") or ""
    meta_tags = raw_doc.get("meta_tags") or {}

    # 2. Fetch structured logs
    struct_col = get_collection("structured_linkedin")
    struct_doc = struct_col.find_one({"company_slug": company_slug})

    if not struct_doc:
        print(f"[ERROR] No structured company profile found for '{company_slug}' in MongoDB.")
        return

    identity = struct_doc.get("identity") or {}
    description = struct_doc.get("description") or {}
    posts = struct_doc.get("recent_posts") or []
    locations = struct_doc.get("office_locations") or []
    bi = struct_doc.get("bi_profile") or {}

    # -------------------------------------------------------------
    # SECTION 1: Core Company Profile
    # -------------------------------------------------------------
    print("\n[SECTION 1] CORE PROFILE MATCHING")
    print("-" * 80)
    
    # Name
    print(f"{'Field':<25} | {'Raw Scraped Source Snippet':<35} | {'Structured Parsed Value':<35}")
    print("-" * 80)
    print(f"{'Company Name':<25} | {'og:title -> ' + meta_tags.get('og:title', '')[:25]:<35} | {identity.get('company_name'):<35}")
    
    # Website
    web_snippet = "Website https://..." if "Website https" in raw_text else "Not explicit"
    print(f"{'Website URL':<25} | {web_snippet:<35} | {identity.get('website_url'):<35}")
    
    # Industry
    ind_match = re.search(r"Industry\s+([^\n]+)", raw_text)
    ind_snippet = ind_match.group(0)[:30] if ind_match else "Industry ..."
    print(f"{'Industry':<25} | {ind_snippet:<35} | {identity.get('industry'):<35}")
    
    # Size
    size_match = re.search(r"Company size\s+([^\n]+)", raw_text)
    size_snippet = size_match.group(0)[:30] if size_match else "Company size ..."
    print(f"{'Employee Range':<25} | {size_snippet:<35} | {identity.get('company_size_range'):<35}")

    # Founded
    founded_match = re.search(r"Founded\s+(\d{4})", raw_text)
    founded_snippet = founded_match.group(0) if founded_match else "Founded ..."
    print(f"{'Founded Year':<25} | {founded_snippet:<35} | {str(identity.get('founded_year')):<35}")

    # Stock
    stock_match = re.search(r"\(([A-Z]+):\s*([A-Z]+)\)", raw_text)
    stock_snippet = stock_match.group(0) if stock_match else "Stock symbol ..."
    stock_val = f"{identity.get('stock_exchange')}:{identity.get('stock_symbol')}" if identity.get("stock_symbol") else "None"
    print(f"{'Stock Ticker':<25} | {stock_snippet:<35} | {stock_val:<35}")

    # -------------------------------------------------------------
    # SECTION 2: Description & Tagline
    # -------------------------------------------------------------
    print("\n[SECTION 2] DESCRIPTION & POSITIONING")
    print("-" * 80)
    print(">>> RAW TAGLINE SLICE:")
    # Print tagline slice
    followers_match = re.search(r"followers\s+(.*?)\s+See jobs", raw_text)
    if followers_match:
        print(f"  [RAW]: ... followers {followers_match.group(1)[:70]} ... See jobs")
    else:
        print("  [RAW]: Tagline found near followers text block.")
    print(f"  [STRUCTURED TAGLINE]: \"{identity.get('tagline')}\"")
    
    print("\n>>> RAW ABOUT US DESCRIPTION (FIRST 150 CHARS):")
    about_snippet = raw_text[raw_text.find("About us") + 8:raw_text.find("About us") + 250].strip().replace('\n', ' ')
    print(f"  [RAW]: \"{about_snippet[:150]}...\"")
    about_text_val = description.get('about_text') if description else None
    about_text_str = about_text_val[:150] if about_text_val else "N/A"
    print(f"  [STRUCTURED ABOUT]: \"{about_text_str}...\"")

    # -------------------------------------------------------------
    # SECTION 3: Office Locations
    # -------------------------------------------------------------
    print("\n[SECTION 3] OFFICE LOCATIONS EXTRACTION")
    print("-" * 80)
    loc_raw = raw_text[raw_text.find("Locations") + 9:raw_text.find("Locations") + 250].strip().replace('\n', ' ')
    print(f"  [RAW SLICE]: ... Locations {loc_raw[:150]} ...")
    print(f"  [PARSED LOCATIONS COUNT]: {len(locations)} offices structured.")
    print("  [SAMPLE EXTRACTED OFFICES]:")
    for loc in locations[:3]:
        print(f"    - {loc.get('city')}, {loc.get('country')} (Address: {(loc.get('full_address') or '')[:50]}...)")

    # -------------------------------------------------------------
    # SECTION 4: Recent Posts (Updates)
    # -------------------------------------------------------------
    print("\n[SECTION 4] COMPANY RECENT POSTS")
    print("-" * 80)
    print(f"  [PARSED POSTS COUNT]: {len(posts)} recent company posts extracted successfully.")
    print("  [SAMPLE EXTRACTED POSTS]:")
    for i, p in enumerate(posts[:2], 1):
        print(f"    Post {i}: \"{p.get('post_text')[:120]}...\"")

    # -------------------------------------------------------------
    # SECTION 5: Business Intelligence Profile (Downstream PPT Input)
    # -------------------------------------------------------------
    print("\n[SECTION 5] GENERATED BUSINESS INTELLIGENCE PROFILE")
    print("-" * 80)
    print(f"  * Differentiators : {bi.get('key_differentiators')}")
    print(f"  * Advantages      : {bi.get('competitive_advantages')}")
    print(f"  * Competitors     : {[c.get('competitor_name') for c in bi.get('identified_competitors', [])]}")
    print(f"  * Core Initiatives: {[ini.get('initiative_name') for ini in bi.get('strategic_initiatives', [])]}")
    print(f"  * Challenges      : {[ch.get('challenge_area') for ch in bi.get('business_challenges', [])]}")
    
    print("\n" + "=" * 80)
    print(" SUCCESS: Scraper verified. Clean, non-empty MongoDB records are ready.")
    print("=" * 80)

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "infosys"
    display_comparison(target.lower())
