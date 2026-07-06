"""
linkedin/inspect_mongo.py
-------------------------
Inspects the local MongoDB database to verify that the PPT-Agent
collections and documents exist.

Usage:
    python linkedin/inspect_mongo.py
"""

import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
from config.settings import settings

def inspect_db():
    print(f"Connecting to MongoDB at: {settings.MONGO_URI}")
    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=2000)
    
    try:
        # 1. List all database names
        db_names = client.list_database_names()
        print(f"\nAvailable Databases on server: {db_names}")
        
        # 2. Check if ppt_agent_db exists
        target_db = settings.MONGO_DB_NAME
        if target_db in db_names:
            print(f"[OK] Found target database: '{target_db}'")
        else:
            print(f"[ERROR] Target database '{target_db}' does not exist yet on this server.")
            print("Running a simulation run will create it automatically once data is inserted.")
            return

        db = client[target_db]
        
        # 3. List collections
        collections = db.list_collection_names()
        print(f"\nCollections in '{target_db}': {collections}")
        
        for col_name in collections:
            count = db[col_name].count_documents({})
            print(f" - Collection '{col_name}': {count} documents")
            
            # Print sample data
            if count > 0:
                print(f"   Sample document from '{col_name}':")
                sample = db[col_name].find_one()
                # Clean _id for pretty printing
                if sample and "_id" in sample:
                    sample["_id"] = str(sample["_id"])
                
                # Print key identity or metadata fields
                if col_name == "structured_linkedin":
                    print(f"     Slug: {sample.get('company_slug')}")
                    if 'identity' in sample and sample['identity']:
                        print(f"     Name: {sample['identity'].get('company_name')}")
                        print(f"     Industry: {sample['identity'].get('industry')}")
                    if 'bi_profile' in sample and sample['bi_profile']:
                        print(f"     Executive Summary: {sample['bi_profile'].get('executive_summary')[:80]}...")
                elif col_name == "raw_linkedin":
                    print(f"     Slug: {sample.get('company_slug')}")
                    print(f"     Layer: {sample.get('scrape_layer')}")
                    print(f"     Page URL: {sample.get('page_url')}")
                elif col_name == "scrape_logs":
                    print(f"     Slug: {sample.get('company_slug')}")
                    print(f"     Status: {sample.get('scrape_status')}")
                    print(f"     Duration: {sample.get('duration_seconds')}s")
                print()
                
    except Exception as e:
        print(f"Error connecting to or querying MongoDB: {e}")
        print("\nMake sure your local MongoDB instance is started. If you run Windows:")
        print("1. Open Command Prompt as Administrator")
        print("2. Run: net start MongoDB")

if __name__ == "__main__":
    inspect_db()
