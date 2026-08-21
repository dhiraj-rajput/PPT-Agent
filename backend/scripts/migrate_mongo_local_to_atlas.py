"""
scripts/migrate_mongo_local_to_atlas.py
----------------------------------------
Migrates all local MongoDB collections and documents to MongoDB Atlas.

Usage:
    python scripts/migrate_mongo_local_to_atlas.py
"""

import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pymongo import MongoClient
from pymongo.errors import BulkWriteError

try:
    import certifi
    CERTIFI_PATH = certifi.where()
except ImportError:
    CERTIFI_PATH = None

# ---- Migration Configuration ----
LOCAL_URI_CANDIDATES = [
    "mongodb://127.0.0.1:27017/",
    "mongodb://localhost:27017/",
]

from config.settings import settings

LOCAL_DB_NAMES = ["company_scraper", "ppt_agent_db", "orbitai", "winbidai"]

ATLAS_URI = os.environ.get("ATLAS_MONGO_URI") or settings.MONGO_URI
ATLAS_DB_NAME = os.environ.get("ATLAS_MONGO_DB_NAME") or getattr(settings, "MONGO_DB_NAME", "winbidai")

BATCH_SIZE = 500


def get_atlas_client() -> MongoClient:
    kwargs: dict[str, Any] = {
        "serverSelectionTimeoutMS": 10000,
        "connectTimeoutMS": 10000,
    }
    if CERTIFI_PATH:
        kwargs["tlsCAFile"] = CERTIFI_PATH
    return MongoClient(ATLAS_URI, **kwargs)


def find_active_local_db():
    for uri in LOCAL_URI_CANDIDATES:
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=2000)
            available_dbs = client.list_database_names()
            for db_name in LOCAL_DB_NAMES:
                if db_name in available_dbs:
                    db = client[db_name]
                    colls = [c for c in db.list_collection_names() if not c.startswith("system.")]
                    if colls:
                        return client, db, uri, db_name
        except Exception:
            continue
    return None, None, None, None


def migrate():
    print("=" * 70)
    print("🚀 MONGODB LOCAL TO ATLAS MIGRATION SCRIPT")
    print("=" * 70)

    # 1. Connect to Local Mongo
    local_client, local_db, local_uri, local_db_name = find_active_local_db()

    if local_db is None:
        print("❌ No active local MongoDB database found with data.")
        print(f"Checked local URIs: {LOCAL_URI_CANDIDATES}")
        print(f"Checked DB names: {LOCAL_DB_NAMES}")
        print("\nIf your local MongoDB is running on a custom port, update LOCAL_URI_CANDIDATES in this script.")
        return

    print(f"✅ Found Local MongoDB at: {local_uri}")
    print(f"📦 Source Database: '{local_db_name}'")

    collections = [c for c in local_db.list_collection_names() if not c.startswith("system.")]
    print(f"📚 Found {len(collections)} collections to migrate: {collections}\n")

    # 2. Connect to Atlas
    print(f"🌐 Connecting to MongoDB Atlas: {ATLAS_DB_NAME}...")
    try:
        atlas_client = get_atlas_client()
        atlas_client.admin.command("ping")
        atlas_db = atlas_client[ATLAS_DB_NAME]
        print(f"✅ Connected to MongoDB Atlas! Target DB: '{ATLAS_DB_NAME}'\n")
    except Exception as err:
        print(f"❌ Failed to connect to MongoDB Atlas: {err}")
        print("\n💡 TIP: Ensure your IP address is added to the MongoDB Atlas Network Access whitelist!")
        return

    # 3. Migrate Collection by Collection
    total_docs_migrated = 0
    for coll_name in collections:
        source_coll = local_db[coll_name]
        target_coll = atlas_db[coll_name]

        total_source_docs = source_coll.count_documents({})
        if total_source_docs == 0:
            print(f"⏩ Skipping empty collection '{coll_name}'")
            continue

        print(f"🔄 Migrating collection '{coll_name}' ({total_source_docs} documents)...")

        # Migrate Indexes first
        try:
            indexes = source_coll.index_information()
            for idx_name, idx_info in indexes.items():
                if idx_name == "_id_":
                    continue
                keys = idx_info["key"]
                options = {k: v for k, v in idx_info.items() if k not in ["key", "v", "ns"]}
                try:
                    target_coll.create_index(keys, **options)
                except Exception:
                    pass
        except Exception as idx_err:
            print(f"   ⚠️ Index setup warning for '{coll_name}': {idx_err}")

        # Batch Insert Documents
        inserted_count = 0
        batch = []
        for doc in source_coll.find({}):
            batch.append(doc)
            if len(batch) >= BATCH_SIZE:
                try:
                    res = target_coll.insert_many(batch, ordered=False)
                    inserted_count += len(res.inserted_ids)
                except BulkWriteError as bwe:
                    # Ignore duplicate key errors if re-running
                    inserted_count += bwe.details.get("nInserted", 0)
                batch = []

        if batch:
            try:
                res = target_coll.insert_many(batch, ordered=False)
                inserted_count += len(res.inserted_ids)
            except BulkWriteError as bwe:
                inserted_count += bwe.details.get("nInserted", 0)


        print(f"   ✅ Done! Successfully migrated {inserted_count}/{total_source_docs} documents into Atlas.")
        total_docs_migrated += inserted_count

    print("\n" + "=" * 70)
    print(f"🎉 MIGRATION COMPLETE! Total documents written to Atlas: {total_docs_migrated}")
    print("=" * 70)


if __name__ == "__main__":
    migrate()
