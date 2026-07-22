"""
scripts/import_company_catalog.py
-----------------------------------
Seeds the MongoDB `company_catalog` collection from the OrbitAvanya
services + add-ons Excel workbook, so document generation reads real
service/pricing data instead of the hardcoded fallback stub.

This is the source of truth app/core/company_catalog.py reads at runtime —
run this once after updating the Excel file, or whenever you want to refresh
Mongo from a new version of it. Safe to re-run (upserts the single catalog
document, doesn't duplicate).

Usage:
    python scripts/import_company_catalog.py
    python scripts/import_company_catalog.py --file /path/to/OrbitAvanya_Services_ADD.xlsx
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.company_catalog import _parse_excel_workbook, MONGO_COLLECTION, MONGO_DOC_ID  # noqa: E402
from utils.db_client import get_collection  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed MongoDB company_catalog from the services Excel workbook.")
    parser.add_argument(
        "--file",
        default=str(PROJECT_ROOT / "private" / "OrbitAvanya_Services_ADD.xlsx"),
        help="Path to the OrbitAvanya_Services_ADD.xlsx workbook.",
    )
    args = parser.parse_args()

    xlsx_path = Path(args.file)
    if not xlsx_path.exists():
        print(f"ERROR: Excel file not found at {xlsx_path}")
        print("Pass --file /path/to/OrbitAvanya_Services_ADD.xlsx if it's somewhere else.")
        sys.exit(1)

    catalog = _parse_excel_workbook(xlsx_path)
    if not catalog or not catalog.get("services"):
        print(f"ERROR: No services parsed from {xlsx_path} — check the sheet names/headers match "
              "'Services' (#, NAIC Code, Service Category, Service, Description) and "
              "'Premium Enterprise Add-ons' (Service, Starting Price (USD)).")
        sys.exit(1)

    col = get_collection(MONGO_COLLECTION)
    result = col.update_one(
        {"_id": MONGO_DOC_ID},
        {
            "$set": {
                "services": catalog["services"],
                "addons": catalog["addons"],
                "source_file": xlsx_path.name,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )

    print(
        f"Imported {len(catalog['services'])} services and {len(catalog['addons'])} add-ons "
        f"into MongoDB collection '{MONGO_COLLECTION}' (doc _id='{MONGO_DOC_ID}')."
    )
    print(f"Matched: {result.matched_count}, Modified: {result.modified_count}, Upserted: {bool(result.upserted_id)}")


if __name__ == "__main__":
    main()
