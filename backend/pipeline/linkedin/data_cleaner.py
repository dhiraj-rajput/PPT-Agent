"""
linkedin/data_cleaner.py
------------------------
Cleans and normalizes raw scraped LinkedIn data before it enters
the LLM structuring and BI extraction stages.

Why this matters:
  - LinkedIn pages contain noise: emojis, tracking params, boilerplate text,
    duplicate content, HTML artifacts, and inconsistent formatting.
  - Feeding dirty data to the LLM wastes tokens and degrades output quality.
  - Cleaning first = cheaper, faster, more accurate LLM calls.

What this module does:
  1. Strips HTML tags and decodes HTML entities
  2. Normalizes whitespace (collapses multiple spaces/newlines)
  3. Removes LinkedIn boilerplate phrases (sign-in prompts, cookie banners)
  4. Deduplicates posts and job listings
  5. Normalizes employee count strings → integers
  6. Validates and cleans URLs
  7. Strips emojis from structured text fields (keeps them in post text)
  8. Truncates overly long text to LLM-safe lengths
  9. Assigns an overall data quality score (0.0 - 1.0)
"""

import re
import unicodedata
from html import unescape
from urllib.parse import urlparse, urlunparse

from utils.helpers import is_valid_url, setup_logger

from pipeline.linkedin.models import (
    CompanyLocation,
    CompanyPost,
    EmployeeInsights,
    JobPosting,
    LinkedInCompanyData,
)

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# LinkedIn Boilerplate Phrases to Remove
# ---------------------------------------------------------------------------
# These phrases appear on every LinkedIn page and contain no useful data.

LINKEDIN_BOILERPLATE_PHRASES = [
    "Join to view full profile",
    "Sign in to view",
    "Sign up to see",
    "Join LinkedIn",
    "Already on LinkedIn?",
    "Agree & Join LinkedIn",
    "By clicking Continue to join or sign in",
    "LinkedIn © 2024",
    "LinkedIn © 2025",
    "LinkedIn © 2026",
    "User Agreement",
    "Privacy Policy",
    "Cookie Policy",
    "Copyright Policy",
    "Brand Policy",
    "Community Guidelines",
    "Cookie settings",
    "Manage cookies",
    "We use cookies",
    "By using this site you agree",
    "Your profile and activity data",
    "500+ connections",
    "View mutual connections",
    "Send InMail",
    "Message",
    "Follow",
    "Report this profile",
    "Report this company",
    "See all employees on LinkedIn",
    "Try Premium for free",
    "See who you know",
    "Add your email",
    "Show more",
    "Show less",
    "See all",
    "Load more",
    "You're now following",
    "Following",
    "People also viewed",
    "People you may know",
    "Trending on LinkedIn",
]

# Max character limits for different text types
# Chosen to stay well under the LLM context window while preserving key info
MAX_ABOUT_TEXT_LENGTH = 5_000
MAX_POST_TEXT_LENGTH = 2_000
MAX_JOB_DESCRIPTION_LENGTH = 1_000
MAX_RAW_TEXT_FOR_LLM = 8_000


class DataCleaner:
    """
    Cleans and normalizes a LinkedInCompanyData object in-place.

    Call clean() on a freshly structured object before passing it to the
    BI extractor or storing it as the final result.

    Usage:
        cleaner = DataCleaner()
        cleaned_data, quality_score = cleaner.clean(company_data)
    """

    def clean(
        self,
        company_data: LinkedInCompanyData,
    ) -> tuple[LinkedInCompanyData, float]:
        """
        Runs all cleaning operations on the company data object.

        Args:
            company_data: A LinkedInCompanyData object (may have dirty/noisy fields).

        Returns:
            A tuple of:
              - The cleaned LinkedInCompanyData object (modified in place).
              - A quality score float between 0.0 and 1.0.
        """
        logger.info(f"[DataCleaner] Cleaning data for: '{company_data.company_slug}'")

        # Clean each section independently
        if company_data.identity:
            company_data.identity = self._clean_identity(company_data.identity)

        if company_data.description:
            company_data.description = self._clean_description(company_data.description)

        company_data.recent_posts = self._clean_posts(company_data.recent_posts)
        company_data.job_postings = self._clean_job_postings(company_data.job_postings)
        company_data.leadership_team = self._clean_leadership(company_data.leadership_team)
        company_data.office_locations = self._clean_locations(company_data.office_locations)

        if company_data.employee_insights:
            company_data.employee_insights = self._clean_employee_insights(
                company_data.employee_insights
            )

        # Calculate and attach overall quality score
        quality_score = self._calculate_data_quality_score(company_data)
        company_data.data_quality_score = quality_score

        logger.info(
            f"[DataCleaner] Done | company='{company_data.company_slug}' "
            f"| quality_score={quality_score:.2f} "
            f"| posts={len(company_data.recent_posts)} "
            f"| jobs={len(company_data.job_postings)}"
        )

        return company_data, quality_score

    # ---------------------------------------------------------------------------
    # Section Cleaners
    # ---------------------------------------------------------------------------

    def _clean_identity(self, identity):
        """Cleans company identity fields."""
        if identity.company_name:
            identity.company_name = self._strip_boilerplate(
                self._normalize_whitespace(
                    self._remove_emojis(identity.company_name)
                )
            )

        if identity.tagline:
            identity.tagline = self._normalize_whitespace(
                self._remove_emojis(identity.tagline)
            )

        if identity.website_url:
            identity.website_url = self._clean_url(identity.website_url)

        if identity.headquarters_location:
            identity.headquarters_location = self._normalize_whitespace(
                identity.headquarters_location
            )

        if identity.industry:
            identity.industry = self._normalize_whitespace(identity.industry)

        # Clean the specialties list — remove duplicates and empty strings
        identity.specialties = list(dict.fromkeys(
            [s.strip() for s in identity.specialties if s.strip()]
        ))

        # Normalize followers count string → int if needed
        if isinstance(identity.followers_count, str):
            identity.followers_count = self._parse_count_string(identity.followers_count)

        return identity

    def _clean_description(self, description):
        """Cleans about text and statements."""
        if description.about_text:
            description.about_text = self._clean_long_text(
                description.about_text,
                max_length=MAX_ABOUT_TEXT_LENGTH,
            )

        if description.mission_statement:
            description.mission_statement = self._normalize_whitespace(
                description.mission_statement
            )

        if description.vision_statement:
            description.vision_statement = self._normalize_whitespace(
                description.vision_statement
            )

        if description.value_proposition:
            description.value_proposition = self._normalize_whitespace(
                description.value_proposition
            )

        # Clean customer segments and geographies lists
        description.target_customer_segments = list(dict.fromkeys(
            [s.strip() for s in description.target_customer_segments if s.strip()]
        ))
        description.geographies_served = list(dict.fromkeys(
            [g.strip() for g in description.geographies_served if g.strip()]
        ))

        return description

    def _clean_posts(self, posts: list[CompanyPost]) -> list[CompanyPost]:
        """
        Cleans post text, removes duplicates, and filters out low-quality posts.

        A post is considered low-quality if:
          - Its text is under 20 characters after cleaning (probably just an emoji or link)
          - Its text is entirely composed of boilerplate phrases

        Returns:
            Deduplicated, cleaned list of posts.
        """
        cleaned_posts = []
        seen_post_texts = set()

        for post in posts:
            if not post.post_text:
                continue

            # Clean the text
            cleaned_text = self._clean_long_text(
                post.post_text,
                max_length=MAX_POST_TEXT_LENGTH,
                preserve_emojis=True,   # Keep emojis in posts — they're intentional
            )

            # Skip posts that are too short after cleaning
            if len(cleaned_text.strip()) < 20:
                continue

            # Skip duplicate posts (normalize before comparing)
            normalized_key = re.sub(r"\s+", " ", cleaned_text.lower().strip())[:100]
            if normalized_key in seen_post_texts:
                continue
            seen_post_texts.add(normalized_key)

            post.post_text = cleaned_text

            # Clean post URL
            if post.post_url:
                post.post_url = self._clean_linkedin_url(post.post_url)

            # Normalize engagement counts
            if isinstance(post.reactions_count, str):
                post.reactions_count = self._parse_count_string(post.reactions_count)
            if isinstance(post.comments_count, str):
                post.comments_count = self._parse_count_string(post.comments_count)
            if isinstance(post.reshares_count, str):
                post.reshares_count = self._parse_count_string(post.reshares_count)

            # Clean media URLs
            post.media_urls = [
                url for url in post.media_urls
                if url and is_valid_url(url)
            ]

            cleaned_posts.append(post)

        return cleaned_posts

    def _clean_job_postings(self, jobs: list[JobPosting]) -> list[JobPosting]:
        """
        Cleans job titles/locations, removes duplicates, normalizes fields.

        Returns:
            Deduplicated, cleaned list of job postings.
        """
        cleaned_jobs = []
        seen_job_keys = set()

        for job in jobs:
            if not job.job_title:
                continue

            cleaned_title = self._normalize_whitespace(
                self._remove_emojis(job.job_title)
            )

            if not cleaned_title:
                continue

            # Dedup by title + location combination
            dedup_key = f"{cleaned_title.lower()}|{(job.job_location or '').lower()}"
            if dedup_key in seen_job_keys:
                continue
            seen_job_keys.add(dedup_key)

            job.job_title = cleaned_title

            if job.job_location:
                job.job_location = self._normalize_whitespace(job.job_location)

            if job.employment_type:
                job.employment_type = self._normalize_whitespace(job.employment_type)

            if job.experience_level:
                job.experience_level = self._normalize_whitespace(job.experience_level)

            # Clean skills list
            job.key_skills_required = list(dict.fromkeys(
                [s.strip() for s in job.key_skills_required if s.strip()]
            ))

            cleaned_jobs.append(job)

        return cleaned_jobs

    def _clean_leadership(self, leaders: list) -> list:
        """Removes duplicate leaders and cleans name/title fields."""
        cleaned = []
        seen_names = set()

        blacklist_names = {
            "user agreement", "privacy policy", "cookie policy", "linkedin member",
            "password show", "sign in", "join now", "cookie use", "brand policy",
            "copyright policy", "about", "help center", "safety center", "mobile",
            "developers", "language", "upgrade browser", "sign up", "log in",
            "linkedin", "member", "the phoenix", "mills ltd", "phoenix mills",
            "security center", "agreement", "policy", "cookies", "terms of use"
        }

        for leader in leaders:
            if not leader.full_name:
                continue

            clean_name = self._normalize_whitespace(self._remove_emojis(leader.full_name))
            clean_name_lower = clean_name.lower().strip()

            # Filter out blacklisted names or names that are too short/generic
            if clean_name_lower in blacklist_names or len(clean_name_lower) < 3:
                continue

            # Filter out names that look like system text or page links
            if any(term in clean_name_lower for term in ["policy", "agreement", "cookie", "sign in", "sign up", "log in"]):
                continue

            if clean_name_lower in seen_names:
                continue

            seen_names.add(clean_name_lower)
            leader.full_name = clean_name
            leader.job_title = self._normalize_whitespace(
                self._remove_emojis(leader.job_title or "")
            )
            if leader.linkedin_profile_url:
                leader.linkedin_profile_url = self._clean_linkedin_url(
                    leader.linkedin_profile_url
                )
            cleaned.append(leader)

        return cleaned

    def _clean_locations(self, locations: list[CompanyLocation]) -> list[CompanyLocation]:
        """Removes duplicate locations and normalizes address fields."""
        cleaned = []
        seen_location_keys = set()

        for location in locations:
            city = (location.city or "").strip()
            country = (location.country or "").strip()
            location_key = f"{city.lower()}|{country.lower()}"

            if location_key in seen_location_keys or (not city and not country):
                continue

            seen_location_keys.add(location_key)

            if location.full_address:
                location.full_address = self._normalize_whitespace(location.full_address)

            location.city = city
            location.country = country

            cleaned.append(location)

        return cleaned

    def _clean_employee_insights(self, insights: EmployeeInsights) -> EmployeeInsights:
        """Normalizes and validates employee insight fields."""
        # Normalize count strings to integers
        if isinstance(insights.total_employee_count, str):
            insights.total_employee_count = self._parse_count_string(
                insights.total_employee_count
            )

        if isinstance(insights.employees_on_linkedin_count, str):
            insights.employees_on_linkedin_count = self._parse_count_string(
                insights.employees_on_linkedin_count
            )

        # Validate growth percentages (filter unrealistic values)
        if insights.employee_growth_percentage_6_months is not None:
            if abs(insights.employee_growth_percentage_6_months) > 200:
                # 200% growth in 6 months is extremely rare — likely a parsing error
                insights.employee_growth_percentage_6_months = None

        if insights.employee_growth_percentage_1_year is not None:
            if abs(insights.employee_growth_percentage_1_year) > 500:
                insights.employee_growth_percentage_1_year = None

        # Clean skills list
        insights.top_skills_listed = list(dict.fromkeys(
            [s.strip() for s in insights.top_skills_listed if s.strip()]
        ))[:20]  # Limit to 20 skills max

        # Clean universities list
        insights.top_universities_attended = list(dict.fromkeys(
            [u.strip() for u in insights.top_universities_attended if u.strip()]
        ))[:15]

        # Clean top hiring roles
        insights.top_hiring_roles = list(dict.fromkeys(
            [r.strip() for r in insights.top_hiring_roles if r.strip()]
        ))[:10]

        return insights

    # ---------------------------------------------------------------------------
    # Raw Text Cleaning for LLM Input
    # ---------------------------------------------------------------------------

    @staticmethod
    def clean_raw_text_for_llm(raw_text: str) -> str:
        """
        Cleans raw page text specifically to optimize it as LLM input.

        This is used before sending text to the LLM structurer or BI extractor
        to maximize the signal-to-noise ratio within the token budget.

        Args:
            raw_text: Raw text scraped from a LinkedIn page.

        Returns:
            Cleaned text ready for an LLM prompt (max MAX_RAW_TEXT_FOR_LLM chars).
        """
        if not raw_text:
            return ""

        # 1. Strip HTML tags (in case raw HTML was mixed in)
        text = re.sub(r"<[^>]+>", " ", raw_text)

        # 2. Decode HTML entities (&amp; → &, &nbsp; → space, etc.)
        text = unescape(text)

        # 3. Remove LinkedIn boilerplate lines
        lines = text.split("\n")
        clean_lines = []
        for line in lines:
            stripped = line.strip()
            # Skip short lines and boilerplate
            if len(stripped) < 3:
                continue
            if any(phrase.lower() in stripped.lower() for phrase in LINKEDIN_BOILERPLATE_PHRASES):
                continue
            clean_lines.append(stripped)

        text = "\n".join(clean_lines)

        # 4. Normalize whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)   # Max 2 consecutive newlines
        text = re.sub(r"[ \t]{2,}", " ", text)    # Collapse multiple spaces/tabs
        text = text.strip()

        # 5. Truncate to LLM-safe length
        if len(text) > MAX_RAW_TEXT_FOR_LLM:
            text = text[:MAX_RAW_TEXT_FOR_LLM] + "\n\n[...truncated for LLM context limit]"

        return text

    # ---------------------------------------------------------------------------
    # Core Text Processing Utilities
    # ---------------------------------------------------------------------------

    def _clean_long_text(
        self,
        text: str,
        max_length: int,
        preserve_emojis: bool = False,
    ) -> str:
        """
        Full cleaning pipeline for a block of text:
        strip HTML → decode entities → remove boilerplate → normalize whitespace
        → optionally remove emojis → truncate.
        """
        if not text:
            return ""

        # Strip HTML
        text = re.sub(r"<[^>]+>", " ", text)

        # Decode HTML entities
        text = unescape(text)

        # Remove boilerplate phrases
        text = self._strip_boilerplate(text)

        # Remove emojis if not preserving
        if not preserve_emojis:
            text = self._remove_emojis(text)

        # Normalize whitespace
        text = self._normalize_whitespace(text)

        # Truncate
        if len(text) > max_length:
            text = text[:max_length].rsplit(" ", 1)[0] + "..."

        return text.strip()

    def _strip_boilerplate(self, text: str) -> str:
        """Removes LinkedIn boilerplate phrases from a string."""
        for phrase in LINKEDIN_BOILERPLATE_PHRASES:
            text = text.replace(phrase, "")
        return text

    def _normalize_whitespace(self, text: str) -> str:
        """Collapses multiple whitespace characters into a single space."""
        if not text:
            return ""
        text = re.sub(r"[ \t]+", " ", text)        # Collapse spaces/tabs
        text = re.sub(r"\n{2,}", "\n", text)        # Collapse newlines
        return text.strip()

    def _remove_emojis(self, text: str) -> str:
        """
        Removes emoji characters from text using Unicode category detection.
        Keeps standard punctuation, letters, digits, and common symbols.
        """
        if not text:
            return ""

        cleaned_chars = []
        for char in text:
            unicode_category = unicodedata.category(char)
            # Keep: letters (L), numbers (N), punctuation (P), spaces (Z), symbols (S)
            # Remove: 'So' (Other Symbol = emojis), 'Cf' (Format chars), etc.
            if unicode_category.startswith(("L", "N", "P", "Z")) or char in ("-", "_", "+", "=", "/", "\\", "@", "#", "$", "%", "&"):
                cleaned_chars.append(char)
            else:
                cleaned_chars.append(" ")  # Replace emoji with space

        return re.sub(r" +", " ", "".join(cleaned_chars)).strip()

    def _clean_url(self, url: str) -> str | None:
        """
        Cleans a URL by removing tracking parameters and normalizing format.

        Args:
            url: Any URL string.

        Returns:
            A clean URL string, or None if the URL is invalid.
        """
        if not url or not isinstance(url, str):
            return None

        url = url.strip()

        if not is_valid_url(url):
            # Try adding https:// prefix
            if not url.startswith("http"):
                url = f"https://{url}"
            if not is_valid_url(url):
                return None

        # Remove common tracking parameters
        parsed = urlparse(url)
        # Reconstruct without query string and fragment (removes tracking params)
        clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        return clean.rstrip("/")

    def _clean_linkedin_url(self, url: str) -> str | None:
        """
        Cleans a LinkedIn-specific URL by removing tracking parameters (?trk=...).
        """
        if not url:
            return None

        url = url.strip()

        # Remove query string (LinkedIn tracking params like ?trk=..., ?profileId=...)
        if "?" in url:
            url = url.split("?")[0]

        # Remove fragment
        if "#" in url:
            url = url.split("#")[0]

        return url.rstrip("/")

    def _parse_count_string(self, count_str) -> int | None:
        """
        Parses a count string into an integer.

        Handles formats like:
          "47,321" → 47321
          "1.2M" → 1200000
          "500K" → 500000
          "Over 200" → 200
          "500+" → 500
        """
        if count_str is None:
            return None

        if isinstance(count_str, (int, float)):
            return int(count_str)

        text = str(count_str).strip().lower()

        # Remove common prefixes
        text = re.sub(r"^(over|approximately|about|around|~)\s*", "", text)

        # Remove commas and + signs
        text = text.replace(",", "").replace("+", "").strip()

        try:
            if "m" in text:
                # "1.2m" → 1200000
                return int(float(text.replace("m", "")) * 1_000_000)
            if "k" in text:
                # "500k" → 500000
                return int(float(text.replace("k", "")) * 1_000)
            return int(float(text))
        except (ValueError, TypeError):
            return None

    # ---------------------------------------------------------------------------
    # Data Quality Scoring
    # ---------------------------------------------------------------------------

    def _calculate_data_quality_score(self, company_data: LinkedInCompanyData) -> float:
        """
        Calculates an overall data quality score for the company data.

        Score is based on how many key fields are populated with meaningful data.
        Used to flag companies that need re-scraping or manual review.

        Scoring breakdown:
          - Identity fields (company name, industry, size, HQ):  30 points
          - Description (about text):                            20 points
          - Leadership team:                                     10 points
          - Employee insights:                                   10 points
          - Recent posts:                                        10 points
          - Job postings:                                        10 points
          - BI profile:                                          10 points

        Returns:
            A float between 0.0 (no data) and 1.0 (complete data).
        """
        total_points = 0
        earned_points = 0

        # --- Identity (30 points) ---
        total_points += 30
        if company_data.identity:
            if company_data.identity.company_name:
                earned_points += 8
            if company_data.identity.industry:
                earned_points += 5
            if company_data.identity.company_size_range:
                earned_points += 5
            if company_data.identity.headquarters_location:
                earned_points += 5
            if company_data.identity.website_url:
                earned_points += 4
            if company_data.identity.founded_year:
                earned_points += 3

        # --- Description (20 points) ---
        total_points += 20
        if company_data.description and company_data.description.about_text:
            about_length = len(company_data.description.about_text)
            if about_length > 500:
                earned_points += 20
            elif about_length > 200:
                earned_points += 12
            elif about_length > 50:
                earned_points += 6

        # --- Leadership (10 points) ---
        total_points += 10
        leaders_count = len(company_data.leadership_team)
        earned_points += min(10, leaders_count * 3)

        # --- Employee Insights (10 points) ---
        total_points += 10
        if company_data.employee_insights:
            if company_data.employee_insights.total_employee_count:
                earned_points += 5
            if company_data.employee_insights.top_skills_listed:
                earned_points += 3
            if company_data.employee_insights.employee_growth_percentage_1_year is not None:
                earned_points += 2

        # --- Posts (10 points) ---
        total_points += 10
        posts_count = len(company_data.recent_posts)
        earned_points += min(10, posts_count * 2)

        # --- Jobs (10 points) ---
        total_points += 10
        jobs_count = len(company_data.job_postings)
        earned_points += min(10, jobs_count * 1)

        # --- BI Profile (10 points) ---
        total_points += 10
        if company_data.bi_profile:
            if company_data.bi_profile.executive_summary:
                earned_points += 4
            if company_data.bi_profile.growth_signals:
                earned_points += 3
            if company_data.bi_profile.business_challenges:
                earned_points += 3

        quality_score = round(earned_points / total_points, 2)
        return quality_score


def clean_raw_text_for_llm(raw_text: str) -> str:
    """
    Module-level convenience function for cleaning raw text before LLM calls.
    Delegates to DataCleaner.clean_raw_text_for_llm().
    """
    return DataCleaner.clean_raw_text_for_llm(raw_text)
