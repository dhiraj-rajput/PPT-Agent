"""
app/core/company_catalog.py
----------------------------
Loads and indexes the authoritative OrbitAvanya services and add-ons catalog
from private/OrbitAvanya_Services_ADD.xlsx.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EXCEL_PATH = PROJECT_ROOT / "private" / "OrbitAvanya_Services_ADD.xlsx"

_cached_catalog: Optional[Dict[str, Any]] = None


def load_services_catalog() -> Dict[str, Any]:
    """
    Parses both sheets ('Services' and 'Premium Enterprise Add-ons') from
    OrbitAvanya_Services_ADD.xlsx into a structured, searchable catalog.
    """
    global _cached_catalog
    if _cached_catalog is not None:
        return _cached_catalog

    services: List[Dict[str, Any]] = []
    addons: List[Dict[str, Any]] = []
    categories: Dict[str, List[Dict[str, Any]]] = {}

    if EXCEL_PATH.exists():
        try:
            import openpyxl
            wb = openpyxl.load_workbook(str(EXCEL_PATH), data_only=True)

            # 1. Parse 'Services' sheet
            if "Services" in wb.sheetnames:
                ws = wb["Services"]
                for row in list(ws.iter_rows(min_row=2, values_only=True)):
                    if not row or not any(row):
                        continue
                    # Headers: #, NAIC Code, Service Category, Service, Description
                    idx = row[0] if len(row) > 0 else None
                    naics = str(row[1]).strip() if len(row) > 1 and row[1] else "541511"
                    category = str(row[2]).strip() if len(row) > 2 and row[2] else "General"
                    service_name = str(row[3]).strip() if len(row) > 3 and row[3] else ""
                    description = str(row[4]).strip() if len(row) > 4 and row[4] else ""

                    if not service_name:
                        continue

                    item = {
                        "id": idx,
                        "naics_code": naics,
                        "category": category,
                        "service_name": service_name,
                        "description": description,
                    }
                    services.append(item)
                    categories.setdefault(category, []).append(item)

            # 2. Parse 'Premium Enterprise Add-ons' sheet
            if "Premium Enterprise Add-ons" in wb.sheetnames:
                ws_add = wb["Premium Enterprise Add-ons"]
                for row in list(ws_add.iter_rows(min_row=2, values_only=True)):
                    if not row or not any(row):
                        continue
                    name = str(row[0]).strip() if len(row) > 0 and row[0] else ""
                    price = str(row[1]).strip() if len(row) > 1 and row[1] else "Custom Pricing"

                    if name and name.lower() != "service":
                        addons.append({
                            "service_name": name,
                            "price": price,
                        })

            logger.info(f"[CompanyCatalog] Successfully loaded {len(services)} services and {len(addons)} add-ons from Excel.")
        except Exception as exc:
            logger.warning(f"[CompanyCatalog] Failed to parse Excel catalog {EXCEL_PATH}: {exc}")

    # Fallback to hardcoded profiles if Excel parsing fails or yields empty lists
    if not services:
        services = [
            {"id": 1, "naics_code": "541511", "category": "AI Solutions", "service_name": "AI Chatbot & RAG", "description": "Enterprise RAG & Conversational AI"},
            {"id": 2, "naics_code": "541511", "category": "Custom Software", "service_name": "ERP & CRM Development", "description": "Enterprise ERP, CRM & HRMS Systems"},
            {"id": 3, "naics_code": "541511", "category": "Web Development", "service_name": "Government Portal", "description": "Secure Citizen Portals & CMS"},
            {"id": 4, "naics_code": "541511", "category": "Mobile Apps", "service_name": "Flutter & Native Apps", "description": "iOS & Android Cross-Platform Applications"},
        ]

    _cached_catalog = {
        "services": services,
        "addons": addons,
        "categories": categories,
    }
    return _cached_catalog


def get_catalog_products() -> List[Dict[str, Any]]:
    """Returns a list of structured product profiles matching the format expected by generators."""
    catalog = load_services_catalog()
    products: List[Dict[str, Any]] = []

    for cat_name, cat_items in catalog["categories"].items():
        features = [item["service_name"] for item in cat_items]
        descriptions = " ".join(item["description"] for item in cat_items if item["description"])
        
        products.append({
            "product_name": f"OrbitAvanya {cat_name}",
            "company_name": "OrbitAvanya Tech LLP",
            "industry_domain": cat_name,
            "about_text": f"OrbitAvanya's {cat_name} suite provides: {descriptions[:300]}...",
            "key_features": features,
            "technology_stack": {
                "frontend": ["React", "Next.js", "Flutter"],
                "backend": ["Python", "FastAPI", "Node.js"],
                "database": ["PostgreSQL", "MongoDB"],
                "cloud": ["AWS", "Azure", "Docker"]
            },
            "security_and_compliance": ["ISO 27001 Ready", "SOC 2 Type II", "Role-Based Access Control", "FIPS 140 Encryption"],
            "pricing_model": "Custom Enterprise SLA / Fixed Milestone"
        })

    return products
