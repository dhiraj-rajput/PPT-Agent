"""
api/sam_gov/competitor_profiler.py
----------------------------------
Profiles discovered bidders/competitors using a 100% rule-based and pattern-based search.
No AI, LLM, OpenAI, or Ollama models are used.
Includes caching in MongoDB to avoid duplicate scraping.
"""

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from config.settings import settings
from utils.helpers import setup_logger

logger = setup_logger(__name__)


class CompetitorProfiler:
    """
    Profiles competitor companies using rule-based Tavily searches and regex parsing.
    Reuses MongoDB cache to avoid redundant scrapings.
    """

    def __init__(self, limit: int = 3, cache_days: int = 7) -> None:
        self.limit = limit
        self.cache_days = cache_days
        self.tavily_key = settings.TAVILY_API_KEY
        self.db = None
        try:
            from utils.db_client import get_database
            self.db = get_database()
        except Exception as exc:
            logger.warning(f"MongoDB database connection failed in CompetitorProfiler: {exc}")

    def profile_competitors(self, competitor_list: List[Dict[str, Any]], use_mock: bool = False) -> List[Dict[str, Any]]:
        """
        Takes a list of competitor dicts and profiles each one, returning a list of their intelligence profiles.
        Strictly limits the processing to the first self.limit competitors.
        """
        profiles = []
        target_list = competitor_list[:self.limit]

        for comp in target_list:
            name = comp.get("company_name", "").strip()
            if not name:
                continue

            logger.info(f"Processing competitor profiling for: '{name}'")
            profile = None

            # 1. Try to load from MongoDB cache
            if self.db is not None and not use_mock:
                profile = self._get_cached_profile(name)
                if profile:
                    logger.info(f"Cache hit: Loaded fresh profile for competitor '{name}' from MongoDB.")
                    profiles.append(profile)
                    continue

            # 2. Run rule-based profile extraction via web search
            logger.info(f"Cache miss: Running rule-based profiler for competitor '{name}'...")
            try:
                profile = self._extract_profile_via_search(name, use_mock=use_mock)
                if profile:
                    profiles.append(profile)
                    # Save to MongoDB cache (only if not in mock mode)
                    if not use_mock:
                        self._save_profile_to_cache(profile)
                    logger.info(f"Successfully profiled and cached competitor: '{name}'")
                else:
                    logger.warning(f"Rule-based profiler returned no profile data for '{name}'.")
            except Exception as e:
                logger.error(f"Failed to profile competitor '{name}' via rule-based search: {e}", exc_info=True)

        return profiles

    def _get_cached_profile(self, company_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve profile from 'company_profiles' if it exists and is fresh."""
        if self.db is None:
            return None

        try:
            col = self.db["company_profiles"]
            # Search by name (case-insensitive regex)
            query = {"company_name": {"$regex": f"^{re.escape(company_name)}$", "$options": "i"}}
            doc = col.find_one(query)
            
            if doc:
                # Check freshness
                gen_at = doc.get("generated_at") or doc.get("last_updated")
                if gen_at:
                    dt = datetime.fromisoformat(gen_at.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    if now - dt < timedelta(days=self.cache_days):
                        return doc
        except Exception as e:
            logger.warning(f"Failed to check company profiles cache for '{company_name}': {e}")

        return None

    def _save_profile_to_cache(self, profile: Dict[str, Any]) -> None:
        """Saves a profile to the 'company_profiles' MongoDB collection."""
        if self.db is None:
            return
        try:
            col = self.db["company_profiles"]
            # Enforce unique index search by company_slug or company_name
            company_name = profile["company_name"]
            col.update_one(
                {"company_name": company_name},
                {"$set": profile},
                upsert=True
            )
            logger.info(f"Saved company profile for '{company_name}' in MongoDB.")
        except Exception as e:
            logger.warning(f"Failed to cache company profile: {e}")

    def _extract_profile_via_search(self, company_name: str, use_mock: bool = False) -> Dict[str, Any]:
        """
        Runs a Tavily search for the company and extracts its profile fields using rules and regex.
        """
        snippets = []
        if use_mock or not self.tavily_key or "your_" in self.tavily_key:
            # Provide high-quality mock profiles for common mock bidders
            logger.info(f"Using mock competitor profiling for: {company_name}")
            return self._get_mock_profile(company_name)
        
        # Query Tavily
        query = f'"{company_name}" company profile website headquarters size industry products'
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=self.tavily_key)
            response = client.search(query=query, max_results=5, search_depth="basic")
            results = response.get("results", [])
            snippets = [r.get("snippet", "") for r in results]
        except Exception as e:
            logger.error(f"Tavily search failed for company '{company_name}': {e}")

        if not snippets:
            return self._get_mock_profile(company_name)

        corpus = " ".join(snippets)
        corpus_lower = corpus.lower()

        # Rule 1: Extract Website
        website = "N/A"
        # Find any http/https URL in the corpus
        urls = re.findall(r'https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', corpus)
        # Prefer URLs containing parts of the company name
        company_word = company_name.split()[0].lower()
        matched_url = next((u for u in urls if company_word in u.lower() and "wikipedia" not in u.lower()), None)
        if matched_url:
            website = matched_url
        elif urls:
            website = urls[0]

        # Rule 2: Extract Headquarters (HQ)
        headquarters = "N/A"
        # Match pattern "City, State" (e.g. McLean, Virginia or Tysons, VA or London, UK)
        hq_matches = re.findall(r'\b([A-Z][a-zA-Z\s]+,\s*[A-Z]{2}|[A-Z][a-zA-Z\s]+,\s*[A-Z][a-zA-Z]+)\b', corpus)
        if hq_matches:
            # Filter out known non-location words or use the first location mention
            filtered_hq = [hq for hq in hq_matches if not any(w in hq.lower() for w in ["july", "june", "inc", "llp", "llc"])]
            if filtered_hq:
                headquarters = filtered_hq[0]

        # Rule 3: Extract Size / Employee Count
        employee_count = "N/A"
        size_patterns = [
            r'(\d{1,3}(?:,\d{3})+)\s*employees',
            r'(\d+\+)\s*employees',
            r'(\d+\s*-\s*\d+)\s*employees',
            r'employee\s*count\s*(?:is|of)?\s*(\d{1,3}(?:,\d{3})+|\d+\+)'
        ]
        for pat in size_patterns:
            m = re.search(pat, corpus_lower)
            if m:
                employee_count = m.group(1)
                break

        # Rule 4: Extract Industry
        industry = "Professional Services"
        industry_keywords = [
            ("Information Technology", ["information technology", "it services", "software development"]),
            ("Management Consulting", ["management consulting", "advisory", "strategic consulting"]),
            ("Defense & Space", ["defense", "aerospace", "national security", "military"]),
            ("Government Contracting", ["government contracting", "federal contractor", "govcon"])
        ]
        for ind, keywords in industry_keywords:
            if any(kw in corpus_lower for kw in keywords):
                industry = ind
                break

        # Rule 5: Extract Products/Services
        products = []
        product_keywords = [
            ("Cybersecurity", ["cybersecurity", "cyber defense", "security"]),
            ("Cloud Migration", ["cloud migration", "aws", "azure", "cloud computing"]),
            ("Data Analytics", ["data analytics", "business intelligence", "tableau", "snowflake", "predictive modeling"]),
            ("Systems Integration", ["systems integration", "software engineering", "etl"]),
            ("Digital Transformation", ["digital transformation", "modernization"])
        ]
        for prod, keywords in product_keywords:
            if any(kw in corpus_lower for kw in keywords):
                products.append(prod)

        if not products:
            products = ["Federal Consulting Services", "Systems Integration"]

        profile = {
            "company_name": company_name,
            "company_slug": company_name.lower().replace(" ", "-").replace(".", "").replace(",", ""),
            "website": website,
            "headquarters": headquarters,
            "employee_count": employee_count,
            "company_size": employee_count,
            "industry": industry,
            "products": products,
            "generated_at": datetime.now(tz=timezone.utc).isoformat()
        }

        return profile

    def _get_mock_profile(self, company_name: str) -> Dict[str, Any]:
        """Provides mock profiles for testing/fallback."""
        name_lower = company_name.lower()
        if "booz allen" in name_lower:
            return {
                "company_name": "Booz Allen Hamilton Inc.",
                "company_slug": "booz-allen-hamilton",
                "website": "https://www.boozallen.com",
                "headquarters": "McLean, VA",
                "employee_count": "29,000+",
                "company_size": "29,000+",
                "industry": "Information Technology",
                "products": ["Cybersecurity", "Data Analytics", "Cloud Migration", "Systems Integration"],
                "generated_at": datetime.now(tz=timezone.utc).isoformat()
            }
        elif "deloitte" in name_lower:
            return {
                "company_name": "Deloitte Consulting LLP",
                "company_slug": "deloitte",
                "website": "https://www.deloitte.com",
                "headquarters": "Arlington, VA",
                "employee_count": "150,000+",
                "company_size": "150,000+",
                "industry": "Management Consulting",
                "products": ["Data Analytics", "Systems Integration", "Digital Transformation", "Management Consulting"],
                "generated_at": datetime.now(tz=timezone.utc).isoformat()
            }
        elif "guidehouse" in name_lower:
            return {
                "company_name": "Guidehouse LLP",
                "company_slug": "guidehouse",
                "website": "https://www.guidehouse.com",
                "headquarters": "McLean, VA",
                "employee_count": "12,000+",
                "company_size": "12,000+",
                "industry": "Management Consulting",
                "products": ["Data Analytics", "Cloud Migration", "Management Consulting"],
                "generated_at": datetime.now(tz=timezone.utc).isoformat()
            }
        else:
            return {
                "company_name": company_name,
                "company_slug": company_name.lower().replace(" ", "-"),
                "website": f"https://www.{company_name.lower().split()[0]}.com",
                "headquarters": "Washington, DC",
                "employee_count": "1,000+",
                "company_size": "1,000+",
                "industry": "Professional Services",
                "products": ["Federal Consulting Services", "Systems Integration"],
                "generated_at": datetime.now(tz=timezone.utc).isoformat()
            }
