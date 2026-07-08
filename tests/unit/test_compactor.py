"""
tests/unit/test_compactor.py
----------------------------
Unit tests for models/compactor.py, verifying model parsing, URL helpers,
message building, OpenRouter calling, and model rotation fallback logic.
"""

import pytest
import json
import requests
from unittest.mock import MagicMock, patch
from models.compactor import (
    BusinessIntelligenceCompactor,
    _canonical_website,
    _domain_key,
    _build_messages,
)


def test_url_helpers():
    assert _canonical_website("wipro.com") == "https://wipro.com/"
    assert _canonical_website("http://WIPRO.COM/about") == "http://wipro.com/about"
    assert _canonical_website("") == ""

    assert _domain_key("https://www.wipro.com/index.html") == "wipro_com"
    assert _domain_key("http://wipro-tech.co.uk/") == "wipro_tech_co_uk"
    assert _domain_key("") == ""


def test_parse_json_from_response():
    compactor = BusinessIntelligenceCompactor()
    
    # 1. Clean JSON
    raw_json = '{"company_name": "Test"}'
    parsed = compactor._parse_json_from_response(raw_json)
    assert parsed["company_name"] == "Test"

    # 2. Markdown fenced JSON
    fenced_json = "```json\n{\n  \"company_name\": \"Fenced\"\n}\n```"
    parsed = compactor._parse_json_from_response(fenced_json)
    assert parsed["company_name"] == "Fenced"

    # 3. Bad enclosing formatting
    embedded_json = "Here is the response: {\"company_name\": \"Embedded\"} Hope you like it!"
    parsed = compactor._parse_json_from_response(embedded_json)
    assert parsed["company_name"] == "Embedded"

    # 4. Invalid JSON
    with pytest.raises(ValueError):
        compactor._parse_json_from_response("Not a JSON string")


def test_build_messages():
    data = {
        "company_name": "TestCorp",
        "raw_website_text": "A" * 10000,
        "google_search_insights": ["Insight"] * 20,
    }
    messages = _build_messages(data)
    
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    
    # Verify truncation logic
    user_content = messages[1]["content"]
    assert "truncated" in user_content
    # The truncated text length in JSON should be around 5000 chars plus metadata, so total user_content should be < 16000
    assert len(user_content) < 16000


@patch("requests.post")
def test_call_openrouter_success(mock_post):
    # Mock OpenRouter success response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"company_name": "Success"}'
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    compactor = BusinessIntelligenceCompactor()
    compactor.openrouter_api_key = "test_key"
    
    res = compactor._call_openrouter([{"role": "user", "content": "hi"}])
    assert res == '{"company_name": "Success"}'
    mock_post.assert_called_once()


@patch("requests.post")
def test_run_llm_compaction_fallback_on_429(mock_post):
    # Simulate a rate limit (429 status code) on the primary model,
    # followed by success on the fallback model.
    mock_429_response = MagicMock()
    mock_429_response.status_code = 429
    mock_429_response.text = "Rate limit exceeded"
    
    # Create the HTTPError to trigger fallback
    http_err = requests.HTTPError("429 Client Error", response=mock_429_response)
    
    mock_success_response = MagicMock()
    mock_success_response.status_code = 200
    mock_success_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"company_name": "Fallback Success"}'
                }
            }
        ]
    }

    # Side effect: first call raises HTTPError, second call returns success response
    mock_post.side_effect = [http_err, mock_success_response]

    compactor = BusinessIntelligenceCompactor()
    compactor.openrouter_api_key = "test_key"
    compactor.openrouter_model = "google/gemma-4-31b-it:free"
    compactor._free_model_fallbacks = ["google/gemma-3-27b-it:free"]

    normalized_data = {"company_name": "FallbackCorp"}
    
    result = compactor._run_llm_compaction(normalized_data, max_retries=1)
    
    assert result["company_name"] == "Fallback Success"
    assert mock_post.call_count == 2
    # Verify it tried the primary model first, then the fallback model
    calls = mock_post.call_args_list
    assert calls[0][1]["json"]["model"] == "google/gemma-4-31b-it:free"
    assert calls[1][1]["json"]["model"] == "google/gemma-3-27b-it:free"
