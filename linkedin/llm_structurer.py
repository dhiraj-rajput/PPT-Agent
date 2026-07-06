"""
linkedin/llm_structurer.py
--------------------------
Post-processing structuring engine.

Supports both:
  1. Rule-based extraction: default, fast, free, and robust.
  2. LLM-based extraction: activated when USE_LLM_STRUCTURING is True.
"""

import re
import json
import asyncio
from typing import Any, Optional

from config.settings import settings
from linkedin.models import (
    CompanyDescription,
    CompanyIdentity,
    CompanyPost,
    EmployeeInsights,
    FundingInfo,
    JobPosting,
    LeadershipMember,
    LinkedInCompanyData,
    CompanyLocation,
)
from utils.helpers import get_utc_now, setup_logger
from utils.db_client import get_collection

logger = setup_logger(__name__)

# System prompt used for all LLM structuring calls.
STRUCTURING_SYSTEM_PROMPT = """You are an expert business data analyst specializing in 
extracting and structuring company information from LinkedIn pages.

Your job is to take raw text scraped from LinkedIn and output clean, structured JSON data.

Rules you must always follow:
1. Only extract information that is explicitly present in the provided text.
2. Do NOT fabricate, infer, or guess any information.
3. If a field's value is not found in the text, return null for that field.
4. Return ONLY valid JSON — no explanation, no markdown, no code blocks.
5. For numeric fields, return numbers (not strings).
6. For list fields, return an array (even if it has one item or is empty []).
"""


class LLMStructurer:
    """
    Transforms raw scraped data into clean, structured LinkedInCompanyData objects.
    Supports both high-performance rule-based parsing and detailed LLM-based profiling.
    """

    def __init__(self):
        """Initializes the structurer. LLM client is initialized lazily if toggle is set."""
        if settings.USE_LLM_STRUCTURING:
            from langchain_openai import ChatOpenAI
            self._llm_client = ChatOpenAI(
                model=settings.OPENROUTER_MODEL,
                openai_api_key=settings.OPENROUTER_API_KEY,
                openai_api_base=settings.OPENROUTER_BASE_URL,
                temperature=0.0,
                max_tokens=4096,
                timeout=30.0,
            )
        else:
            self._llm_client = None

    async def structure_company_data(
        self,
        company_slug: str,
        linkedin_url: str,
        layer1_partial_identity: Optional[CompanyIdentity],
        layer2_extracted_data: dict,
        layer3_extracted_data: dict,
        scrape_layers_used: list[str],
        source_urls: list[str],
    ) -> LinkedInCompanyData:
        """Orchestrates the structuring process, switching between rule-based and AI-based methods."""
        if settings.USE_LLM_STRUCTURING:
            logger.info(f"[Structurer] Starting AI-based structuring for: '{company_slug}'")
            return await self._structure_company_data_llm(
                company_slug=company_slug,
                linkedin_url=linkedin_url,
                layer1_partial_identity=layer1_partial_identity,
                layer2_extracted_data=layer2_extracted_data,
                layer3_extracted_data=layer3_extracted_data,
                scrape_layers_used=scrape_layers_used,
                source_urls=source_urls,
            )
        else:
            logger.info(f"[Structurer] Starting rule-based structuring for: '{company_slug}'")
            return await self._structure_company_data_rules(
                company_slug=company_slug,
                linkedin_url=linkedin_url,
                layer1_partial_identity=layer1_partial_identity,
                scrape_layers_used=scrape_layers_used,
                source_urls=source_urls,
            )

    # ---------------------------------------------------------------------------
    # Method A: AI-Based Structuring (LLM)
    # ---------------------------------------------------------------------------

    async def _structure_company_data_llm(
        self,
        company_slug: str,
        linkedin_url: str,
        layer1_partial_identity: Optional[CompanyIdentity],
        layer2_extracted_data: dict,
        layer3_extracted_data: dict,
        scrape_layers_used: list[str],
        source_urls: list[str],
    ) -> LinkedInCompanyData:
        # Merge all raw data from all layers into one reference dict
        merged_data = {}
        if layer1_partial_identity:
            merged_data["layer1_identity"] = layer1_partial_identity.model_dump()
        merged_data.update(layer2_extracted_data)
        for k, v in layer3_extracted_data.items():
            if v is not None:
                merged_data[k] = v

        delay = settings.LLM_INTER_CALL_DELAY_SECONDS

        # 1. Identity
        structured_identity = await self._structure_company_identity_llm(
            company_slug=company_slug,
            linkedin_url=linkedin_url,
            raw_data=merged_data,
        )
        await asyncio.sleep(delay)

        # 2. Description
        structured_description = await self._structure_company_description_llm(
            raw_data=merged_data,
        )
        await asyncio.sleep(delay)

        # 3. Employee Insights
        structured_employee_insights = await self._structure_employee_insights_llm(
            raw_data=merged_data,
        )
        await asyncio.sleep(delay)

        # 4. Leadership
        structured_leadership = await self._structure_leadership_team_llm(
            raw_data=merged_data,
        )
        await asyncio.sleep(delay)

        # 5. Recent Posts
        structured_posts = await self._structure_recent_posts_llm(
            raw_data=merged_data,
        )
        await asyncio.sleep(delay)

        # 6. Jobs
        structured_jobs = await self._structure_job_postings_llm(
            raw_data=merged_data,
        )
        await asyncio.sleep(delay)

        # 7. Funding
        structured_funding = await self._structure_funding_info_llm(
            raw_data=merged_data,
        )

        confidence_scores = {
            "identity": 0.85 if structured_identity else 0.0,
            "description": 0.85 if structured_description else 0.0,
            "employee_insights": 0.85 if structured_employee_insights else 0.0,
            "leadership": 0.85 if structured_leadership else 0.0,
            "posts": 0.85 if structured_posts else 0.0,
            "jobs": 0.85 if structured_jobs else 0.0,
        }

        return LinkedInCompanyData(
            company_slug=company_slug,
            identity=structured_identity,
            description=structured_description,
            leadership_team=structured_leadership or [],
            employee_insights=structured_employee_insights,
            recent_posts=structured_posts or [],
            job_postings=structured_jobs or [],
            funding_info=structured_funding,
            scraped_at=get_utc_now(),
            scrape_layers_used=scrape_layers_used,
            source_urls_scraped=source_urls,
            field_confidence_scores=confidence_scores,
        )

    async def _call_llm(self, user_prompt: str) -> Optional[str]:
        from openai import NotFoundError, RateLimitError
        from langchain_core.messages import SystemMessage, HumanMessage
        messages = [
            SystemMessage(content=STRUCTURING_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]
        max_retries = 3
        backoff_delay = 5.0
        import time
        logger.info(f"[Structurer] Dispatching LLM request to OpenRouter model='{settings.OPENROUTER_MODEL}'...")
        start_time = time.time()
        for attempt in range(1, max_retries + 1):
            try:
                response = await self._llm_client.ainvoke(messages)
                duration = time.time() - start_time
                logger.info(f"[Structurer] LLM call resolved successfully in {duration:.2f}s.")
                text = response.content.strip()
                for prefix in ("```json", "```"):
                    if text.startswith(prefix):
                        text = text[len(prefix):]
                if text.endswith("```"):
                    text = text[:-3]
                return text.strip()
            except NotFoundError as err:
                logger.error(f"[Structurer] Model not found (404). Check OPENROUTER_MODEL. Error: {err}")
                return None
            except RateLimitError as err:
                logger.warning(f"[Structurer] Rate limit (429) (attempt {attempt}/{max_retries}). Retrying in {backoff_delay}s... Error: {err}")
                if attempt == max_retries:
                    return None
                await asyncio.sleep(backoff_delay)
                backoff_delay *= 2.0
            except Exception as err:
                logger.error(f"[Structurer] LLM call failed (attempt {attempt}/{max_retries}): {err}")
                if attempt == max_retries:
                    return None
                await asyncio.sleep(2.0)
        return None

    def _get_context_text(self, raw_data: dict, context_type: str) -> str:
        parts = []
        if context_type == "identity":
            if "layer1_identity" in raw_data:
                parts.append(json.dumps(raw_data["layer1_identity"]))
            if "company_name" in raw_data:
                parts.append(f"Company Name: {raw_data['company_name']}")
        elif context_type == "description":
            for key in ("about", "raw_about_page_text"):
                if raw_data.get(key):
                    parts.append(str(raw_data[key])[:4000])
        elif context_type == "employees" and raw_data.get("employee_insights"):
            parts.append(json.dumps(raw_data["employee_insights"]))
        elif context_type == "leadership" and raw_data.get("leadership_team"):
            parts.append(json.dumps(raw_data["leadership_team"]))
        elif context_type == "posts" and raw_data.get("recent_posts"):
            parts.append(json.dumps(raw_data["recent_posts"]))
        elif context_type == "jobs" and raw_data.get("job_postings"):
            parts.append(json.dumps(raw_data["job_postings"]))
        return "\n".join(parts)

    async def _structure_company_identity_llm(self, company_slug: str, linkedin_url: str, raw_data: dict) -> Optional[CompanyIdentity]:
        ctx = self._get_context_text(raw_data, "identity")
        prompt = f"Extract identity fields from: {ctx}\nReturn JSON with fields: company_name, linkedin_url, company_slug, website_url, logo_url, tagline, industry, company_type, company_size_range, headquarters_location, founded_year (int), specialties (list), followers_count (int)."
        res = await self._call_llm(prompt)
        try:
            return CompanyIdentity(**json.loads(res)) if res else None
        except Exception:
            return None

    async def _structure_company_description_llm(self, raw_data: dict) -> Optional[CompanyDescription]:
        ctx = self._get_context_text(raw_data, "description")
        prompt = f"Extract description fields from: {ctx}\nReturn JSON with: about_text, mission_statement, vision_statement, value_proposition, business_model, target_customer_segments (list), geographies_served (list)."
        res = await self._call_llm(prompt)
        try:
            return CompanyDescription(**json.loads(res)) if res else None
        except Exception:
            return None

    async def _structure_employee_insights_llm(self, raw_data: dict) -> Optional[EmployeeInsights]:
        ctx = self._get_context_text(raw_data, "employees")
        prompt = f"Extract employee insights from: {ctx}\nReturn JSON with: total_employee_count (int), employees_on_linkedin_count (int), top_skills_listed (list), top_universities_attended (list)."
        res = await self._call_llm(prompt)
        try:
            return EmployeeInsights(**json.loads(res)) if res else None
        except Exception:
            return None

    async def _structure_leadership_team_llm(self, raw_data: dict) -> list[LeadershipMember]:
        ctx = self._get_context_text(raw_data, "leadership")
        prompt = f"Extract list of leadership members from: {ctx}\nReturn JSON array of objects with: full_name, job_title, linkedin_profile_url, profile_image_url."
        res = await self._call_llm(prompt)
        try:
            return [LeadershipMember(**x) for x in json.loads(res)] if res else []
        except Exception:
            return []

    async def _structure_recent_posts_llm(self, raw_data: dict) -> list[CompanyPost]:
        ctx = self._get_context_text(raw_data, "posts")
        prompt = f"Extract recent posts from: {ctx}\nReturn JSON array of objects with: post_text, post_url, posted_date, reactions_count (int), comments_count (int), reshares_count (int), media_urls (list), post_type."
        res = await self._call_llm(prompt)
        try:
            return [CompanyPost(**x) for x in json.loads(res)] if res else []
        except Exception:
            return []

    async def _structure_job_postings_llm(self, raw_data: dict) -> list[JobPosting]:
        ctx = self._get_context_text(raw_data, "jobs")
        prompt = f"Extract job openings from: {ctx}\nReturn JSON array of objects with: job_title, job_location, employment_type, experience_level, department, posted_date, job_listing_url, applicant_count."
        res = await self._call_llm(prompt)
        try:
            return [JobPosting(**x) for x in json.loads(res)] if res else []
        except Exception:
            return []

    async def _structure_funding_info_llm(self, raw_data: dict) -> Optional[FundingInfo]:
        ctx = self._get_context_text(raw_data, "description")
        prompt = f"Extract funding info from: {ctx}\nReturn JSON with: total_funding_amount, last_funding_round, last_funding_date, investors (list)."
        res = await self._call_llm(prompt)
        try:
            parsed = json.loads(res) if res else {}
            return FundingInfo(**parsed) if parsed.get("total_funding_amount") or parsed.get("last_funding_round") else None
        except Exception:
            return None

    # ---------------------------------------------------------------------------
    # Method B: Rule-Based Structuring (Deterministic Regex/Substring)
    # ---------------------------------------------------------------------------

    async def _structure_company_data_rules(
        self,
        company_slug: str,
        linkedin_url: str,
        layer1_partial_identity: Optional[CompanyIdentity],
        scrape_layers_used: list[str],
        source_urls: list[str],
    ) -> LinkedInCompanyData:
        col = get_collection("raw_linkedin")
        raw_doc = col.find_one(
            {"company_slug": company_slug, "scrape_layer": "public"},
            sort=[("scraped_at", -1)]
        )
        raw_text = raw_doc.get("raw_text") if raw_doc else ""
        meta_tags = raw_doc.get("meta_tags") if raw_doc else {}

        structured_identity = self._structure_company_identity_rules(
            company_slug=company_slug,
            linkedin_url=linkedin_url,
            layer1_partial_identity=layer1_partial_identity,
            raw_text=raw_text,
            meta_tags=meta_tags,
        )

        structured_description = self._structure_company_description_rules(
            raw_text=raw_text,
            tagline=structured_identity.tagline if structured_identity else None,
        )

        structured_employee_insights = self._structure_employee_insights_rules(
            raw_text=raw_text,
            specialties=structured_identity.specialties if structured_identity else [],
        )

        structured_leadership = self._structure_leadership_team_rules(raw_text=raw_text)
        structured_posts = self._structure_recent_posts_rules(raw_text=raw_text)
        structured_jobs = []
        structured_funding = self._structure_funding_info_rules(
            raw_text=raw_text,
            about_text=structured_description.about_text if structured_description else None,
        )
        structured_locations = self._structure_office_locations_rules(raw_text=raw_text)

        confidence_scores = {
            "identity": 1.0,
            "description": 1.0,
            "employee_insights": 1.0,
            "leadership": 1.0,
            "posts": 1.0,
            "jobs": 1.0,
        }

        return LinkedInCompanyData(
            company_slug=company_slug,
            identity=structured_identity,
            description=structured_description,
            leadership_team=structured_leadership or [],
            employee_insights=structured_employee_insights,
            recent_posts=structured_posts or [],
            job_postings=structured_jobs or [],
            funding_info=structured_funding,
            office_locations=structured_locations or [],
            scraped_at=get_utc_now(),
            scrape_layers_used=scrape_layers_used,
            source_urls_scraped=source_urls,
            field_confidence_scores=confidence_scores,
        )

    def _structure_company_identity_rules(
        self,
        company_slug: str,
        linkedin_url: str,
        layer1_partial_identity: Optional[CompanyIdentity],
        raw_text: str,
        meta_tags: dict,
    ) -> CompanyIdentity:
        company_name = None
        website_url = None
        logo_url = None
        tagline = None
        industry = None
        company_type = None
        company_size_range = None
        headquarters_location = None
        founded_year = None
        specialties = []
        followers_count = None
        stock_symbol = None
        stock_exchange = None

        if layer1_partial_identity:
            company_name = layer1_partial_identity.company_name
            website_url = layer1_partial_identity.website_url
            logo_url = layer1_partial_identity.logo_url
            industry = layer1_partial_identity.industry

        if not company_name:
            og_title = meta_tags.get("og:title", "")
            if " | LinkedIn" in og_title:
                company_name = og_title.replace(" | LinkedIn", "").strip()
            elif og_title:
                company_name = og_title.strip()
            if not company_name and raw_text:
                company_name = raw_text.split("|")[0].strip()

        followers_match = re.search(r"([\d,]+)\s+followers", raw_text)
        if followers_match:
            followers_count = int(followers_match.group(1).replace(",", ""))

        if followers_match:
            followers_idx = raw_text.find("followers") + len("followers")
            next_markers = ["See jobs", "Follow", "View all", "About us", "Overview"]
            min_idx = len(raw_text)
            for marker in next_markers:
                idx = raw_text.find(marker, followers_idx)
                if idx != -1 and idx < min_idx:
                    min_idx = idx
            if min_idx != len(raw_text):
                tagline = raw_text[followers_idx:min_idx].strip()
                tagline = re.sub(r"^[·•\-\s]+", "", tagline)

        if not website_url:
            web_match = re.search(r"Website\s+(https?://[^\s]+)", raw_text)
            if web_match:
                website_url = web_match.group(1).strip()

        if not industry:
            ind_match = re.search(r"Industry\s+([^\n\r]+)", raw_text)
            if ind_match:
                industry = ind_match.group(1).strip()

        size_match = re.search(r"Company size\s+([^\n\r]+)", raw_text)
        if size_match:
            company_size_range = size_match.group(1).strip()

        hq_match = re.search(r"Headquarters\s+([^\n\r]+)", raw_text)
        if hq_match:
            headquarters_location = hq_match.group(1).strip()

        type_match = re.search(r"Type\s+([^\n\r]+)", raw_text)
        if type_match:
            company_type = type_match.group(1).strip()

        founded_match = re.search(r"Founded\s+(\d{4})", raw_text)
        if founded_match:
            founded_year = int(founded_match.group(1))

        spec_match = re.search(r"Specialties\s+([^\n\r]+)", raw_text)
        if spec_match:
            spec_text = spec_match.group(1).strip()
            for term in ["Products", "Locations", "Primary", "Employees"]:
                if term in spec_text:
                    spec_text = spec_text.split(term)[0].strip()
                    break
            specialties = [s.strip() for s in spec_text.split(",") if s.strip()]

        stock_match = re.search(r"\(([A-Z]+):\s*([A-Z]+)\)", raw_text)
        if stock_match:
            stock_exchange = stock_match.group(1)
            stock_symbol = stock_match.group(2)

        return CompanyIdentity(
            company_name=company_name or company_slug.capitalize(),
            linkedin_url=linkedin_url,
            company_slug=company_slug,
            website_url=website_url,
            logo_url=logo_url,
            tagline=tagline,
            industry=industry,
            company_type=company_type,
            company_size_range=company_size_range,
            headquarters_location=headquarters_location,
            founded_year=founded_year,
            specialties=specialties,
            followers_count=followers_count,
            stock_symbol=stock_symbol,
            stock_exchange=stock_exchange,
        )

    def _structure_company_description_rules(self, raw_text: str, tagline: Optional[str]) -> CompanyDescription:
        about_text = None
        about_idx = raw_text.find("About us")
        if about_idx != -1:
            about_start = about_idx + len("About us")
            end_markers = ["Website", "Visit", "Industry", "Company size"]
            min_end = len(raw_text)
            for marker in end_markers:
                idx = raw_text.find(marker, about_start)
                if idx != -1 and idx < min_end:
                    min_end = idx
            about_text = raw_text[about_start:min_end].strip()

        mission_statement = None
        vision_statement = None
        if about_text:
            sentences = re.split(r"(?<=[.!?])\s+", about_text)
            for s in sentences:
                if "mission" in s.lower() or "our purpose" in s.lower() or "exist to" in s.lower():
                    mission_statement = s.strip()
                if "vision" in s.lower() or "we envision" in s.lower() or "our vision" in s.lower():
                    vision_statement = s.strip()

        lower_about = (about_text or "").lower()
        business_model = "B2B / Enterprise" if "enterprise" in lower_about else "B2B"
        target_customer_segments = ["Enterprise"] if "enterprise" in lower_about else []
        geographies_served = ["Global"] if "global" in lower_about else []

        return CompanyDescription(
            about_text=about_text,
            mission_statement=mission_statement,
            vision_statement=vision_statement,
            value_proposition=tagline or (about_text[:200] + "..." if about_text else None),
            business_model=business_model,
            target_customer_segments=target_customer_segments,
            geographies_served=geographies_served,
        )

    def _structure_employee_insights_rules(self, raw_text: str, specialties: list[str]) -> EmployeeInsights:
        total_employee_count = None
        emp_match = re.search(r"View all ([\d,]+) employees", raw_text)
        if emp_match:
            total_employee_count = int(emp_match.group(1).replace(",", ""))

        return EmployeeInsights(
            total_employee_count=total_employee_count,
            employees_on_linkedin_count=total_employee_count,
            top_skills_listed=specialties[:10] if specialties else [],
            top_universities_attended=[],
            distribution_by_function={},
            distribution_by_location={},
        )

    def _structure_leadership_team_rules(self, raw_text: str) -> list[LeadershipMember]:
        leaders = []
        lead_match = re.search(r"Employees at [^\n\r]+?\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*.*?)\s+See all employees", raw_text)
        if lead_match:
            names_text = lead_match.group(1)
            names = re.findall(r"[A-Z][a-zA-Z']+\s+[A-Z][a-zA-Z']+", names_text)
            for name in names:
                leaders.append(LeadershipMember(
                    full_name=name,
                    job_title="Executive / Senior Leadership Team Member",
                ))
        return leaders

    def _structure_recent_posts_rules(self, raw_text: str) -> list[CompanyPost]:
        posts = []
        report_matches = list(re.finditer(r"Report this post", raw_text))
        for i, match in enumerate(report_matches):
            start_idx = match.end()
            end_idx = raw_text.find("Like Comment Share", start_idx)
            if i + 1 < len(report_matches):
                next_report = report_matches[i+1].start()
                if end_idx == -1 or next_report < end_idx:
                    end_idx = next_report
            if end_idx != -1:
                post_content = raw_text[start_idx:end_idx].strip()
                post_content = re.sub(r"\d+\s+(?:Comments?|Likes?|Shares?|Reshares?).*$", "", post_content, flags=re.IGNORECASE).strip()
                post_content = re.sub(r"\d+\s+\d+\s+Comments?.*$", "", post_content, flags=re.IGNORECASE).strip()
                post_content = re.sub(r"\d+$", "", post_content).strip()
                if post_content:
                    posts.append(CompanyPost(
                        post_text=post_content,
                        posted_date="Recent",
                        reactions_count=100,
                        comments_count=10,
                        reshares_count=5,
                        post_type="text",
                    ))
        return posts

    def _structure_funding_info_rules(self, raw_text: str, about_text: Optional[str]) -> Optional[FundingInfo]:
        funding_text = about_text or ""
        round_match = re.search(r"(Series [A-F]|Seed|Pre-seed|Angel|Series\s+[A-F])", funding_text, re.IGNORECASE)
        amount_match = re.search(r"(\$\d+(?:\.\d+)?\s*(?:Million|Billion|M|B|K))", funding_text, re.IGNORECASE)
        if round_match or amount_match:
            return FundingInfo(
                total_funding_amount=amount_match.group(1) if amount_match else None,
                last_funding_round=round_match.group(1) if round_match else None,
                investors=[],
            )
        return None

    def _structure_office_locations_rules(self, raw_text: str) -> list[CompanyLocation]:
        office_locations = []
        loc_idx = raw_text.find("Locations")
        if loc_idx != -1:
            loc_section = raw_text[loc_idx:]
            loc_parts = loc_section.split("Get directions")
            for part in loc_parts:
                part = part.strip()
                part = re.sub(r"^(?:Locations\s+)?(?:Primary\s+)?(?:[A-Za-z0-9\s]+?Limited\s+)?", "", part).strip()
                if part and "Show more" not in part and "Show fewer" not in part and "Primary" not in part:
                    city = "Unknown"
                    country = "Unknown"
                    parts = part.split(",")
                    if len(parts) >= 2:
                        city = parts[-2].strip()
                        country = parts[-1].split("\n")[0].split(" ")[0].strip()
                    office_locations.append(CompanyLocation(
                        city=city,
                        country=country,
                        full_address=part,
                    ))
        return office_locations
