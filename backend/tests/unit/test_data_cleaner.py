"""
tests/unit/test_data_cleaner.py
--------------------------------
Unit tests for linkedin/data_cleaner.py.

Tests every cleaning function in isolation without hitting any external services.
All inputs are hand-crafted strings that simulate real LinkedIn page noise.
"""

import pytest
from datetime import datetime, timezone

from pipeline.linkedin.data_cleaner import DataCleaner, clean_raw_text_for_llm
from pipeline.linkedin.models import (
    CompanyIdentity,
    CompanyLocation,
    CompanyPost,
    EmployeeInsights,
    JobPosting,
    LeadershipMember,
    LinkedInCompanyData,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cleaner() -> DataCleaner:
    """Shared DataCleaner instance for all tests."""
    return DataCleaner()


@pytest.fixture
def minimal_company_data() -> LinkedInCompanyData:
    """A minimal LinkedInCompanyData object with an identity only."""
    identity = CompanyIdentity(
        company_name="Acme Corp",
        linkedin_url="https://www.linkedin.com/company/acme-corp",
        company_slug="acme-corp",
        industry="Information Technology",
        company_size_range="1,001-5,000 employees",
        headquarters_location="San Francisco, CA",
        website_url="https://acme.com",
        founded_year=2010,
    )
    return LinkedInCompanyData(
        company_slug="acme-corp",
        identity=identity,
        scraped_at=datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# _normalize_whitespace
# ---------------------------------------------------------------------------

class TestNormalizeWhitespace:
    def test_collapses_multiple_spaces(self, cleaner):
        result = cleaner._normalize_whitespace("hello    world")
        assert result == "hello world"

    def test_collapses_tabs_and_spaces(self, cleaner):
        result = cleaner._normalize_whitespace("hello\t\t world")
        assert result == "hello world"

    def test_collapses_multiple_newlines(self, cleaner):
        result = cleaner._normalize_whitespace("line1\n\n\nline2")
        assert result == "line1\nline2"

    def test_strips_leading_trailing(self, cleaner):
        result = cleaner._normalize_whitespace("  hello  ")
        assert result == "hello"

    def test_empty_string_returns_empty(self, cleaner):
        assert cleaner._normalize_whitespace("") == ""

    def test_none_like_empty_returns_empty(self, cleaner):
        assert cleaner._normalize_whitespace("   ") == ""


# ---------------------------------------------------------------------------
# _remove_emojis
# ---------------------------------------------------------------------------

class TestRemoveEmojis:
    def test_removes_standard_emoji(self, cleaner):
        result = cleaner._remove_emojis("Hello 🚀 World")
        assert "🚀" not in result
        assert "Hello" in result
        assert "World" in result

    def test_keeps_latin_text_intact(self, cleaner):
        result = cleaner._remove_emojis("Infosys Ltd. - IT Services")
        assert result == "Infosys Ltd. - IT Services"

    def test_keeps_special_chars(self, cleaner):
        result = cleaner._remove_emojis("C++ & Python / Java @scale #AI")
        assert "C" in result
        assert "@" in result
        assert "#" in result

    def test_empty_string_returns_empty(self, cleaner):
        assert cleaner._remove_emojis("") == ""

    def test_multiple_emojis_removed(self, cleaner):
        text = "We are hiring! 🎉🌍💼"
        result = cleaner._remove_emojis(text)
        for emoji in ("🎉", "🌍", "💼"):
            assert emoji not in result


# ---------------------------------------------------------------------------
# _parse_count_string
# ---------------------------------------------------------------------------

class TestParseCountString:
    def test_integer_passthrough(self, cleaner):
        assert cleaner._parse_count_string(12345) == 12345

    def test_float_truncated(self, cleaner):
        assert cleaner._parse_count_string(1.9) == 1

    def test_comma_separated_number(self, cleaner):
        assert cleaner._parse_count_string("47,321") == 47321

    def test_k_suffix(self, cleaner):
        assert cleaner._parse_count_string("500K") == 500000

    def test_m_suffix(self, cleaner):
        assert cleaner._parse_count_string("1.2M") == 1200000

    def test_over_prefix(self, cleaner):
        assert cleaner._parse_count_string("Over 200") == 200

    def test_approximately_prefix(self, cleaner):
        assert cleaner._parse_count_string("approximately 1000") == 1000

    def test_plus_sign(self, cleaner):
        assert cleaner._parse_count_string("500+") == 500

    def test_none_returns_none(self, cleaner):
        assert cleaner._parse_count_string(None) is None

    def test_invalid_string_returns_none(self, cleaner):
        assert cleaner._parse_count_string("not a number") is None

    def test_empty_string_returns_none(self, cleaner):
        assert cleaner._parse_count_string("") is None


# ---------------------------------------------------------------------------
# _strip_boilerplate
# ---------------------------------------------------------------------------

class TestStripBoilerplate:
    def test_removes_join_to_view(self, cleaner):
        text = "About us: Join to view full profile - we are a tech company."
        result = cleaner._strip_boilerplate(text)
        assert "Join to view full profile" not in result

    def test_removes_multiple_phrases(self, cleaner):
        text = "Sign in to view | LinkedIn © 2026 | Cookie Policy"
        result = cleaner._strip_boilerplate(text)
        assert "Sign in to view" not in result
        assert "LinkedIn © 2026" not in result
        assert "Cookie Policy" not in result

    def test_preserves_non_boilerplate(self, cleaner):
        text = "Infosys is a global leader in next-generation digital services."
        result = cleaner._strip_boilerplate(text)
        assert "Infosys is a global leader" in result


# ---------------------------------------------------------------------------
# _clean_url
# ---------------------------------------------------------------------------

class TestCleanUrl:
    def test_removes_tracking_params(self, cleaner):
        url = "https://infosys.com/page?utm_source=linkedin&utm_medium=social"
        result = cleaner._clean_url(url)
        assert "utm_source" not in result
        assert "https://infosys.com/page" == result

    def test_removes_trailing_slash(self, cleaner):
        result = cleaner._clean_url("https://infosys.com/")
        assert not result.endswith("/")

    def test_adds_https_prefix(self, cleaner):
        result = cleaner._clean_url("infosys.com")
        assert result.startswith("https://")

    def test_invalid_url_returns_none(self, cleaner):
        result = cleaner._clean_url("/")
        assert result is None

    def test_none_returns_none(self, cleaner):
        assert cleaner._clean_url(None) is None

    def test_empty_returns_none(self, cleaner):
        assert cleaner._clean_url("") is None


# ---------------------------------------------------------------------------
# _clean_linkedin_url
# ---------------------------------------------------------------------------

class TestCleanLinkedInUrl:
    def test_removes_trk_param(self, cleaner):
        url = "https://www.linkedin.com/company/infosys?trk=top_nav"
        result = cleaner._clean_linkedin_url(url)
        assert "trk" not in result
        assert result == "https://www.linkedin.com/company/infosys"

    def test_removes_fragment(self, cleaner):
        url = "https://www.linkedin.com/in/ceo#experience"
        result = cleaner._clean_linkedin_url(url)
        assert "#experience" not in result

    def test_none_returns_none(self, cleaner):
        assert cleaner._clean_linkedin_url(None) is None


# ---------------------------------------------------------------------------
# _clean_posts
# ---------------------------------------------------------------------------

class TestCleanPosts:
    def test_removes_empty_text_posts(self, cleaner):
        posts = [
            CompanyPost(post_text=None),
            CompanyPost(post_text=""),
            CompanyPost(post_text="   "),
        ]
        result = cleaner._clean_posts(posts)
        assert len(result) == 0

    def test_removes_short_posts(self, cleaner):
        posts = [CompanyPost(post_text="Hi!")]  # Under 20 chars
        result = cleaner._clean_posts(posts)
        assert len(result) == 0

    def test_deduplicates_identical_posts(self, cleaner):
        text = "We are excited to announce our new partnership with Acme Corporation."
        posts = [CompanyPost(post_text=text), CompanyPost(post_text=text)]
        result = cleaner._clean_posts(posts)
        assert len(result) == 1

    def test_keeps_unique_posts(self, cleaner):
        posts = [
            CompanyPost(post_text="We just launched our new AI platform for enterprise customers!"),
            CompanyPost(post_text="Congratulations to our team for winning the innovation award 2026!"),
        ]
        result = cleaner._clean_posts(posts)
        assert len(result) == 2

    def test_normalizes_reaction_count_string(self, cleaner):
        post = CompanyPost(
            post_text="We are excited to share our latest product update with the community!",
            reactions_count=1200,
        )
        result = cleaner._clean_posts([post])
        assert result[0].reactions_count == 1200


# ---------------------------------------------------------------------------
# _clean_job_postings
# ---------------------------------------------------------------------------

class TestCleanJobPostings:
    def test_removes_empty_title_jobs(self, cleaner):
        jobs = [JobPosting(job_title="")]
        result = cleaner._clean_job_postings(jobs)
        assert len(result) == 0

    def test_deduplicates_same_title_location(self, cleaner):
        jobs = [
            JobPosting(job_title="Software Engineer", job_location="Bangalore"),
            JobPosting(job_title="Software Engineer", job_location="Bangalore"),
        ]
        result = cleaner._clean_job_postings(jobs)
        assert len(result) == 1

    def test_keeps_different_locations(self, cleaner):
        jobs = [
            JobPosting(job_title="Software Engineer", job_location="Bangalore"),
            JobPosting(job_title="Software Engineer", job_location="Mumbai"),
        ]
        result = cleaner._clean_job_postings(jobs)
        assert len(result) == 2

    def test_strips_emoji_from_title(self, cleaner):
        job = JobPosting(job_title="🚀 Senior Data Engineer")
        result = cleaner._clean_job_postings([job])
        assert len(result) == 1
        assert "🚀" not in result[0].job_title


# ---------------------------------------------------------------------------
# _clean_leadership
# ---------------------------------------------------------------------------

class TestCleanLeadership:
    def test_removes_empty_name_leaders(self, cleaner):
        leaders = [
            LeadershipMember(full_name="", job_title="CEO"),
        ]
        result = cleaner._clean_leadership(leaders)
        assert len(result) == 0

    def test_deduplicates_by_name(self, cleaner):
        leaders = [
            LeadershipMember(full_name="John Smith", job_title="CEO"),
            LeadershipMember(full_name="John Smith", job_title="Chief Executive Officer"),
        ]
        result = cleaner._clean_leadership(leaders)
        assert len(result) == 1

    def test_case_insensitive_dedup(self, cleaner):
        leaders = [
            LeadershipMember(full_name="JOHN SMITH", job_title="CEO"),
            LeadershipMember(full_name="john smith", job_title="CEO"),
        ]
        result = cleaner._clean_leadership(leaders)
        assert len(result) == 1

    def test_filters_blacklisted_names(self, cleaner):
        leaders = [
            LeadershipMember(full_name="John Smith", job_title="CEO"),
            LeadershipMember(full_name="User Agreement", job_title="Executive"),
            LeadershipMember(full_name="Privacy Policy", job_title="Executive"),
            LeadershipMember(full_name="LinkedIn Member", job_title="Executive"),
        ]
        result = cleaner._clean_leadership(leaders)
        assert len(result) == 1
        assert result[0].full_name == "John Smith"

    def test_filters_garbage_links_or_short_names(self, cleaner):
        leaders = [
            LeadershipMember(full_name="Ab", job_title="Director"),  # too short
            LeadershipMember(full_name="About Cookie Policy Page", job_title="Link"),  # contains cookie policy term
            LeadershipMember(full_name="Jane Doe", job_title="VP"),
        ]
        result = cleaner._clean_leadership(leaders)
        assert len(result) == 1
        assert result[0].full_name == "Jane Doe"


# ---------------------------------------------------------------------------
# _clean_locations
# ---------------------------------------------------------------------------

class TestCleanLocations:
    def test_removes_locations_with_no_city_or_country(self, cleaner):
        locations = [CompanyLocation(city=None, country=None)]
        result = cleaner._clean_locations(locations)
        assert len(result) == 0

    def test_deduplicates_by_city_country(self, cleaner):
        locations = [
            CompanyLocation(city="Mumbai", country="India"),
            CompanyLocation(city="Mumbai", country="India"),
        ]
        result = cleaner._clean_locations(locations)
        assert len(result) == 1

    def test_keeps_different_cities(self, cleaner):
        locations = [
            CompanyLocation(city="Mumbai", country="India"),
            CompanyLocation(city="Bangalore", country="India"),
        ]
        result = cleaner._clean_locations(locations)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _calculate_data_quality_score
# ---------------------------------------------------------------------------

class TestDataQualityScore:
    def test_empty_data_scores_low(self, cleaner):
        data = LinkedInCompanyData(
            company_slug="empty-co",
            scraped_at=datetime.now(tz=timezone.utc),
        )
        score = cleaner._calculate_data_quality_score(data)
        assert score == 0.0

    def test_full_identity_scores_higher(self, cleaner, minimal_company_data):
        score = cleaner._calculate_data_quality_score(minimal_company_data)
        assert score > 0.0

    def test_score_is_between_0_and_1(self, cleaner, minimal_company_data):
        # Add posts and jobs
        minimal_company_data.recent_posts = [
            CompanyPost(post_text="Post number one with some meaningful content here."),
            CompanyPost(post_text="Post number two with even more meaningful content."),
        ]
        minimal_company_data.job_postings = [
            JobPosting(job_title="Senior Engineer"),
        ]
        score = cleaner._calculate_data_quality_score(minimal_company_data)
        assert 0.0 <= score <= 1.0

    def test_score_never_exceeds_1(self, cleaner, minimal_company_data):
        # Add many posts and jobs to try to overflow
        minimal_company_data.recent_posts = [
            CompanyPost(post_text=f"Post {i} with adequate length for testing purposes here.")
            for i in range(20)
        ]
        score = cleaner._calculate_data_quality_score(minimal_company_data)
        assert score <= 1.0


# ---------------------------------------------------------------------------
# _clean_employee_insights
# ---------------------------------------------------------------------------

class TestCleanEmployeeInsights:
    def test_normalizes_count_strings(self, cleaner):
        insights = EmployeeInsights(
            total_employee_count=250000,
            employees_on_linkedin_count=50000,
        )
        result = cleaner._clean_employee_insights(insights)
        assert result.total_employee_count == 250000
        assert result.employees_on_linkedin_count == 50000

    def test_filters_unrealistic_growth_6m(self, cleaner):
        insights = EmployeeInsights(employee_growth_percentage_6_months=999.9)
        result = cleaner._clean_employee_insights(insights)
        assert result.employee_growth_percentage_6_months is None

    def test_filters_unrealistic_growth_1y(self, cleaner):
        insights = EmployeeInsights(employee_growth_percentage_1_year=600.0)
        result = cleaner._clean_employee_insights(insights)
        assert result.employee_growth_percentage_1_year is None

    def test_keeps_realistic_growth(self, cleaner):
        insights = EmployeeInsights(
            employee_growth_percentage_6_months=15.5,
            employee_growth_percentage_1_year=30.0,
        )
        result = cleaner._clean_employee_insights(insights)
        assert result.employee_growth_percentage_6_months == 15.5
        assert result.employee_growth_percentage_1_year == 30.0

    def test_deduplicates_skills(self, cleaner):
        insights = EmployeeInsights(
            top_skills_listed=["Python", "Python", "Java", "Java", "AWS"]
        )
        result = cleaner._clean_employee_insights(insights)
        assert result.top_skills_listed.count("Python") == 1
        assert result.top_skills_listed.count("Java") == 1

    def test_limits_skills_to_20(self, cleaner):
        insights = EmployeeInsights(
            top_skills_listed=[f"Skill{i}" for i in range(50)]
        )
        result = cleaner._clean_employee_insights(insights)
        assert len(result.top_skills_listed) <= 20


# ---------------------------------------------------------------------------
# clean_raw_text_for_llm (module-level function)
# ---------------------------------------------------------------------------

class TestCleanRawTextForLlm:
    def test_strips_html_tags(self):
        raw = "<div><h1>Infosys</h1><p>A global company.</p></div>"
        result = clean_raw_text_for_llm(raw)
        assert "<div>" not in result
        assert "<h1>" not in result
        assert "Infosys" in result
        assert "A global company." in result

    def test_decodes_html_entities(self):
        raw = "Infosys &amp; Associates &ndash; IT Services"
        result = clean_raw_text_for_llm(raw)
        assert "&amp;" not in result
        assert "&" in result

    def test_removes_linkedin_boilerplate(self):
        raw = "Sign in to view\nInfosys is a tech company.\nJoin LinkedIn to connect."
        result = clean_raw_text_for_llm(raw)
        assert "Sign in to view" not in result
        assert "Join LinkedIn" not in result
        assert "Infosys is a tech company." in result

    def test_truncates_long_text(self):
        long_text = "A" * 20_000
        result = clean_raw_text_for_llm(long_text)
        assert len(result) <= 8_100  # 8000 + truncation marker

    def test_empty_input_returns_empty(self):
        assert clean_raw_text_for_llm("") == ""

    def test_skips_short_lines(self):
        # Lines under 3 chars should be filtered
        raw = "AB\nInfosys is a leading global IT company.\nOK"
        result = clean_raw_text_for_llm(raw)
        assert "AB" not in result


# ---------------------------------------------------------------------------
# Full clean() integration (uses real data objects, no external calls)
# ---------------------------------------------------------------------------

class TestFullClean:
    def test_clean_returns_company_data_and_score(self, cleaner, minimal_company_data):
        result_data, score = cleaner.clean(minimal_company_data)
        assert isinstance(result_data, LinkedInCompanyData)
        assert isinstance(score, float)

    def test_clean_sets_data_quality_score(self, cleaner, minimal_company_data):
        result_data, score = cleaner.clean(minimal_company_data)
        assert result_data.data_quality_score == score

    def test_clean_handles_none_identity(self, cleaner):
        data = LinkedInCompanyData(
            company_slug="no-identity",
            scraped_at=datetime.now(tz=timezone.utc),
            identity=None,
        )
        result_data, score = cleaner.clean(data)
        # Should NOT raise — just return empty/low score
        assert result_data.identity is None
        assert score == 0.0

    def test_clean_deduplicates_posts(self, cleaner, minimal_company_data):
        duplicate_post = CompanyPost(
            post_text="We are delighted to announce the launch of our new AI platform for enterprise."
        )
        minimal_company_data.recent_posts = [duplicate_post, duplicate_post, duplicate_post]
        result_data, _ = cleaner.clean(minimal_company_data)
        assert len(result_data.recent_posts) == 1
