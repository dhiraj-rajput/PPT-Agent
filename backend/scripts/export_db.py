"""
scripts/export_db.py
---------------------
Exports the full MongoDB database into a compressed zip archive (company_scraper_db.zip)
so that another developer/friend can restore the exact same database state.
"""

import shutil
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bson import json_util
from utils.db_client import get_database
from utils.helpers import setup_logger

logger = setup_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = PROJECT_ROOT / "db_export_temp"
ZIP_OUTPUT = PROJECT_ROOT / "company_scraper_db.zip"


def export_database():
    db = get_database()
    collections = db.list_collection_names()
    logger.info(f"Starting database export for {len(collections)} collections...")

    if EXPORT_DIR.exists():
        shutil.rmtree(EXPORT_DIR)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    for coll_name in collections:
        coll = db[coll_name]
        count = 0
        file_path = EXPORT_DIR / f"{coll_name}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("[\n")
            first = True
            for doc in coll.find({}):
                if not first:
                    f.write(",\n")
                f.write("  " + json_util.dumps(doc))
                first = False
                count += 1
            f.write("\n]\n")
        logger.info(f" - Exported collection '{coll_name}': {count} documents")

    logger.info("Compressing exported collections into ZIP archive...")
    with zipfile.ZipFile(ZIP_OUTPUT, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for json_file in EXPORT_DIR.glob("*.json"):
            zip_file.write(json_file, arcname=json_file.name)

    shutil.rmtree(EXPORT_DIR)
    logger.info(f"Database export complete! Archive saved at: {ZIP_OUTPUT}")
    print(f"\n[SUCCESS] Database archive created: {ZIP_OUTPUT}")
    print("Send 'company_scraper_db.zip' to your friend. They can run 'python restore.py' to get the exact same DB!")


if __name__ == "__main__":
    export_database()
