import pymongo
from bson import json_util
import zipfile
import os
import shutil

def main():
    try:
        from config.settings import settings
        mongo_uri = settings.MONGO_URI
        db_name = settings.MONGO_DB_NAME
    except Exception:
        mongo_uri = "mongodb://localhost:27017/"
        db_name = "ppt_agent_db"

    client = pymongo.MongoClient(mongo_uri)
    db = client[db_name]

    zip_path = "company_scraper_db.zip"
    extract_dir = "company_scraper_restore_temp"

    if not os.path.exists(zip_path):
        print(f"Error: {zip_path} not found in current directory.")
        return

    os.makedirs(extract_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)

        print(f"Restoring database '{db_name}'...")
        for file in os.listdir(extract_dir):
            if file.endswith(".json"):
                coll_name = file[:-5]
                coll = db[coll_name]
                
                # Clear existing data in collection before restoring
                coll.delete_many({})
                
                with open(os.path.join(extract_dir, file), "r", encoding="utf-8") as f:
                    data = json_util.loads(f.read())
                    
                if data:
                    coll.insert_many(data)
                print(f" - Restored collection: {coll_name} ({len(data)} documents)")
    finally:
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        print("\nSuccess! Database restoration completed successfully!")

if __name__ == "__main__":
    main()