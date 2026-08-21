"""
tests/unit/test_linkedin_outreach.py
-------------------------------------
Unit tests for the LinkedIn Outreach Module (Dev B).
Covers AI prompt generation, reply classification, and profile parsing.
"""

from unittest.mock import MagicMock, patch
import pytest

try:
    from pipeline.ai.outreach_prompts import (
        classify_reply_intent,
        generate_connection_note,
        generate_followup_message,
    )
    _OUTREACH_PROMPTS_OK = True
except ImportError:
    _OUTREACH_PROMPTS_OK = False


@pytest.mark.skipif(not _OUTREACH_PROMPTS_OK, reason="pipeline.ai.outreach_prompts not available")
class TestLinkedInAIOutreach:

    @patch("pipeline.ai.outreach_prompts.get_ai_client")
    def test_generate_connection_note_character_limit(self, mock_get_client):
        # Set up mock AI client response
        mock_client = MagicMock()
        mock_client.chat_text.return_value = "Hello! I saw your profile and loved your work. I would love to connect."
        mock_get_client.return_value = mock_client

        target_profile = {
            "full_name": "John Doe",
            "title": "Software Engineer",
            "organization_name": "Acme Corp",
            "headline": "Software Engineer at Acme Corp",
            "summary": "Building cool things.",
            "experience": [{"title": "Software Engineer", "company": "Acme Corp"}]
        }
        our_company = "We help developers write clean code."

        note = generate_connection_note(target_profile, our_company)
        
        # Verify the client was called
        mock_client.chat_text.assert_called_once()
        # Verify note is clean and within 300 character limit
        assert len(note) <= 300
        assert "John Doe" not in note  # should not default greetings unless fallback

    @patch("pipeline.ai.outreach_prompts.get_ai_client")
    def test_generate_connection_note_truncation(self, mock_get_client):
        # Return a response exceeding 300 chars to test hard truncation
        mock_client = MagicMock()
        mock_client.chat_text.return_value = "A" * 350
        mock_get_client.return_value = mock_client

        target_profile = {"full_name": "Jane"}
        our_company = "Company Info"

        note = generate_connection_note(target_profile, our_company)
        assert len(note) == 300
        assert note.endswith("...")

    @patch("pipeline.ai.outreach_prompts.get_ai_client")
    def test_generate_followup_message(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.chat_text.return_value = "Thanks for connecting. Let's discuss collaboration."
        mock_get_client.return_value = mock_client

        target_profile = {"full_name": "Jane Smith"}
        chat_history = [{"direction": "out", "content": "Hi"}, {"direction": "in", "content": "Hello"}]
        our_company = "Orbit"

        msg = generate_followup_message(target_profile, chat_history, our_company)
        assert msg == "Thanks for connecting. Let's discuss collaboration."

    @patch("pipeline.ai.outreach_prompts.get_ai_client")
    def test_classify_reply_intent(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.chat_json.return_value = {
            "intent": "interested",
            "confidence": 0.95,
            "suggested_next_action": "Send calendar link."
        }
        mock_get_client.return_value = mock_client

        result = classify_reply_intent("I would love to see a demo of your product next Tuesday.")
        
        assert result["intent"] == "interested"
        assert result["confidence"] == 0.95
        assert result["suggested_next_action"] == "Send calendar link."
