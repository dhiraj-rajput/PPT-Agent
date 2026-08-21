"""
tests/unit/test_helpers.py
--------------------------
Unit tests for utils/helpers.py.

Covers URL validation, slug extraction, datetime helpers,
and the count-string parser utilities.
"""

from datetime import datetime, timezone

import pytest
from utils.helpers import (
    extract_company_slug_from_url,
    format_datetime_for_display,
    get_utc_now,
    is_valid_url,
    normalize_linkedin_company_url,
    safe_json_dumps,
)

# ---------------------------------------------------------------------------
# is_valid_url
# ---------------------------------------------------------------------------

class TestIsValidUrl:
    def test_valid_https_url(self):
        assert is_valid_url("https://www.linkedin.com/company/infosys") is True

    def test_valid_http_url(self):
        assert is_valid_url("http://example.com") is True

    def test_missing_scheme_is_invalid(self):
        assert is_valid_url("linkedin.com/company/infosys") is False

    def test_ftp_scheme_is_invalid(self):
        assert is_valid_url("ftp://files.example.com") is False

    def test_empty_string_is_invalid(self):
        assert is_valid_url("") is False

    def test_just_a_word_is_invalid(self):
        assert is_valid_url("google") is False

    def test_url_with_path_is_valid(self):
        assert is_valid_url("https://infosys.com/products/ai") is True

    def test_url_with_query_params_is_valid(self):
        assert is_valid_url("https://site.com/page?q=test&from=linkedin") is True


# ---------------------------------------------------------------------------
# normalize_linkedin_company_url
# ---------------------------------------------------------------------------

class TestNormalizeLinkedInCompanyUrl:
    def test_removes_query_params(self):
        url = "https://www.linkedin.com/company/infosys?trk=top_nav"
        result = normalize_linkedin_company_url(url)
        assert "trk" not in result
        assert result == "https://www.linkedin.com/company/infosys"

    def test_removes_fragment(self):
        url = "https://www.linkedin.com/company/infosys#about"
        result = normalize_linkedin_company_url(url)
        assert "#about" not in result

    def test_strips_trailing_slash(self):
        url = "https://www.linkedin.com/company/infosys/"
        result = normalize_linkedin_company_url(url)
        assert not result.endswith("/")

    def test_canonical_url_unchanged(self):
        url = "https://www.linkedin.com/company/infosys"
        result = normalize_linkedin_company_url(url)
        assert result == url


# ---------------------------------------------------------------------------
# extract_company_slug_from_url
# ---------------------------------------------------------------------------

class TestExtractCompanySlugFromUrl:
    def test_basic_slug_extraction(self):
        url = "https://www.linkedin.com/company/infosys"
        assert extract_company_slug_from_url(url) == "infosys"

    def test_slug_with_dash(self):
        url = "https://www.linkedin.com/company/tata-consultancy-services"
        assert extract_company_slug_from_url(url) == "tata-consultancy-services"

    def test_url_with_trailing_slash(self):
        url = "https://www.linkedin.com/company/infosys/"
        assert extract_company_slug_from_url(url) == "infosys"

    def test_url_with_query_params(self):
        url = "https://www.linkedin.com/company/infosys?trk=top"
        assert extract_company_slug_from_url(url) == "infosys"

    def test_invalid_url_raises_value_error(self):
        with pytest.raises(ValueError):
            extract_company_slug_from_url("https://www.linkedin.com/in/john-doe")

    def test_non_company_url_raises_value_error(self):
        with pytest.raises(ValueError):
            extract_company_slug_from_url("https://www.linkedin.com/jobs/view/123")

    def test_empty_slug_raises_value_error(self):
        with pytest.raises(ValueError):
            extract_company_slug_from_url("https://www.linkedin.com/company/")


# ---------------------------------------------------------------------------
# get_utc_now
# ---------------------------------------------------------------------------

class TestGetUtcNow:
    def test_returns_datetime(self):
        result = get_utc_now()
        assert isinstance(result, datetime)

    def test_is_timezone_aware(self):
        result = get_utc_now()
        assert result.tzinfo is not None

    def test_is_utc(self):
        result = get_utc_now()
        assert result.tzinfo == timezone.utc

    def test_two_calls_are_sequential(self):
        t1 = get_utc_now()
        t2 = get_utc_now()
        assert t2 >= t1


# ---------------------------------------------------------------------------
# format_datetime_for_display
# ---------------------------------------------------------------------------

class TestFormatDatetimeForDisplay:
    def test_formats_aware_datetime(self):
        dt = datetime(2026, 7, 6, 12, 30, 0, tzinfo=timezone.utc)
        result = format_datetime_for_display(dt)
        assert result == "2026-07-06T12:30:00Z"

    def test_formats_naive_datetime_as_utc(self):
        dt = datetime(2026, 1, 1, 0, 0, 0)  # naive
        result = format_datetime_for_display(dt)
        assert result.endswith("Z")
        assert "2026-01-01" in result

    def test_output_is_iso_format(self):
        dt = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        result = format_datetime_for_display(dt)
        assert result == "2026-12-31T23:59:59Z"


# ---------------------------------------------------------------------------
# safe_json_dumps
# ---------------------------------------------------------------------------

class TestSafeJsonDumps:
    def test_serializes_basic_dict(self):
        data = {"name": "Infosys", "employees": 343000}
        result = safe_json_dumps(data)
        assert "Infosys" in result
        assert "343000" in result

    def test_serializes_datetime(self):
        dt = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
        data = {"scraped_at": dt}
        result = safe_json_dumps(data)
        assert "2026-07-06" in result

    def test_handles_list(self):
        result = safe_json_dumps(["a", "b", "c"])
        assert '"a"' in result
        assert '"c"' in result

    def test_returns_string(self):
        assert isinstance(safe_json_dumps({"key": "value"}), str)

    def test_indentation(self):
        data = {"key": "value"}
        result = safe_json_dumps(data, indent=4)
        # Should contain 4-space indentation
        assert "    " in result
