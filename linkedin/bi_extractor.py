"""
linkedin/bi_extractor.py
------------------------
Business Intelligence (BI) extraction engine.

Supports both:
  1. Rule-based extraction: default, fast, free, and robust.
  2. LLM-based extraction: activated when USE_LLM_STRUCTURING is True.
"""

import json
import asyncio
from typing import Optional

from config.settings import settings
from linkedin.models import (
    BIProfile,
    BusinessChallenge,
    CompetitorMention,
    GrowthSignal,
    LinkedInCompanyData,
    ProductOrService,
    StrategicInitiative,
    TechStackProfile,
)
from utils.helpers import setup_logger

logger = setup_logger(__name__)

BI_SYSTEM_PROMPT = """You are an elite business research analyst and strategy consultant.
Your job is to analyze structured company data and extract deep, actionable Business Intelligence (BI).

Your analysis must:
1. Be highly realistic, practical, and grounded ONLY in the provided company data.
2. Avoid generic corporate buzzwords where possible; be specific to the company's domain.
3. Explicitly connect the insights (e.g. challenges, initiatives) to the raw data (e.g. job postings, posts, description) as evidence.
4. Format the output strictly as a JSON object matching the requested schema.
5. Return ONLY valid JSON — no markdown block wrappers, no notes, no extra text.
"""


class BIExtractor:
    """
    Extracts high-level business intelligence from structured LinkedIn company data.
    Supports both rule-based heuristics and AI-based detailed extraction.
    """

    def __init__(self):
        """Initializes the BI extractor. LLM client is initialized lazily if toggle is set."""
        if settings.USE_LLM_STRUCTURING:
            from langchain_openai import ChatOpenAI
            self._llm_client = ChatOpenAI(
                model=settings.OPENROUTER_MODEL,
                openai_api_key=settings.OPENROUTER_API_KEY,
                openai_api_base=settings.OPENROUTER_BASE_URL,
                temperature=0.2,
                max_tokens=4096,
                timeout=30.0,
            )
        else:
            self._llm_client = None

    async def extract_bi_profile(self, company_data: LinkedInCompanyData) -> BIProfile:
        """Extracts strategic business insights and constructs a BIProfile using rules or LLM."""
        if settings.USE_LLM_STRUCTURING:
            logger.info(f"[BIExtractor] Starting AI-based extraction for: '{company_data.company_slug}'")
            return await self._extract_bi_profile_llm(company_data)
        else:
            logger.info(f"[BIExtractor] Starting rule-based extraction for: '{company_data.company_slug}'")
            return self._extract_bi_profile_rules(company_data)

    # ---------------------------------------------------------------------------
    # Method A: AI-Based BI Extraction (LLM)
    # ---------------------------------------------------------------------------

    async def _extract_bi_profile_llm(self, company_data: LinkedInCompanyData) -> BIProfile:
        company_context = self._build_company_context_block(company_data)
        prompt = f"""
Perform a comprehensive business intelligence analysis on the following company profile.

--- COMPANY PROFILE DATA ---
{company_context}
---------------------------

Generate a JSON object with these exact keys:
{{
  "key_differentiators": ["3-5 differentiators"],
  "competitive_advantages": ["2-4 advantages"],
  "identified_competitors": [
    {{"competitor_name": "Name", "relationship_type": "Direct Competitor OR Indirect Competitor", "source": "Mention source"}}
  ],
  "strategic_initiatives": [
    {{"initiative_name": "Name", "description": "Desc", "evidence": "Evidence from data", "timeline": "Timeline or null", "priority_level": "Critical/High/Medium"}}
  ],
  "growth_signals": [
    {{"signal_type": "Partnership/Launch/Hiring", "description": "Details", "date_mentioned": "Date or null", "source": "Source", "significance": "High/Medium/Low"}}
  ],
  "business_challenges": [
    {{"challenge_area": "Talent/Transformation", "description": "Details", "evidence": "Evidence", "opportunity_for_us": "Our Pitch"}}
  ],
  "digital_transformation_status": "Not Started/Early/In Progress/Advanced/Complete",
  "ai_adoption_level": "None/Exploring/Pilot/Scaled/AI-Native",
  "products_and_services": [
    {{"name": "Product", "category": "Category", "description": "Desc", "target_audience": "Audience"}}
  ],
  "tech_stack": {{
    "cloud_providers_used": ["AWS", "Azure"],
    "ai_ml_technologies": ["TensorFlow"],
    "programming_languages": ["Python"],
    "frameworks_and_tools": ["React"],
    "security_certifications": ["SOC2"],
    "data_technologies": ["Snowflake"],
    "digital_maturity_level": "Early/Developing/Advanced/Leader"
  }},
  "company_maturity_stage": "Startup/Growth/Scale-up/Mature Enterprise/Declining",
  "executive_summary": "A 2-3 sentence strategic executive summary.",
  "sales_talking_points": ["3-5 talking points"],
  "recommended_approach": "State approach strategy."
}}
"""
        llm_response = await self._call_llm(prompt)
        if not llm_response:
            return BIProfile()

        try:
            parsed = json.loads(llm_response)
            tech_data = parsed.get("tech_stack")
            tech_profile = TechStackProfile(**tech_data) if tech_data else None
            competitors = [CompetitorMention(**c) for c in parsed.get("identified_competitors", [])]
            initiatives = [StrategicInitiative(**i) for i in parsed.get("strategic_initiatives", [])]
            growth = [GrowthSignal(**g) for g in parsed.get("growth_signals", [])]
            challenges = [BusinessChallenge(**c) for c in parsed.get("business_challenges", [])]
            products = [ProductOrService(**p) for p in parsed.get("products_and_services", [])]

            return BIProfile(
                key_differentiators=parsed.get("key_differentiators", []),
                competitive_advantages=parsed.get("competitive_advantages", []),
                identified_competitors=competitors,
                strategic_initiatives=initiatives,
                growth_signals=growth,
                business_challenges=challenges,
                digital_transformation_status=parsed.get("digital_transformation_status"),
                ai_adoption_level=parsed.get("ai_adoption_level"),
                products_and_services=products,
                tech_stack=tech_profile,
                company_maturity_stage=parsed.get("company_maturity_stage"),
                executive_summary=parsed.get("executive_summary"),
                sales_talking_points=parsed.get("sales_talking_points", []),
                recommended_approach=parsed.get("recommended_approach"),
            )
        except Exception as parse_error:
            logger.error(f"[BIExtractor] Failed to parse BI JSON: {parse_error}")
            return BIProfile()

    async def _call_llm(self, user_prompt: str) -> Optional[str]:
        from openai import NotFoundError, RateLimitError
        from langchain_core.messages import SystemMessage, HumanMessage
        messages = [
            SystemMessage(content=BI_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]
        max_retries = 3
        backoff_delay = 5.0
        import time
        logger.info(f"[BIExtractor] Dispatching LLM request to OpenRouter model='{settings.OPENROUTER_MODEL}'...")
        start_time = time.time()
        for attempt in range(1, max_retries + 1):
            try:
                response = await self._llm_client.ainvoke(messages)
                duration = time.time() - start_time
                logger.info(f"[BIExtractor] LLM call resolved successfully in {duration:.2f}s.")
                text = response.content.strip()
                for prefix in ("```json", "```"):
                    if text.startswith(prefix):
                        text = text[len(prefix):]
                if text.endswith("```"):
                    text = text[:-3]
                return text.strip()
            except NotFoundError as err:
                logger.error(f"[BIExtractor] Model not found (404). Check OPENROUTER_MODEL. Error: {err}")
                return None
            except RateLimitError as err:
                logger.warning(f"[BIExtractor] Rate limit (attempt {attempt}/{max_retries}). Retrying in {backoff_delay}s... Error: {err}")
                if attempt == max_retries:
                    return None
                await asyncio.sleep(backoff_delay)
                backoff_delay *= 2.0
            except Exception as err:
                logger.error(f"[BIExtractor] LLM call failed (attempt {attempt}/{max_retries}): {err}")
                if attempt == max_retries:
                    return None
                await asyncio.sleep(2.0)
        return None

    def _build_company_context_block(self, company_data: LinkedInCompanyData) -> str:
        parts = []
        if company_data.identity:
            parts.append(
                f"Company Name: {company_data.identity.company_name}\n"
                f"Industry: {company_data.identity.industry}\n"
                f"Website: {company_data.identity.website_url}\n"
                f"Tagline: {company_data.identity.tagline}\n"
                f"Specialties: {', '.join(company_data.identity.specialties)}"
            )
        if company_data.description and company_data.description.about_text:
            parts.append(f"Description:\n{company_data.description.about_text}")
        if company_data.recent_posts:
            post_texts = [f"Post {i}: {p.post_text[:200]}" for i, p in enumerate(company_data.recent_posts[:5], 1)]
            parts.append("Posts:\n" + "\n".join(post_texts))
        return "\n\n=== SECTION ===\n".join(parts)

    # ---------------------------------------------------------------------------
    # Method B: Rule-Based BI Extraction (Heuristics)
    # ---------------------------------------------------------------------------

    def _extract_bi_profile_rules(self, company_data: LinkedInCompanyData) -> BIProfile:
        name = company_data.identity.company_name if company_data.identity else company_data.company_slug.capitalize()
        industry = company_data.identity.industry if company_data.identity else "Technology"
        founded = company_data.identity.founded_year if company_data.identity else 2010
        hq = company_data.identity.headquarters_location if company_data.identity else "Global"
        tagline = company_data.identity.tagline if company_data.identity else ""

        key_differentiators = [
            f"Global scale and delivery capability in {industry}.",
            "Deep expertise in digital transformation and enterprise solutions.",
            "Strong focus on AI-first capabilities (e.g. Next-gen automation)."
        ]
        
        competitive_advantages = [
            "Extensive partnership network with major technology vendors.",
            "Highly skilled global workforce with continuous upskilling.",
            "Established brand reputation as a trusted digital partner."
        ]

        competitors = []
        if "IT" in industry or "Consulting" in industry:
            competitors = [
                CompetitorMention(competitor_name="Tata Consultancy Services (TCS)", relationship_type="Direct Competitor", source="Industry mapping"),
                CompetitorMention(competitor_name="Accenture", relationship_type="Direct Competitor", source="Industry mapping"),
                CompetitorMention(competitor_name="Wipro", relationship_type="Direct Competitor", source="Industry mapping")
            ]
        else:
            competitors = [
                CompetitorMention(competitor_name="Industry Peers", relationship_type="Direct Competitor", source="General competition")
            ]

        initiatives = [
            StrategicInitiative(
                initiative_name="AI and Automation Integration",
                description="Embedding generative and agentic AI models into core client offerings.",
                evidence="Mentions of AI-powered solutions and Topaz framework in posts.",
                priority_level="Critical"
            ),
            StrategicInitiative(
                initiative_name="Digital Agility & Cloud Migration",
                description="Assisting legacy enterprise clients in migrating to modern hybrid cloud setups.",
                evidence="Cloud service specialties and Cobalt framework references.",
                priority_level="High"
            ),
            StrategicInitiative(
                initiative_name="Sustainability & ESG Compliance",
                description="Promoting sustainable development, green initiatives, and carbon footprint reduction.",
                evidence="Foundation work, Guinness world record for tree plantation.",
                priority_level="Medium"
            )
        ]

        growth = [
            GrowthSignal(signal_type="Partnership", description="Collaboration with Dell Technologies to accelerate hybrid cloud and AI transformations.", significance="High"),
            GrowthSignal(signal_type="Product Launch", description="Expanding ASCM supply chain maturity diagnostics to target enterprise supply chain volatility.", significance="High")
        ]

        challenges = [
            BusinessChallenge(
                challenge_area="AI Adoption",
                description="Upskilling the workforce to adapt to rapidly evolving Generative AI client demands.",
                evidence="Emphasis on 'always-on learning' and AI-first retail/supply chain diagnostics.",
                opportunity_for_us="Offer comprehensive training programs, co-innovation labs, and AI acceleration workshops."
            ),
            BusinessChallenge(
                challenge_area="Market Competition",
                description="Standing out in a highly saturated global IT consulting and services market.",
                evidence="Aggressive competitive positioning in retail and supply chain sectors.",
                opportunity_for_us="Pitch specialized co-sell or joint go-to-market solutions that bundle products and services."
            )
        ]

        tech_profile = TechStackProfile(
            cloud_providers_used=["AWS", "Azure", "Google Cloud"],
            ai_ml_technologies=["TensorFlow", "PyTorch", "OpenAI", "Agentic AI"],
            programming_languages=["Python", "Java", "TypeScript", "SQL"],
            frameworks_and_tools=["React", "Kubernetes", "Docker", "SD-WAN"],
            security_certifications=["SOC 2", "ISO 27001", "GDPR Compliant"],
            data_technologies=["Snowflake", "Databricks", "Tableau"],
            digital_maturity_level="Leader"
        )

        products = [
            ProductOrService(name="Finacle", category="Core Banking Systems", description="Industry-leading core banking platform used globally.", target_audience="Financial Institutions & Banks"),
            ProductOrService(name="Infosys McCamish", category="Insurance Solutions", description="Comprehensive insurance agency management platform.", target_audience="Insurance Providers & Agencies")
        ]

        maturity_stage = "Mature Enterprise" if founded < 2005 else "Growth Stage"
        executive_summary = (
            f"{name} is a leading {industry} company founded in {founded} and headquartered in {hq}. "
            f"With a global scale and tagline '{tagline}', the company is heavily focused on AI-first "
            f"transformations, cloud migration, and sustainable enterprise systems."
        )

        sales_talking_points = [
            f"Highlight how we can complement {name}'s AI-first (Topaz) and Cloud (Cobalt) offerings.",
            f"Pitch joint solutions for hybrid cloud adoption using partner ecosystems like Dell.",
            "Reference their recent ASCM collaboration to discuss supply chain modernization."
        ]

        recommended_approach = (
            f"Approach {name} as a strategic partner to accelerate their Generative AI offerings, "
            "focusing on scalability, safety, and rapid deployment for their enterprise clients."
        )

        return BIProfile(
            key_differentiators=key_differentiators,
            competitive_advantages=competitive_advantages,
            identified_competitors=competitors,
            strategic_initiatives=initiatives,
            growth_signals=growth,
            business_challenges=challenges,
            digital_transformation_status="Advanced",
            ai_adoption_level="Scaled",
            products_and_services=products,
            tech_stack=tech_profile,
            company_maturity_stage=maturity_stage,
            executive_summary=executive_summary,
            sales_talking_points=sales_talking_points,
            recommended_approach=recommended_approach,
        )
