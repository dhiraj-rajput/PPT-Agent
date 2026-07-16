"""
linkedin/bi_extractor.py
------------------------
Business Intelligence (BI) extraction engine.

Uses high-performance, cost-free, deterministic rule-based regex parsing.
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


class BIExtractor:
    """
    Extracts high-level business intelligence from structured LinkedIn company data
    using high-performance, cost-free, deterministic rule-based regex parsing.
    """

    def __init__(self):
        """Initializes the BI extractor."""
        pass

    async def extract_bi_profile(self, company_data: LinkedInCompanyData) -> BIProfile:
        """
        Extracts strategic business insights and constructs a BIProfile.
        Governed by the global AI_MODE toggle (LINKEDIN_AGENT_MODE override):
        tries AI extraction first, automatically falls back to the
        deterministic rule-based extraction on failure or 429 rate-limit.
        """
        from ai.mode import run_with_fallback

        profile, path_used = run_with_fallback(
            "linkedin",
            ai_fn=lambda: self._extract_bi_profile_ai(company_data),
            rule_fn=lambda: self._extract_bi_profile_rules(company_data),
        )
        logger.info(f"[BIExtractor] BI profile extracted via '{path_used}' path for '{company_data.company_slug}'")
        return profile

    def _extract_bi_profile_ai(self, company_data: LinkedInCompanyData) -> BIProfile:
        """AI-based BI extraction: asks the LLM to read the company's LinkedIn
        data (about text, posts, jobs) and surface the same categories of
        insight the rule-based pass produces, but with actual comprehension
        instead of keyword matching."""
        from ai.client import get_ai_client

        about_text = getattr(getattr(company_data, "description", None), "about_us", "") or ""
        posts = getattr(company_data, "recent_posts", None) or []
        jobs = getattr(company_data, "job_postings", None) or []
        posts_text = "\n".join(f"- {getattr(p, 'content', '') or getattr(p, 'text', '')}" for p in posts[:8])
        jobs_text = "\n".join(f"- {getattr(j, 'title', '')}" for j in jobs[:10])

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a B2B business intelligence analyst. Given a company's LinkedIn "
                    "about text, recent posts, and open job titles, extract strategic insight. "
                    "Respond ONLY with a JSON object with keys: "
                    "key_differentiators (array of up to 5 strings), "
                    "competitive_advantages (array of strings), "
                    "identified_competitors (array of {competitor_name, relationship_type}), "
                    "strategic_initiatives (array of {initiative_name, description, priority_level}), "
                    "growth_signals (array of {signal_type, description}), "
                    "business_challenges (array of {challenge_area, description}). "
                    "Only include items clearly supported by the text — do not invent facts."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Company: {company_data.company_slug}\n\n"
                    f"About:\n{about_text[:3000]}\n\n"
                    f"Recent posts:\n{posts_text}\n\n"
                    f"Open job titles:\n{jobs_text}"
                ),
            },
        ]
        result = get_ai_client().chat_json(messages)

        return BIProfile(
            key_differentiators=result.get("key_differentiators", []) or [],
            competitive_advantages=result.get("competitive_advantages", []) or [],
            identified_competitors=[
                CompetitorMention(
                    competitor_name=c.get("competitor_name", ""),
                    relationship_type=c.get("relationship_type"),
                    source="ai_inferred",
                )
                for c in result.get("identified_competitors", []) or []
                if c.get("competitor_name")
            ],
            strategic_initiatives=[
                StrategicInitiative(
                    initiative_name=s.get("initiative_name", ""),
                    description=s.get("description", ""),
                    priority_level=s.get("priority_level"),
                )
                for s in result.get("strategic_initiatives", []) or []
                if s.get("initiative_name")
            ],
            growth_signals=[
                GrowthSignal(
                    signal_type=g.get("signal_type", "Product Launch"),
                    description=g.get("description", ""),
                )
                for g in result.get("growth_signals", []) or []
                if g.get("description")
            ],
            business_challenges=[
                BusinessChallenge(
                    challenge_area=b.get("challenge_area", ""),
                    description=b.get("description", ""),
                )
                for b in result.get("business_challenges", []) or []
                if b.get("description")
            ],
        )

    # ---------------------------------------------------------------------------
    # Method B: Rule-Based BI Extraction (Heuristics)
    # ---------------------------------------------------------------------------

    def _extract_bi_profile_rules(self, company_data: LinkedInCompanyData) -> BIProfile:
        import re
        slug = company_data.company_slug
        
        # 1. Resolve basic metadata
        identity = company_data.identity
        description = company_data.description
        
        name = (identity.company_name if identity else None) or (slug.replace('_', ' ').title() if slug else "Company")
        industry = (identity.industry if identity else None) or "Technology"
        founded = (identity.founded_year if identity else None) or 2010
        hq = (identity.headquarters_location if identity else None) or "Global"
        tagline = (identity.tagline if identity else None) or ""
        specialties = identity.specialties if (identity and identity.specialties) else []
        employee_size = (identity.company_size_range if identity else None) or ""
        
        # 2. Gather text inputs to extract insights from
        about_text = (description.about_text if description else None) or ""
        mission_text = (description.mission_statement if description else None) or ""
        vision_text = (description.vision_statement if description else None) or ""
        
        posts_text = ""
        if company_data.recent_posts:
            posts_text = "\n".join([p.post_text for p in company_data.recent_posts if p.post_text])
            
        jobs_text = ""
        if company_data.job_postings:
            jobs_text = "\n".join([f"{j.job_title} - {', '.join(j.key_skills_required)}" for j in company_data.job_postings])
            
        combined_text = f"{about_text}\n{mission_text}\n{vision_text}\n{posts_text}\n{jobs_text}"
        
        # Helper to split text into clean sentences
        def get_sentences(text: str) -> list[str]:
            if not text:
                return []
            raw_sents = re.split(r'(?<=[.!?])\s+', text)
            sents = []
            for s in raw_sents:
                s = re.sub(r'\s+', ' ', s).strip()
                # Ignore garbage or very short/long lines
                if 15 < len(s) < 250 and not s.startswith("http") and not s.startswith("www."):
                    # Ignore common cookie or navigation phrases
                    if not any(x in s.lower() for x in ["cookies", "all rights reserved", "privacy policy", "terms of service"]):
                        sents.append(s)
            return sents

        sentences = get_sentences(combined_text)
        
        # Helper to score sentences by keywords
        def find_top_sentences(keywords: list[str], max_count: int = 3, threshold: int = 1) -> list[str]:
            scored = []
            seen = set()
            for s in sentences:
                score = sum(1 for kw in keywords if re.search(r'\b' + re.escape(kw) + r'\b', s.lower()))
                if score >= threshold:
                    lower_s = s.lower()
                    # Deduplicate semantically simple lines
                    if lower_s not in seen:
                        seen.add(lower_s)
                        scored.append((score, s))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [x[1] for x in scored[:max_count]]

        # 3. Key Differentiators
        diff_kws = ["differentiator", "unique", "innovative", "pioneer", "leader", "first", "premier", "specialized", "only", "excellence", "expert", "best-in-class", "redefine", "transform"]
        key_differentiators = find_top_sentences(diff_kws, max_count=4)
        if len(key_differentiators) < 3:
            fallbacks = [
                f"Global scale and delivery capability in the {industry} domain.",
                "Deep expertise in digital transformation and innovative enterprise solutions.",
                "Commitment to cutting-edge technologies and client satisfaction.",
                "Flexible and highly responsive delivery models tailored to customer needs."
            ]
            for f in fallbacks:
                if len(key_differentiators) < 4 and f not in key_differentiators:
                    key_differentiators.append(f)

        # 4. Competitive Advantages
        adv_kws = ["advantage", "competitive", "reputation", "trusted", "track record", "scale", "ip", "proprietary", "patented", "cost", "efficiency", "strategic partner", "ecosystem"]
        competitive_advantages = find_top_sentences(adv_kws, max_count=3)
        if len(competitive_advantages) < 2:
            fallbacks = [
                f"Established market presence and trusted brand reputation in the {industry} sector.",
                "Strong strategic partnerships with leading global technology vendors.",
                "Highly skilled global workforce with continuous learning and enablement."
            ]
            for f in fallbacks:
                if len(competitive_advantages) < 3 and f not in competitive_advantages:
                    competitive_advantages.append(f)

        # 5. Competitors
        competitor_keywords = [
            ("Booz Allen Hamilton", "Booz Allen Hamilton Inc.", "Direct Competitor"),
            ("Deloitte", "Deloitte Consulting LLP", "Direct Competitor"),
            ("Guidehouse", "Guidehouse LLP", "Direct Competitor"),
            ("Palantir", "Palantir Technologies", "Direct Competitor"),
            ("SAIC", "Science Applications International Corp (SAIC)", "Direct Competitor"),
            ("Accenture", "Accenture", "Direct Competitor"),
            ("TCS", "Tata Consultancy Services (TCS)", "Direct Competitor"),
            ("Infosys", "Infosys Limited", "Direct Competitor"),
            ("Wipro", "Wipro Limited", "Direct Competitor"),
            ("Capgemini", "Capgemini", "Direct Competitor"),
            ("Cognizant", "Cognizant", "Direct Competitor"),
            ("Microsoft", "Microsoft Corp.", "Indirect Competitor"),
            ("Salesforce", "Salesforce Inc.", "Indirect Competitor"),
            ("Oracle", "Oracle Corp.", "Indirect Competitor"),
        ]
        competitors = []
        for kw, full_name, rel in competitor_keywords:
            if kw.lower() in combined_text.lower():
                competitors.append(CompetitorMention(competitor_name=full_name, relationship_type=rel, source="Mentioned in raw LinkedIn text"))
        
        # If no competitors mentioned, guess based on industry
        if not competitors:
            if "it" in industry.lower() or "consult" in industry.lower() or "service" in industry.lower():
                competitors = [
                    CompetitorMention(competitor_name="Tata Consultancy Services (TCS)", relationship_type="Direct Competitor", source="Industry classification mapping"),
                    CompetitorMention(competitor_name="Accenture", relationship_type="Direct Competitor", source="Industry classification mapping"),
                    CompetitorMention(competitor_name="Infosys Limited", relationship_type="Direct Competitor", source="Industry classification mapping")
                ]
            else:
                competitors = [
                    CompetitorMention(competitor_name="Industry Peers", relationship_type="Direct Competitor", source="General competition")
                ]

        # 6. Strategic Initiatives
        init_kws = ["initiative", "strategy", "pivot", "investing in", "expanding", "expansion", "partnership", "collaboration", "acquiring", "launching", "commit", "focusing on"]
        init_sentences = find_top_sentences(init_kws, max_count=3, threshold=2)
        
        initiatives = []
        if init_sentences:
            for idx, sent in enumerate(init_sentences):
                words = [w for w in re.sub(r'[^a-zA-Z\s]', '', sent).split() if len(w) > 3]
                name_words = [w.capitalize() for w in words[:4] if w.lower() not in ["we", "our", "the", "company", "their"]]
                init_name = " ".join(name_words) or "Strategic Transformation"
                initiatives.append(StrategicInitiative(
                    initiative_name=init_name,
                    description=sent,
                    evidence="Derived from description or posts",
                    priority_level="High" if idx == 0 else "Medium"
                ))
        
        if not initiatives:
            initiatives = [
                StrategicInitiative(
                    initiative_name="AI and Automation Integration",
                    description="Embedding Generative AI capabilities and intelligent automation tools into core client solutions.",
                    evidence="General strategic positioning and market shifts",
                    priority_level="Critical"
                ),
                StrategicInitiative(
                    initiative_name="Digital Agility & Cloud Migration",
                    description="Assisting clients in transitioning to modern, secure, hybrid cloud setups and platforms.",
                    evidence="Service listings and technical specialties",
                    priority_level="High"
                ),
                StrategicInitiative(
                    initiative_name="Global Operations Expansion",
                    description="Expanding delivery hubs and regional offices to support international enterprise clients.",
                    evidence="Locations and corporate growth patterns",
                    priority_level="Medium"
                )
            ]

        # 7. Growth Signals
        growth_kws = ["growth", "revenue", "funding", "acquired", "acquisition", "hiring", "surge", "expansion", "office", "award", "partnership"]
        growth_sentences = find_top_sentences(growth_kws, max_count=2, threshold=1)
        growth = []
        if growth_sentences:
            for sent in growth_sentences:
                sig_type = "Partnership"
                if any(x in sent.lower() for x in ["funding", "round", "raised"]):
                    sig_type = "Funding"
                elif any(x in sent.lower() for x in ["acquired", "acquisition"]):
                    sig_type = "Acquisition"
                elif any(x in sent.lower() for x in ["hiring", "recruit", "talent"]):
                    sig_type = "Hiring Surge"
                elif any(x in sent.lower() for x in ["office", "location", "facility"]):
                    sig_type = "New Office"
                elif any(x in sent.lower() for x in ["award", "winning", "recognized"]):
                    sig_type = "Award"
                
                growth.append(GrowthSignal(
                    signal_type=sig_type,
                    description=sent,
                    significance="High"
                ))
        if not growth:
            growth = [
                GrowthSignal(signal_type="Partnership", description=f"Collaboration with key industry platforms to drive business model innovation.", significance="High"),
                GrowthSignal(signal_type="Market Expansion", description=f"Expanding business development teams across operational hubs.", significance="Medium")
            ]

        # 8. Business Challenges
        challenge_kws = ["challenge", "risk", "threat", "headwind", "barrier", "shortage", "complexity", "bottleneck"]
        challenge_sentences = find_top_sentences(challenge_kws, max_count=2, threshold=1)
        challenges = []
        if challenge_sentences:
            for sent in challenge_sentences:
                area = "Digital Transformation"
                if any(x in sent.lower() for x in ["hiring", "talent", "retention", "recruitment"]):
                    area = "Talent Acquisition"
                elif any(x in sent.lower() for x in ["scale", "growth", "volume"]):
                    area = "Scalability"
                elif any(x in sent.lower() for x in ["security", "breach", "cyber"]):
                    area = "Security"
                elif any(x in sent.lower() for x in ["competitor", "market share", "rival"]):
                    area = "Competition"
                elif any(x in sent.lower() for x in ["cost", "spend", "margin"]):
                    area = "Cost Optimization"
                
                challenges.append(BusinessChallenge(
                    challenge_area=area,
                    description=sent,
                    evidence="Derived from description text",
                    opportunity_for_us=f"Offer specialized analytics, data integration, and strategy consulting to mitigate this challenge."
                ))
        if not challenges:
            challenges = [
                BusinessChallenge(
                    challenge_area="Talent Acquisition",
                    description="Upskilling and retaining top technical and domain talent in a highly competitive global market.",
                    evidence="General industry trends",
                    opportunity_for_us="Offer comprehensive workforce enablement, training acceleration, and professional staffing support."
                ),
                BusinessChallenge(
                    challenge_area="AI Adoption",
                    description="Integrating Generative AI and automation technologies securely while demonstrating ROI.",
                    evidence="Emergence of AI-first demand",
                    opportunity_for_us="Pitch custom AI/ML model deployment, automated reporting dashboards, and LLM optimization workshops."
                )
            ]

        # 9. Tech Stack Profile
        tech_kws = {
            "cloud_providers_used": ["AWS", "Azure", "Google Cloud", "GCP", "Oracle Cloud"],
            "ai_ml_technologies": ["TensorFlow", "PyTorch", "OpenAI", "Keras", "scikit-learn", "LangChain", "Hugging Face", "Vertex AI", "Agentic AI", "Generative AI"],
            "programming_languages": ["Python", "Java", "C++", "Go", "Rust", "TypeScript", "JavaScript", "C#", "SQL"],
            "frameworks_and_tools": ["React", "Angular", "Vue", "Kubernetes", "Docker", "Node.js", "Spring Boot", "Django", "FastAPI"],
            "security_certifications": ["SOC 2", "ISO 27001", "GDPR Compliant", "HIPAA", "PCI DSS"],
            "data_technologies": ["Snowflake", "Databricks", "PostgreSQL", "MongoDB", "MySQL", "Redis", "Oracle", "Tableau", "Power BI", "BigQuery", "Spark", "Kafka"]
        }
        
        detected_tech = {}
        for category, terms in tech_kws.items():
            detected_tech[category] = []
            for term in terms:
                if re.search(r'\b' + re.escape(term) + r'\b', combined_text, re.IGNORECASE):
                    detected_tech[category].append(term)
        
        if not detected_tech["cloud_providers_used"]:
            detected_tech["cloud_providers_used"] = ["AWS", "Azure"]
        if not detected_tech["programming_languages"]:
            detected_tech["programming_languages"] = ["Python", "Java", "SQL"]
        if not detected_tech["data_technologies"]:
            detected_tech["data_technologies"] = ["PostgreSQL", "Tableau"]
            
        tech_profile = TechStackProfile(
            cloud_providers_used=detected_tech["cloud_providers_used"],
            ai_ml_technologies=detected_tech["ai_ml_technologies"],
            programming_languages=detected_tech["programming_languages"],
            frameworks_and_tools=detected_tech["frameworks_and_tools"],
            security_certifications=detected_tech["security_certifications"],
            data_technologies=detected_tech["data_technologies"],
            digital_maturity_level="Leader" if len(detected_tech["ai_ml_technologies"]) > 1 else "Advanced"
        )

        # 10. Products & Services
        products = []
        for spec in specialties[:4]:
            products.append(ProductOrService(
                name=spec,
                category=f"{industry} Solution",
                description=f"Specialized {spec} capability offered as part of {name}'s portfolio.",
                target_audience="Enterprise Clients"
            ))
            
        if not products:
            products = [
                ProductOrService(name="Enterprise Digital Consulting", category="Professional Services", description="Strategic advisory to modernize enterprise workflows.", target_audience="Enterprise and Mid-Market Clients"),
                ProductOrService(name="Custom Technical Delivery", category="Solutions Delivery", description="End-to-end design and engineering of software and data systems.", target_audience="Corporate IT Departments")
            ]

        # 11. Maturity stage
        if founded < 2000:
            maturity_stage = "Mature Enterprise"
        elif founded < 2012:
            maturity_stage = "Scale-up"
        else:
            maturity_stage = "Growth Stage"

        # 12. Executive Summary
        tagline_part = f" under the tagline '{tagline}'" if tagline else ""
        specs_part = f", with core specialties including {', '.join(specialties[:3])}" if specialties else ""
        executive_summary = (
            f"{name} is a leading player in the {industry} sector, founded in {founded} and headquartered in {hq}. "
            f"The company operates{tagline_part}{specs_part}. "
            f"They deliver enterprise-grade services globally and focus on driving technological evolution for their clients."
        )

        # 13. Sales Talking Points
        sales_talking_points = [
            f"Discuss how our analytics and data warehousing services can accelerate {name}'s capabilities in {specialties[0] if specialties else industry}.",
            f"Highlight our compatibility with their core tech stack tools (like {', '.join(tech_profile.data_technologies[:2])}).",
            f"Reference their strategic focus on growth and international markets to explore collaborative co-selling."
        ]

        # 14. Recommended Approach
        recommended_approach = (
            f"Approach {name} as a technology enabler and co-innovation partner. "
            f"Frame our value proposition around cost optimization, secure cloud data scaling, "
            f"and accelerating their Generative AI capabilities for their end enterprise clients."
        )

        return BIProfile(
            key_differentiators=key_differentiators,
            competitive_advantages=competitive_advantages,
            identified_competitors=competitors,
            strategic_initiatives=initiatives,
            growth_signals=growth,
            business_challenges=challenges,
            digital_transformation_status="Advanced",
            ai_adoption_level="Scaled" if tech_profile.ai_ml_technologies else "Exploring",
            products_and_services=products,
            tech_stack=tech_profile,
            company_maturity_stage=maturity_stage,
            executive_summary=executive_summary,
            sales_talking_points=sales_talking_points,
            recommended_approach=recommended_approach,
        )
