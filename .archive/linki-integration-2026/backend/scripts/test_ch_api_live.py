"""
Live Test Script for Companies House API & UK Tenders
Tests profile retrieval, search, and tenders enrichment using CompaniesHouseClient.
"""

import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.companies_house.ch_client import CompaniesHouseClient
from app.companies_house.opportunities import CompaniesHouseTendersClient

def test_live_api():
    print("==================================================")
    print("Companies House API Live Integration Test")
    print("==================================================")

    ch_key = os.environ.get("COMPANIES_HOUSE_KEY", "").strip()
    print(f"Loaded API Key from env: {'****' + ch_key[-4:] if len(ch_key) >= 4 else '(empty)'}")

    client = CompaniesHouseClient(api_key=ch_key)

    # Test 1: Fetch ROLLS-ROYCE PLC profile (00044008)
    print("\n[Test 1] Fetching company profile for '00044008' (ROLLS-ROYCE PLC)...")
    profile = client.get_company_profile("00044008")
    print(f" -> Company Name: {profile.get('company_name')}")
    print(f" -> Status: {profile.get('company_status')}")
    print(f" -> Creation Date: {profile.get('date_of_creation')}")
    print(f" -> SIC Codes: {profile.get('sic_codes')}")

    # Test 2: Search for 'Avanya' or 'Technology' companies
    print("\n[Test 2] Searching companies with query 'Technology'...")
    search_res = client.search_companies("Technology", items_per_page=3)
    items = search_res.get("items", [])
    print(f" -> Total results found: {search_res.get('total_results')}")
    for item in items:
        print(f"    * [{item.get('company_number')}] {item.get('title')} ({item.get('company_status')})")

    # Test 3: Test UK Tenders client with CH enrichment
    print("\n[Test 3] Fetching UK Tenders enriched with Companies House details...")
    tenders_client = CompaniesHouseTendersClient(ch_client=client)
    tenders = tenders_client.search_uk_tenders(keyword="IT", limit=2)
    print(f" -> Retreived {len(tenders)} enriched tender records:")
    for t in tenders:
        print(f"    * ID: {t.get('id')}")
        print(f"      Title: {t.get('title')}")
        print(f"      Agency: {t.get('agency')}")
        print(f"      Source: {t.get('source')}")
        ch_meta = t.get("raw_companies_house_data", {}).get("company_profile", {})
        if ch_meta:
            print(f"      Enriched CH Profile: {ch_meta.get('company_name')} ({ch_meta.get('company_number')})")

    print("\n==================================================")
    print("SUCCESS: Companies House API integration test complete!")
    print("==================================================")

if __name__ == "__main__":
    test_live_api()
