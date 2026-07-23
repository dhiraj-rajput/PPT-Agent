"""
tests/unit/test_browser_scraper.py
------------------------------------
Unit tests for linkedin/browser_scraper.py.

Focuses on:
  1. _parse_extracted_content — JSON parsing and list-unwrapping logic
  2. Verifying that the bug fix (list → dict unwrapping) works correctly
  3. Edge cases: empty lists, nested lists, invalid JSON, None
"""

import json
import pytest

from pipeline.linkedin.browser_scraper import BrowserLinkedInScraper


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def scraper() -> BrowserLinkedInScraper:
    """Browser scraper instance — browser is NOT initialized here."""
    return BrowserLinkedInScraper()


# ---------------------------------------------------------------------------
# _parse_extracted_content
# ---------------------------------------------------------------------------

class TestParseExtractedContent:
    """Tests the core JSON parsing/unwrapping logic."""

    def test_parses_simple_dict(self, scraper):
        content = json.dumps({"company_name": "Infosys", "industry": "IT"})
        result = scraper._parse_extracted_content(content, "main", "infosys")
        assert isinstance(result, dict)
        assert result["company_name"] == "Infosys"

    def test_unwraps_single_item_list_containing_dict(self, scraper):
        """
        BUG REGRESSION TEST:
        Crawl4AI used to return [{...}] instead of {...}.
        _parse_extracted_content must auto-unwrap single-item lists.
        """
        content = json.dumps([{"company_name": "Infosys", "industry": "IT"}])
        result = scraper._parse_extracted_content(content, "main", "infosys")
        assert isinstance(result, dict)
        assert result["company_name"] == "Infosys"

    def test_keeps_multi_item_list_as_list(self, scraper):
        """Multi-item lists (e.g. posts, jobs) should NOT be unwrapped."""
        posts = [
            {"post_text": "Post 1"},
            {"post_text": "Post 2"},
            {"post_text": "Post 3"},
        ]
        content = json.dumps(posts)
        result = scraper._parse_extracted_content(content, "posts", "infosys")
        assert isinstance(result, list)
        assert len(result) == 3

    def test_returns_none_for_empty_list(self, scraper):
        content = json.dumps([])
        result = scraper._parse_extracted_content(content, "main", "infosys")
        assert result is None

    def test_returns_none_for_none_input(self, scraper):
        result = scraper._parse_extracted_content(None, "main", "infosys")
        assert result is None

    def test_returns_none_for_empty_string(self, scraper):
        result = scraper._parse_extracted_content("", "main", "infosys")
        assert result is None

    def test_returns_none_for_invalid_json(self, scraper):
        result = scraper._parse_extracted_content("{not: valid json}", "main", "infosys")
        assert result is None

    def test_returns_none_for_truncated_json(self, scraper):
        result = scraper._parse_extracted_content('{"company_name": "Inf', "main", "infosys")
        assert result is None

    def test_handles_deeply_nested_valid_json(self, scraper):
        content = json.dumps({
            "company_name": "Infosys",
            "locations": [{"city": "Bangalore", "country": "India"}],
        })
        result = scraper._parse_extracted_content(content, "about", "infosys")
        assert isinstance(result, dict)
        assert isinstance(result["locations"], list)

    def test_single_item_list_with_non_dict_not_unwrapped(self, scraper):
        """A list like ["string"] should remain a list — only [{...}] is unwrapped."""
        content = json.dumps(["just-a-string"])
        result = scraper._parse_extracted_content(content, "main", "infosys")
        # This is a list with a string, not a dict — keep it as-is (list)
        assert isinstance(result, list)

    def test_parses_empty_dict(self, scraper):
        content = json.dumps({})
        result = scraper._parse_extracted_content(content, "main", "infosys")
        assert isinstance(result, dict)
        assert result == {}

    def test_single_item_list_containing_empty_dict(self, scraper):
        """A single-item list with an empty dict should still be unwrapped."""
        content = json.dumps([{}])
        result = scraper._parse_extracted_content(content, "main", "infosys")
        assert isinstance(result, dict)
        assert result == {}
