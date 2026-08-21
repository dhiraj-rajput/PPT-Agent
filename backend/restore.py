"""
restore.py
----------
Restores the complete MongoDB database state from company_scraper_db.zip.
"""

import shutil
import zipfile
from pathlib import Path

from bson import json_util
from config.settings import settings


def restore_database():
    try:
        from utils.db_client import get_database
        db = get_database()
        db_name = db.name
    except Exception:
        from urllib.parse import urlparse

        import pymongo
        _parsed = urlparse(settings.MONGO_URI)
        _safe_uri = f"{_parsed.scheme}://***:***@{_parsed.hostname}"
        print(f"[INFO] Using direct PyMongo connection to {_safe_uri}")
        client = pymongo.MongoClient(settings.MONGO_URI)
        db_name = settings.MONGO_DB_NAME
        db = client[db_name]

    PROJECT_ROOT = Path(__file__).resolve().parent
    zip_path = PROJECT_ROOT / "company_scraper_db.zip"
    if not zip_path.exists():
        zip_path = PROJECT_ROOT / "private" / "company_scraper_db.zip"

    if not zip_path.exists():
        print(f"[ERROR] Could not find 'company_scraper_db.zip' at {zip_path}.")
        print("Please place 'company_scraper_db.zip' in the project root directory and run this script again.")
        return

    extract_dir = PROJECT_ROOT / "db_restore_temp"
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)

        print(f"\nRestoring database '{db_name}' from {zip_path.name}...")
        for json_file in extract_dir.glob("*.json"):
            coll_name = json_file.stem
            coll = db[coll_name]

            with open(json_file, "r", encoding="utf-8") as f:
                data = json_util.loads(f.read())

            if data:
                # Only delete existing data AFTER we've successfully parsed
                # non-empty replacement data. This prevents an empty/corrupt
                # backup from wiping the production collection.
                coll.delete_many({})
                coll.insert_many(data)
                print(f"  [OK] Restored collection '{coll_name}': {len(data)} documents")
            else:
                print(f"  - Collection '{coll_name}' is empty in backup, skipping (data preserved)")

        print(f"\n[SUCCESS] Database '{db_name}' restored successfully!")
    finally:
        if extract_dir.exists():
            shutil.rmtree(extract_dir)


if __name__ == "__main__":
    restore_database()