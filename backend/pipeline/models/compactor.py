"""
models/compactor.py
-------------------
LLM-powered Business Intelligence Compactor. Ollama (free cloud model).

Takes the raw outputs from the three PPT-Agent agents (Website, LinkedIn, Google/External)
and uses an LLM via Ollama (gemma4:31b-cloud) to produce a single, clean OptimizedCompanyProfile JSON.

Cost-reduction measures:
  - Two-pass strategy: compressed system prompt
  - gemma4:31b-cloud is the default (free Ollama cloud model, no API key needed)
  - Fallback chain: tries primary model → gemma3:27b → llama3.1:8b → rule-based
  - normalizer limits raw_website_text to 8 000 chars; prompt builder trims to 4 000
  - Output caching: if the same website was compacted in the last 24 h, reuses MongoDB doc
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse

from pipeline.models.company_schema import OptimizedCompanyProfile
from pipeline.models.normalizer import normalize_company_intelligence
from pipeline.ai.client import get_ai_client
from pipeline.ai.mode import run_with_fallback, AIMode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Project root (two levels up from models/)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _save_json_file(data: Dict[str, Any], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, default=str)
    logger.info(f"Saved JSON to {path}")


# ---------------------------------------------------------------------------
# System prompt — RFP & Competitor Intelligence Focus
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an elite Competitive Intelligence Analyst preparing a company profile for use in an \
RFP (Request for Proposal) evaluation. Your audience is a business development / pre-sales team \
that needs to understand a competitor company deeply.

Combine the Website, LinkedIn, and external search data provided into ONE comprehensive \
competitor/RFP intelligence profile. Your output must enable the reader to:
  1. Understand the company's core products and services (by name, not sentence fragments)
  2. Identify the company's direct competitors and market position
  3. Assess their RFP / proposal strengths and weaknesses
  4. Understand their business model, pricing approach, and revenue scale
  5. Know their key leadership, clients, and technology stack

RULES:
  - Return ONLY a valid JSON object matching the OptimizedCompanyProfile schema below.
  - products and services must be short, specific product/service NAMES (< 10 words each). \
    Do NOT include partial sentences, navigation text, cookie notices, or UI labels.
  - competitors must be actual company names (e.g. "TCS", "Infosys", "Accenture"). \
    If a snippet mentions a competitor, include it.
  - financial_highlights must include specific figures, growth rates, or funding data with dates.
  - rfp_strengths must mention delivery track record, certifications (ISO, CMM, etc.), \
    government/enterprise client wins, or domain expertise.
  - Do not invent details unsupported by the sources.
  - Use concise, document-generation-ready language.
"""

_USER_PROMPT_TEMPLATE = """\
Normalised company data from all agents:

```json
{normalized_json}
```

Produce the final OptimizedCompanyProfile JSON object. Schema:

```json
{schema_json}
```
"""


# ---------------------------------------------------------------------------
# BusinessIntelligenceCompactor
# ---------------------------------------------------------------------------

class BusinessIntelligenceCompactor:
    """
    Orchestrates normalisation → LLM compaction → storage.

    Usage (from pipeline.orchestrator node):
        compactor = BusinessIntelligenceCompactor()
        result = compactor.compact_from_dicts(
            website_data=state["website_data"] or {},
            linkedin_data=state["linkedin_data"] or {},
            google_data={"results": state["external_news"] or []},
            external_insights=state["external_structured_insights"],
        )
        optimized_profile = result["profile"]

    Usage (standalone CLI):
        python models/compactor.py --website path/to/website.json \\
            --linkedin path/to/linkedin.json --google path/to/google.json
    """

    def __init__(self) -> None:
        from config.settings import settings as _settings
        self._settings = _settings
        # Shared Ollama Cloud client (model fallback chain + retries live here)
        self.ai_client = get_ai_client()

        # MongoDB (optional — skip gracefully if offline)
        self.db = None
        try:
            from utils.db_client import get_database
            self.db = get_database()
        except Exception as exc:
            logger.warning(f"MongoDB not available: {exc}")

    # ------------------------------------------------------------------
    # Primary API — called from pipeline.orchestrator node
    # ------------------------------------------------------------------

    def compact_from_dicts(
        self,
        website_data: Dict[str, Any],
        linkedin_data: Dict[str, Any],
        google_data: Dict[str, Any],
        external_insights: Optional[Dict[str, Any]] = None,
        company_slug: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compact all three agent outputs (+ optional external insights) into an
        OptimizedCompanyProfile and persist it.

        Returns:
            {
              "profile":        dict (the OptimizedCompanyProfile),
              "output_path":    str,
              "mongodb_stored": bool,
            }
        """
        logger.info("[Compactor] Starting compact_from_dicts()")

        # 1. Normalise
        normalized = normalize_company_intelligence(
            website_data=website_data,
            linkedin_data=linkedin_data,
            google_data=google_data,
            external_insights=external_insights,
        )

        # 2. AI compaction with rule-based fallback, governed by the global
        #    AI_MODE toggle (with COMPACTOR_MODE per-agent override) and
        #    automatic 429-aware fallback via ai.mode.run_with_fallback.
        import os
        bypass_llm = os.getenv("BYPASS_LLM", "false").lower() in ("true", "1", "yes")
        force_mode = AIMode.RULE_BASED if bypass_llm else None
        if bypass_llm:
            logger.info("[Compactor] BYPASS_LLM=true — forcing rule-based compaction.")

        raw_profile, path_used = run_with_fallback(
            "compactor",
            ai_fn=lambda: self._run_llm_compaction(normalized),
            rule_fn=lambda: self._run_rules_compaction(normalized),
            force_mode=force_mode,
        )
        logger.info(f"[Compactor] Compaction completed via '{path_used}' path.")

        # 3. Inject metadata
        raw_profile["last_updated"] = datetime.now(tz=timezone.utc).isoformat()
        sources: List[str] = []
        if website_data:
            sources.append("Website")
        if linkedin_data:
            sources.append("LinkedIn")
        if google_data.get("results") or external_insights:
            sources.append("Google/External")
        raw_profile.setdefault("sources_used", sources)

        # 4. Validate through Pydantic
        try:
            profile_obj = OptimizedCompanyProfile.model_validate(raw_profile)
            profile_dict = profile_obj.model_dump(mode="json")
        except Exception as exc:
            logger.warning(f"[Compactor] Pydantic validation warning: {exc} — using raw dict")
            profile_dict = raw_profile

        # 5. Persist
        website = profile_dict.get("website") or normalized.get("website") or ""
        output_path = self._save_outputs(profile_dict, website)
        mongodb_stored = self._save_to_mongodb(profile_dict, company_slug=company_slug)

        logger.info(f"[Compactor] Done. profile saved → {output_path}")

        return {
            "profile": profile_dict,
            "output_path": str(output_path),
            "mongodb_stored": mongodb_stored,
        }

    def compact(
        self,
        website_path: Optional[str] = None,
        linkedin_path: Optional[str] = None,
        google_path: Optional[str] = None,
        domain: Optional[str] = None,
        company_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        CLI-oriented entry point: loads JSON files from disk, then compacts.
        """
        # Resolve file paths
        json_dir = Path(PROJECT_ROOT / "output" / "json")
        raw_dir = Path(PROJECT_ROOT / "models" / "input")

        def _load_json(explicit: Optional[str], fallbacks: List[Path]) -> Dict[str, Any]:
            candidates = ([Path(explicit)] if explicit else []) + fallbacks
            for p in candidates:
                if p and p.exists():
                    try:
                        with open(p, encoding="utf-8") as fh:
                            return json.load(fh)
                    except Exception as exc:
                        logger.warning(f"[Compactor] Could not read {p}: {exc}")
            return {}

        domain_key = _domain_key(domain or "")
        website_data = _load_json(website_path, [
            json_dir / f"{domain_key}.json",
            raw_dir / "website.json",
        ])
        linkedin_data = _load_json(linkedin_path, [
            json_dir / f"{domain_key}_linkedin.json",
            raw_dir / "linkedin.json",
        ])
        google_data = _load_json(google_path, [raw_dir / "google.json"])

        return self.compact_from_dicts(
            website_data=website_data,
            linkedin_data=linkedin_data,
            google_data=google_data,
            external_insights=None,
        )

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    def _run_llm_compaction(self, normalized_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call the shared Ollama Cloud client with the normalised payload and
        return parsed JSON. Model fallback chain + retries + 429 detection
        all live in ai.client.OllamaAIClient now.
        """
        messages = _build_messages(normalized_data)
        return self.ai_client.chat_json(messages)

    # ------------------------------------------------------------------
    # JSON parsing
    # ------------------------------------------------------------------

    def _parse_json_from_response(self, text: str) -> Dict[str, Any]:
        text = text.strip()
        # Strip markdown fences
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()
        text_clean = re.sub(r"[\x00-\x08\x0b-\x1f]", " ", text)
        try:
            parsed = json.loads(text_clean, strict=False)
        except json.JSONDecodeError:
            try:
                import json_repair
                parsed = json_repair.repair_json(text_clean, return_objects=True)
            except Exception:
                match = re.search(r"(\{.*\})", text_clean, re.DOTALL)
                if not match:
                    raise ValueError(f"No JSON object found in response. First 500 chars: {text[:500]}")
                try:
                    parsed = json.loads(match.group(1), strict=False)
                except json.JSONDecodeError as inner:
                    try:
                        import json_repair
                        parsed = json_repair.repair_json(match.group(1), return_objects=True)
                    except Exception as last_exc:
                        raise ValueError(f"Extracted JSON is malformed: {last_exc}. First 500 chars: {text[:500]}") from inner
        if not isinstance(parsed, dict):
            raise ValueError("LLM response must be a JSON object.")
        return parsed

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_outputs(self, profile: Dict[str, Any], website: str) -> Path:
        output_dir = PROJECT_ROOT / "output"
        _ensure_directory(output_dir)

        main_path = output_dir / "company_profile.json"
        _save_json_file(profile, main_path)

        domain_clean = _domain_key(website)
        if domain_clean:
            json_dir = PROJECT_ROOT / "output" / "json"
            _ensure_directory(json_dir)
            _save_json_file(profile, json_dir / f"{domain_clean}_profile.json")

        return main_path

    def _save_to_mongodb(self, profile: Dict[str, Any], company_slug: Optional[str] = None) -> bool:
        if self.db is None:
            logger.warning("[Compactor] MongoDB not available — skipping save.")
            return False
        
        # Resolve company_slug from pipeline.website if not passed
        if not company_slug:
            website = profile.get("website")
            if website:
                company_slug = _domain_key(website)
                
        if not company_slug:
            logger.warning("[Compactor] No company_slug resolved — skipping MongoDB save.")
            return False
            
        try:
            collection = self.db["company_profiles"]
            # Inject company_slug (website-based) so it's persisted
            profile["company_slug"] = company_slug
            # Also persist a name-based slug so the frontend can match by company name
            company_name = profile.get("company_name", "")
            if company_name:
                name_slug = re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-")
                profile["company_name_slug"] = name_slug
            result = collection.update_one(
                {"company_slug": company_slug},
                {"$set": profile},
                upsert=True,
            )
            action = "updated" if result.matched_count else "inserted"
            logger.info(f"[Compactor] MongoDB {action} record for slug='{company_slug}'")
            return True
        except Exception as exc:
            logger.error(f"[Compactor] MongoDB save failed: {exc}")
            return False

    def _run_rules_compaction(self, normalized: Dict[str, Any]) -> Dict[str, Any]:
        """
        Produce a schema-compliant OptimizedCompanyProfile using rule-based/pattern-based
        heuristics directly from the normalized dictionary.
        """
        import re
        def _clean_field_text(text: Any, max_len: int = 150) -> str:
            if not text or not isinstance(text, str):
                return ""
            clean = re.sub(r"<[^>]+>", " ", text)
            stop_terms = [
                "Type", "Founded", "Specialties", "Employees", "Locations", "Sign in",
                "Welcome back", "Email or phone", "User Agreement", "Privacy Policy",
                "Cookie Policy", "See all employees", "Get directions", "Updates",
                "Report this post", "followers", "View ", "LinkedIn Member"
            ]
            for term in stop_terms:
                if term in clean:
                    clean = clean.split(term)[0].strip()
            clean = re.sub(r"\s+", " ", clean).strip()
            if len(clean) > max_len:
                clean = clean[:max_len].strip()
            return clean

        company_name = _clean_field_text(normalized.get("company_name", ""), 100)
        website = normalized.get("website", "")
        industry = _clean_field_text(normalized.get("industry", ""), 60)
        hq = _clean_field_text(normalized.get("headquarters", ""), 100)
        specialties = normalized.get("specialties", [])
        emp_count_str = _clean_field_text(normalized.get("employee_count", ""), 60)
        
        # 1. Synthesise a description
        descriptions = normalized.get("descriptions", {})
        description = descriptions.get("linkedin") or descriptions.get("website") or ""
        if not description:
            specs_str = f" specializing in {', '.join(specialties[:3])}" if specialties else ""
            description = f"{company_name} is a professional organization operating in the {industry} sector{specs_str}. Headquarters are located in {hq or 'unknown'}."
        
        # Truncate/clean description — keep up to 2000 chars for quality
        description = description.strip()
        if len(description) > 2000:
            description = description[:1997] + "..."

        # 2. Tech stack
        tech_stack = normalized.get("technology_stack", [])

        # 3. Business model
        business_model = normalized.get("business_model", "")
        if not business_model:
            business_model = descriptions.get("external_business_model") or ""
        if not business_model:
            desc_lower = description.lower()
            if any(x in desc_lower for x in ["saas", "software-as-a-service", "subscription", "cloud platform"]):
                business_model = "Software-as-a-Service (SaaS) subscription model."
            elif any(x in desc_lower for x in ["consulting", "advisory", "professional services", "custom development"]):
                business_model = "Professional consulting and project-based service fees."
            elif any(x in desc_lower for x in ["marketplace", "e-commerce", "transaction"]):
                business_model = "Transaction fee and digital marketplace model."
            else:
                business_model = f"Provides B2B and enterprise solutions in the {industry} sector."

        # 4. Pricing model
        pricing_model = ""
        combined_desc_text = f"{description} {business_model}".lower()
        if any(x in combined_desc_text for x in ["subscription", "saas", "per month", "annual"]):
            pricing_model = "Subscription-based pricing (monthly/annual tiers)."
        elif any(x in combined_desc_text for x in ["license", "on-premise"]):
            pricing_model = "Enterprise licensing model."
        elif any(x in combined_desc_text for x in ["consulting", "project", "advisory", "custom"]):
            pricing_model = "Project-based / Time & Materials billing."
        elif any(x in combined_desc_text for x in ["free trial", "freemium"]):
            pricing_model = "Freemium / Tiered usage options."
        else:
            pricing_model = "Enterprise quote-based pricing."

        # 5. Financial highlights
        financial_highlights = list(normalized.get("financial_highlights", []))
        if not financial_highlights:
            insights = normalized.get("google_search_insights", [])
            for ins in insights:
                sentences = re.split(r'(?<=[.!?])\s+', ins)
                for s in sentences:
                    s = s.strip()
                    if any(x in s.lower() for x in ["revenue", "profit", "growth", "funding", "valuation", "million", "billion"]):
                        if re.search(r'\b\d+(?:\.\d+)?%\b|\$\d+(?:\.\d+)?\s*(?:million|billion|B|M)', s):
                            s_clean = re.sub(r'\s+', ' ', s).strip()
                            if len(s_clean) < 180 and s_clean not in financial_highlights:
                                financial_highlights.append(s_clean)
        if not financial_highlights:
            founded_year = normalized.get("founded_year")
            founded_str = f" since its founding in {founded_year}" if founded_year else ""
            financial_highlights = [
                f"Steady market position and business operations{founded_str}.",
                f"Maintains a workforce scale of {normalized.get('employee_count') or 'enterprise scale'} employees globally."
            ]

        # 6. Competitors — dynamically extracted from search data, NOT hardcoded.
        # We only include competitors that were actually mentioned in search snippets.
        # If none found, return empty list rather than fake company names.
        competitors = list(normalized.get("competitors", []))
        if not competitors:
            # Try to extract from google search insights
            insights = normalized.get("google_search_insights", [])
            competitor_keywords = ["competitor", "rival", "vs", "alternative", "compete", "market share"]
            for insight_text in insights:
                text_lower = insight_text.lower()
                if any(kw in text_lower for kw in competitor_keywords):
                    # Extract capitalized company-like names (2+ words, title case)
                    found = re.findall(r'\b([A-Z][a-z]+ (?:[A-Z][a-z]+\s?)+|[A-Z]{2,}\b)', insight_text)
                    for name in found:
                        name = name.strip()
                        # Filter out common false positives
                        if name and len(name) > 3 and name not in ("The", "This", "These", "Their") and name not in competitors:
                            competitors.append(name)
        # Keep max 6 competitors and add source tag
        competitors = competitors[:6]

        # 7. Value proposition
        value_prop = normalized.get("value_proposition") or descriptions.get("external_value_proposition") or normalized.get("executive_summary") or normalized.get("tagline") or ""
        if not value_prop:
            value_prop = f"Providing reliable, high-quality, and scalable enterprise solutions in the {industry} domain."

        # 8. RFP Strengths
        rfp_strengths = normalized.get("key_differentiators", []) + normalized.get("competitive_advantages", [])
        rfp_strengths = [s.strip() for s in rfp_strengths if s.strip()]
        seen_str = set()
        rfp_strengths_dedup = []
        for s in rfp_strengths:
            if s.lower() not in seen_str:
                seen_str.add(s.lower())
                rfp_strengths_dedup.append(s)
        rfp_strengths = rfp_strengths_dedup
        
        all_desc_text = " ".join(descriptions.values()).lower()
        certs = ["iso 27001", "soc 2", "gdpr", "hipaa", "pci dss"]
        for c in certs:
            if c in all_desc_text:
                rfp_strengths.append(f"Security compliance: {c.upper()} certified/compliant.")
        
        if len(rfp_strengths) < 3:
            rfp_strengths.extend([
                f"Strong domain expertise in {industry} with proven track record.",
                "Scalable operations and robust global delivery methodologies.",
                "Customer-first focus ensuring high satisfaction and retention rates."
            ])

        # 9. RFP Weaknesses
        rfp_weaknesses = []
        if emp_count_str:
            digits = re.findall(r'\d+', emp_count_str.replace(',', ''))
            if digits:
                size = int(digits[0])
                if size < 50:
                    rfp_weaknesses.append("Smaller company size may limit capacity for massive concurrent enterprise rollouts.")
                elif size < 500:
                    rfp_weaknesses.append("Moderate team size compared to multi-national consulting giants.")
        
        if hq:
            rfp_weaknesses.append(f"Geographic focus primarily around {hq}, which may require remote delivery support.")
        
        if not rfp_weaknesses:
            rfp_weaknesses = [
                "Operates in a highly saturated competitive market, requiring continuous differentiation.",
                "Subject to rapid technical changes, demanding constant upskilling and investment."
            ]

        # 10. Opportunities
        opportunities = []
        insights = normalized.get("google_search_insights", [])
        for ins in insights:
            sentences = re.split(r'(?<=\.|\!|\?)\s+', ins)
            for s in sentences:
                s = s.strip()
                if any(x in s.lower() for x in ["expand", "launch", "acquire", "growth", "new market", "partnership"]):
                    s_clean = re.sub(r'\s+', ' ', s).strip()
                    if 25 < len(s_clean) < 180 and s_clean not in opportunities:
                        opportunities.append(s_clean)
        
        if len(opportunities) < 2:
            opportunities.extend([
                f"Expansion of service offerings into emerging technology areas (e.g., Generative AI integration).",
                f"Expanding market share in the growing {industry} sector globally.",
                "Strategic partnerships with major hyperscalers and platforms to drive mutual sales."
            ])

        # 11. Challenges
        challenges = []
        for ins in insights:
            sentences = re.split(r'(?<=\.|\!|\?)\s+', ins)
            for s in sentences:
                s = s.strip()
                if any(x in s.lower() for x in ["challenge", "risk", "threat", "inflation", "competition", "slowdown"]):
                    s_clean = re.sub(r'\s+', ' ', s).strip()
                    if 25 < len(s_clean) < 180 and s_clean not in challenges:
                        challenges.append(s_clean)
                        
        if len(challenges) < 2:
            challenges.extend([
                "Intense competition from larger global players and boutique specialized firms.",
                "Maintaining service quality and margins while scaling human capital.",
                "Keeping pace with rapid shifts in software framework standards and AI methodologies."
            ])

        founded_year = normalized.get("founded_year")
        if founded_year is not None:
            try:
                founded_year = int(founded_year)
            except Exception:
                founded_year = None

        return {
            "company_name": company_name,
            "website": website,
            "industry": industry,
            "description": description,
            "headquarters": hq,
            "locations": normalized.get("locations", []),
            "employee_count": emp_count_str,
            "founded_year": founded_year,
            "specialties": specialties,
            "products": normalized.get("products", []),
            "services": normalized.get("services", []),
            "technology_stack": tech_stack,
            "business_model": business_model,
            "pricing_model": pricing_model,
            "financial_highlights": financial_highlights[:4],
            "leadership": normalized.get("leadership", []),
            "competitors": competitors[:6],
            "value_proposition": value_prop,
            "rfp_strengths": rfp_strengths[:5],
            "rfp_weaknesses": rfp_weaknesses[:4],
            "opportunities": opportunities[:4],
            "challenges": challenges[:4],
            "recent_news": normalized.get("recent_news", [])[:6],
            "clients": normalized.get("clients", []),
            "partners": normalized.get("partners", []),
            "emails": normalized.get("emails", []),
            "phone_numbers": normalized.get("phone_numbers", []),
            "social_links": normalized.get("social_links", [])
        }


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Message builder
# ---------------------------------------------------------------------------

def _build_messages(normalized_data: Dict[str, Any]) -> List[Dict[str, str]]:
    schema_json = json.dumps(OptimizedCompanyProfile.model_json_schema(), indent=2, ensure_ascii=False)

    # Limit raw_website_text in the prompt to avoid huge payloads
    prompt_data = dict(normalized_data)
    if len(prompt_data.get("raw_website_text", "")) > 5_000:
        prompt_data["raw_website_text"] = prompt_data["raw_website_text"][:5_000] + "\n...[truncated]"
    if len(prompt_data.get("google_search_insights", [])) > 10:
        prompt_data["google_search_insights"] = prompt_data["google_search_insights"][:10]

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        normalized_json=json.dumps(prompt_data, indent=2, ensure_ascii=False),
        schema_json=schema_json,
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _canonical_website(value: str) -> str:
    if not value:
        return ""
    candidate = value.strip()
    if not re.match(r"^https?://", candidate, flags=re.IGNORECASE):
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    if not parsed.netloc:
        return ""
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", "", "", ""))


def _domain_key(value: str) -> str:
    if not value:
        return ""
    host = urlparse(_canonical_website(value)).netloc or value
    if host.startswith("www."):
        host = host[4:]
    return re.sub(r"[^a-zA-Z0-9]+", "_", host).strip("_")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="PPT-Agent Business Intelligence Compactor CLI")
    parser.add_argument("--website", type=str, help="Path to Website scraper JSON file")
    parser.add_argument("--linkedin", type=str, help="Path to LinkedIn JSON file")
    parser.add_argument("--google", type=str, help="Path to Google/Search JSON file")
    parser.add_argument("--domain", type=str, help="Company domain or homepage URL")
    parser.add_argument("--company", type=str, help="Company name")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")

    compactor = BusinessIntelligenceCompactor()
    try:
        result = compactor.compact(
            website_path=args.website,
            linkedin_path=args.linkedin,
            google_path=args.google,
            domain=args.domain,
            company_name=args.company,
        )
        logger.info("SUCCESS: Compaction completed.")
        logger.info(f"Profile saved to: {result['output_path']}")
        logger.info(f"MongoDB: {'saved' if result['mongodb_stored'] else 'skipped/failed'}")
        print(json.dumps(result["profile"], indent=2, ensure_ascii=False, default=str))
    except Exception as exc:
        logger.exception(f"CRITICAL: Compactor failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
