"""
tests/unit/test_models.py
--------------------------
Unit tests for linkedin/models.py.

Verifies that Pydantic models:
  - Accept valid data correctly
  - Apply correct field defaults
  - Reject invalid data with ValidationError
  - Serialize/deserialize correctly from dict → model → dict round-trip
"""

import pytest
from datetime import datetime, timezone

from pydantic import ValidationError

from linkedin.models import (
    BIProfile,
    BusinessChallenge,
    CompanyDescription,
    CompanyIdentity,
    CompanyLocation,
    CompanyPost,
    CompetitorMention,
    EmployeeInsights,
    FundingInfo,
    GrowthSignal,
    JobPosting,
    LeadershipMember,
    LinkedInCompanyData,
    ProductOrService,
    RawLinkedInScrapedData,
    StrategicInitiative,
    TechStackProfile,
)


# ---------------------------------------------------------------------------
# Helper: build a minimal valid LinkedInCompanyData
# ---------------------------------------------------------------------------

def make_company_data(**overrides) -> LinkedInCompanyData:
    defaults = {
        "company_slug": "test-corp",
        "scraped_at": datetime.now(tz=timezone.utc),
    }
    defaults.update(overrides)
    return LinkedInCompanyData(**defaults)


# ---------------------------------------------------------------------------
# CompanyIdentity
# ---------------------------------------------------------------------------

class TestCompanyIdentity:
    def test_required_fields_must_be_provided(self):
        with pytest.raises(ValidationError):
            CompanyIdentity(**{})  # Missing company_name, linkedin_url, company_slug

    def test_minimal_valid_identity(self):
        identity = CompanyIdentity(
            company_name="Infosys",
            linkedin_url="https://www.linkedin.com/company/infosys",
            company_slug="infosys",
        )
        assert identity.company_name == "Infosys"
        assert identity.company_slug == "infosys"
        assert identity.website_url is None       # Optional defaults to None
        assert identity.specialties == []         # List defaults to []
        assert identity.followers_count is None

    def test_full_identity(self):
        identity = CompanyIdentity(
            company_name="Infosys",
            linkedin_url="https://www.linkedin.com/company/infosys",
            company_slug="infosys",
            website_url="https://www.infosys.com",
            industry="IT Services and IT Consulting",
            company_type="Public Company",
            company_size_range="10,001+ employees",
            headquarters_location="Bengaluru, Karnataka, India",
            founded_year=1981,
            specialties=["AI", "Cloud", "Digital Transformation"],
            followers_count=6000000,
            stock_symbol="INFY",
            stock_exchange="NYSE",
        )
        assert identity.founded_year == 1981
        assert "AI" in identity.specialties
        assert identity.stock_symbol == "INFY"


# ---------------------------------------------------------------------------
# CompanyDescription
# ---------------------------------------------------------------------------

class TestCompanyDescription:
    def test_all_optional_fields(self):
        desc = CompanyDescription()
        assert desc.about_text is None
        assert desc.mission_statement is None
        assert desc.target_customer_segments == []
        assert desc.geographies_served == []

    def test_accepts_full_description(self):
        desc = CompanyDescription(
            about_text="Infosys is a global technology company.",
            mission_statement="To help enterprises navigate their digital transformation.",
            target_customer_segments=["Enterprise", "SMB"],
            geographies_served=["India", "USA", "Europe"],
        )
        assert desc.about_text is not None
        assert "Enterprise" in desc.target_customer_segments


# ---------------------------------------------------------------------------
# CompanyPost
# ---------------------------------------------------------------------------

class TestCompanyPost:
    def test_all_optional_fields_default(self):
        post = CompanyPost()
        assert post.post_text is None
        assert post.reactions_count is None
        assert post.media_urls == []

    def test_accepts_full_post(self):
        post = CompanyPost(
            post_text="We are excited to launch our AI platform.",
            reactions_count=1500,
            comments_count=45,
            reshares_count=230,
            post_type="article",
            post_topic="Product Launch",
            engagement_rate=0.025,
        )
        assert post.post_text is not None
        assert post.engagement_rate == 0.025


# ---------------------------------------------------------------------------
# JobPosting
# ---------------------------------------------------------------------------

class TestJobPosting:
    def test_job_title_required(self):
        with pytest.raises(ValidationError):
            JobPosting(**{})  # job_title is required

    def test_minimal_valid_job(self):
        job = JobPosting(job_title="Senior Software Engineer")
        assert job.job_title == "Senior Software Engineer"
        assert job.job_location is None
        assert job.key_skills_required == []

    def test_full_job_posting(self):
        job = JobPosting(
            job_title="Data Scientist",
            job_location="Hyderabad, India",
            employment_type="Full-time",
            experience_level="Mid-Senior level",
            department="Data Science",
            key_skills_required=["Python", "TensorFlow", "SQL"],
        )
        assert "Python" in job.key_skills_required
        assert job.experience_level == "Mid-Senior level"


# ---------------------------------------------------------------------------
# LeadershipMember
# ---------------------------------------------------------------------------

class TestLeadershipMember:
    def test_required_fields(self):
        with pytest.raises(ValidationError):
            LeadershipMember(**{})  # full_name and job_title required

    def test_minimal_leader(self):
        leader = LeadershipMember(full_name="Salil Parekh", job_title="CEO")
        assert leader.full_name == "Salil Parekh"
        assert leader.tenure_years is None

    def test_optional_fields(self):
        leader = LeadershipMember(
            full_name="Salil Parekh",
            job_title="CEO",
            linkedin_profile_url="https://www.linkedin.com/in/salilparekh",
            tenure_years=5.5,
            background_summary="Former McKinsey partner.",
        )
        assert leader.tenure_years == 5.5


# ---------------------------------------------------------------------------
# EmployeeInsights
# ---------------------------------------------------------------------------

class TestEmployeeInsights:
    def test_all_optional_defaults(self):
        insights = EmployeeInsights()
        assert insights.total_employee_count is None
        assert insights.top_skills_listed == []
        assert insights.distribution_by_function == {}

    def test_accepts_full_insights(self):
        insights = EmployeeInsights(
            total_employee_count=343000,
            employees_on_linkedin_count=280000,
            employee_growth_percentage_6_months=2.5,
            employee_growth_percentage_1_year=5.0,
            top_skills_listed=["Python", "Java", "Cloud"],
            hiring_velocity="Moderate",
        )
        assert insights.total_employee_count == 343000
        assert insights.hiring_velocity == "Moderate"


# ---------------------------------------------------------------------------
# BIProfile
# ---------------------------------------------------------------------------

class TestBIProfile:
    def test_all_list_fields_default_to_empty(self):
        bi = BIProfile()
        assert bi.key_differentiators == []
        assert bi.competitive_advantages == []
        assert bi.identified_competitors == []
        assert bi.strategic_initiatives == []
        assert bi.growth_signals == []
        assert bi.business_challenges == []
        assert bi.products_and_services == []
        assert bi.sales_talking_points == []

    def test_all_optional_fields_default_to_none(self):
        bi = BIProfile()
        assert bi.executive_summary is None
        assert bi.company_maturity_stage is None
        assert bi.ai_adoption_level is None
        assert bi.tech_stack is None

    def test_accepts_nested_models(self):
        bi = BIProfile(
            key_differentiators=["Global Scale", "AI-first"],
            identified_competitors=[
                CompetitorMention(
                    competitor_name="TCS",
                    relationship_type="Direct Competitor",
                )
            ],
            business_challenges=[
                BusinessChallenge(
                    challenge_area="AI Adoption",
                    description="Transitioning legacy clients to AI-enabled services.",
                )
            ],
            strategic_initiatives=[
                StrategicInitiative(
                    initiative_name="AI Everywhere",
                    description="Embedding AI in all service lines.",
                )
            ],
        )
        assert bi.identified_competitors[0].competitor_name == "TCS"
        assert bi.business_challenges[0].challenge_area == "AI Adoption"
        assert bi.strategic_initiatives[0].initiative_name == "AI Everywhere"


# ---------------------------------------------------------------------------
# LinkedInCompanyData
# ---------------------------------------------------------------------------

class TestLinkedInCompanyData:
    def test_requires_company_slug_and_scraped_at(self):
        with pytest.raises(ValidationError):
            LinkedInCompanyData(**{})  # Both required fields missing

    def test_minimal_valid_company_data(self):
        data = make_company_data()
        assert data.company_slug == "test-corp"
        assert data.identity is None
        assert data.recent_posts == []
        assert data.job_postings == []
        assert data.bi_profile is None
        assert data.data_quality_score is None

    def test_full_company_data_round_trip(self):
        """Verify that model_dump() → reparse produces identical data."""
        identity = CompanyIdentity(
            company_name="Infosys",
            linkedin_url="https://www.linkedin.com/company/infosys",
            company_slug="infosys",
            industry="IT Services",
            founded_year=1981,
        )
        data = make_company_data(
            company_slug="infosys",
            identity=identity,
            job_postings=[JobPosting(job_title="Engineer")],
            scrape_layers_used=["public", "browser"],
            data_quality_score=0.75,
        )
        dumped = data.model_dump()
        reparsed = LinkedInCompanyData(**dumped)
        assert reparsed.company_slug == "infosys"
        assert reparsed.identity is not None
        assert reparsed.identity.company_name == "Infosys"
        assert len(reparsed.job_postings) == 1
        assert reparsed.data_quality_score == 0.75

    def test_bi_profile_can_be_set(self):
        data = make_company_data()
        data.bi_profile = BIProfile(
            executive_summary="A global IT leader.",
            company_maturity_stage="Mature Enterprise",
        )
        assert data.bi_profile.executive_summary == "A global IT leader."


# ---------------------------------------------------------------------------
# RawLinkedInScrapedData
# ---------------------------------------------------------------------------

class TestRawLinkedInScrapedData:
    def test_minimal_raw_data(self):
        raw = RawLinkedInScrapedData(
            company_slug="infosys",
            scrape_layer="public",
            page_url="https://www.linkedin.com/company/infosys",
            scraped_at=datetime.now(tz=timezone.utc),
        )
        assert raw.company_slug == "infosys"
        assert raw.scrape_success is True  # Default True
        assert raw.raw_html is None
        assert raw.error_message is None

    def test_failed_raw_data(self):
        raw = RawLinkedInScrapedData(
            company_slug="test-co",
            scrape_layer="browser",
            page_url="https://www.linkedin.com/company/test-co/about",
            scraped_at=datetime.now(tz=timezone.utc),
            scrape_success=False,
            error_message="Timeout after 30s",
        )
        assert raw.scrape_success is False
        assert raw.error_message == "Timeout after 30s"


# ---------------------------------------------------------------------------
# GrowthSignal
# ---------------------------------------------------------------------------

class TestGrowthSignal:
    def test_required_fields(self):
        with pytest.raises(ValidationError):
            GrowthSignal(**{})  # signal_type and description required

    def test_minimal_signal(self):
        signal = GrowthSignal(
            signal_type="Hiring Surge",
            description="300+ new jobs posted in Q1 2026.",
        )
        assert signal.signal_type == "Hiring Surge"
        assert signal.significance is None


# ---------------------------------------------------------------------------
# FundingInfo
# ---------------------------------------------------------------------------

class TestFundingInfo:
    def test_all_optional(self):
        funding = FundingInfo()
        assert funding.total_funding_amount is None
        assert funding.investors == []
        assert funding.is_profitable is None

    def test_full_funding(self):
        funding = FundingInfo(
            total_funding_amount="$500M",
            last_funding_round="Series D",
            investors=["Sequoia", "Tiger Global"],
            valuation="$2.5B",
            is_profitable=True,
        )
        assert "Sequoia" in funding.investors
        assert funding.is_profitable is True
