"""
tests/unit/test_storage.py
--------------------------
Unit tests for linkedin/storage.py.

All MongoDB calls are mocked using unittest.mock.
No real database is needed to run these tests.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

from linkedin.models import CompanyIdentity, LinkedInCompanyData, RawLinkedInScrapedData
from linkedin.storage import LinkedInStorage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def storage() -> LinkedInStorage:
    return LinkedInStorage()


@pytest.fixture
def sample_company_data() -> LinkedInCompanyData:
    identity = CompanyIdentity(
        company_name="Infosys",
        linkedin_url="https://www.linkedin.com/company/infosys",
        company_slug="infosys",
        industry="IT Services",
    )
    return LinkedInCompanyData(
        company_slug="infosys",
        identity=identity,
        scraped_at=datetime.now(tz=timezone.utc),
        scrape_layers_used=["public", "browser"],
        data_quality_score=0.75,
    )


@pytest.fixture
def sample_raw_data() -> RawLinkedInScrapedData:
    return RawLinkedInScrapedData(
        company_slug="infosys",
        scrape_layer="public",
        page_url="https://www.linkedin.com/company/infosys",
        scraped_at=datetime.now(tz=timezone.utc),
        scrape_success=True,
    )


# ---------------------------------------------------------------------------
# save_raw_scraped_data
# ---------------------------------------------------------------------------

class TestSaveRawScrapedData:
    @patch("linkedin.storage.get_collection")
    def test_inserts_document_and_returns_id(self, mock_get_collection, storage, sample_raw_data):
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        fake_object_id = MagicMock()
        fake_object_id.__str__ = lambda *args, **kwargs: "507f1f77bcf86cd799439011"
        mock_collection.insert_one.return_value = MagicMock(inserted_id=fake_object_id)

        result = storage.save_raw_scraped_data(sample_raw_data)

        # Should call insert_one exactly once
        mock_collection.insert_one.assert_called_once()
        # Should return the string representation of the ObjectId
        assert result == "507f1f77bcf86cd799439011"

    @patch("linkedin.storage.get_collection")
    def test_document_contains_company_slug(self, mock_get_collection, storage, sample_raw_data):
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        fake_id = MagicMock()
        fake_id.__str__ = lambda *args, **kwargs: "abc123"
        mock_collection.insert_one.return_value = MagicMock(inserted_id=fake_id)

        storage.save_raw_scraped_data(sample_raw_data)

        inserted_doc = mock_collection.insert_one.call_args[0][0]
        assert inserted_doc["company_slug"] == "infosys"
        assert inserted_doc["scrape_layer"] == "public"


# ---------------------------------------------------------------------------
# save_structured_company_data
# ---------------------------------------------------------------------------

class TestSaveStructuredCompanyData:
    @patch("linkedin.storage.get_collection")
    def test_calls_update_one_upsert(self, mock_get_collection, storage, sample_company_data):
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        # Simulate a new insert (upserted_id is not None)
        fake_upserted_id = MagicMock()
        fake_upserted_id.__str__ = lambda *args, **kwargs: "newdoc123"
        mock_collection.update_one.return_value = MagicMock(
            upserted_id=fake_upserted_id,
            modified_count=0,
        )

        result = storage.save_structured_company_data(sample_company_data)

        # Should use upsert=True
        call_kwargs = mock_collection.update_one.call_args[1]
        assert call_kwargs.get("upsert") is True

        # Should return the new doc ID
        assert result == "newdoc123"

    @patch("linkedin.storage.get_collection")
    def test_update_case_fetches_existing_id(self, mock_get_collection, storage, sample_company_data):
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        # Simulate an update (upserted_id is None)
        mock_collection.update_one.return_value = MagicMock(
            upserted_id=None,
            modified_count=1,
        )
        fake_existing = {"_id": MagicMock(__str__=lambda self: "existingdoc456")}
        mock_collection.find_one.return_value = fake_existing

        result = storage.save_structured_company_data(sample_company_data)

        # Should fetch the existing doc's ID
        mock_collection.find_one.assert_called_once()
        assert result == "existingdoc456"

    @patch("linkedin.storage.get_collection")
    def test_filter_uses_company_slug(self, mock_get_collection, storage, sample_company_data):
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        fake_upserted_id = MagicMock()
        fake_upserted_id.__str__ = lambda *args, **kwargs: "id123"
        mock_collection.update_one.return_value = MagicMock(upserted_id=fake_upserted_id)

        storage.save_structured_company_data(sample_company_data)
        call_kwargs = mock_collection.update_one.call_args[1]
        filter_arg = call_kwargs.get("filter")
        assert filter_arg == {"company_slug": "infosys"}


# ---------------------------------------------------------------------------
# get_structured_company_data
# ---------------------------------------------------------------------------

class TestGetStructuredCompanyData:
    @patch("linkedin.storage.get_collection")
    def test_returns_none_when_not_found(self, mock_get_collection, storage):
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = None
        mock_get_collection.return_value = mock_collection

        result = storage.get_structured_company_data("nonexistent-slug")
        assert result is None

    @patch("linkedin.storage.get_collection")
    def test_returns_company_data_when_found(self, mock_get_collection, storage, sample_company_data):
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        # Simulate a found document
        doc = sample_company_data.model_dump()
        doc["_id"] = "some-mongo-id"  # MongoDB adds this
        mock_collection.find_one.return_value = doc

        result = storage.get_structured_company_data("infosys")

        assert result is not None
        assert isinstance(result, LinkedInCompanyData)
        assert result.company_slug == "infosys"

    @patch("linkedin.storage.get_collection")
    def test_strips_mongo_id_before_parse(self, mock_get_collection, storage, sample_company_data):
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        doc = sample_company_data.model_dump()
        doc["_id"] = "mongo-internal-id"
        mock_collection.find_one.return_value = doc

        result = storage.get_structured_company_data("infosys")
        # Should not raise ValidationError from _id field
        assert result is not None


# ---------------------------------------------------------------------------
# company_data_exists
# ---------------------------------------------------------------------------

class TestCompanyDataExists:
    @patch("linkedin.storage.get_collection")
    def test_returns_true_when_exists(self, mock_get_collection, storage):
        mock_collection = MagicMock()
        mock_collection.count_documents.return_value = 1
        mock_get_collection.return_value = mock_collection

        result = storage.company_data_exists("infosys")
        assert result is True

    @patch("linkedin.storage.get_collection")
    def test_returns_false_when_not_found(self, mock_get_collection, storage):
        mock_collection = MagicMock()
        mock_collection.count_documents.return_value = 0
        mock_get_collection.return_value = mock_collection

        result = storage.company_data_exists("unknown-company")
        assert result is False

    @patch("linkedin.storage.get_collection")
    def test_uses_limit_1_for_efficiency(self, mock_get_collection, storage):
        mock_collection = MagicMock()
        mock_collection.count_documents.return_value = 0
        mock_get_collection.return_value = mock_collection

        storage.company_data_exists("infosys")

        # Ensure limit=1 is passed for efficiency (avoids full collection scan)
        call_kwargs = mock_collection.count_documents.call_args[1]
        assert call_kwargs.get("limit") == 1


# ---------------------------------------------------------------------------
# log_scrape_operation
# ---------------------------------------------------------------------------

class TestLogScrapeOperation:
    @patch("linkedin.storage.get_collection")
    def test_inserts_log_with_correct_fields(self, mock_get_collection, storage):
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        storage.log_scrape_operation(
            company_slug="infosys",
            scrape_status="success",
            layers_used=["public", "browser"],
            duration_seconds=45.6,
        )

        mock_collection.insert_one.assert_called_once()
        log_doc = mock_collection.insert_one.call_args[0][0]

        assert log_doc["company_slug"] == "infosys"
        assert log_doc["scrape_status"] == "success"
        assert log_doc["layers_used"] == ["public", "browser"]
        assert log_doc["duration_seconds"] == 45.6
        assert log_doc["error_message"] is None

    @patch("linkedin.storage.get_collection")
    def test_logs_error_message_on_failure(self, mock_get_collection, storage):
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        storage.log_scrape_operation(
            company_slug="infosys",
            scrape_status="failed",
            layers_used=["public"],
            duration_seconds=5.0,
            error_message="LLM rate limit exceeded",
        )

        log_doc = mock_collection.insert_one.call_args[0][0]
        assert log_doc["error_message"] == "LLM rate limit exceeded"
        assert log_doc["scrape_status"] == "failed"


# ---------------------------------------------------------------------------
# get_recent_scrape_logs
# ---------------------------------------------------------------------------

class TestGetRecentScrapeLogs:
    @patch("linkedin.storage.get_collection")
    def test_returns_list_of_dicts(self, mock_get_collection, storage):
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.limit.return_value = [
            {"company_slug": "infosys", "scrape_status": "success"},
        ]
        mock_collection.find.return_value = mock_cursor

        result = storage.get_recent_scrape_logs("infosys", limit=5)

        assert isinstance(result, list)

    @patch("linkedin.storage.get_collection")
    def test_excludes_mongo_id_field(self, mock_get_collection, storage):
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.limit.return_value = []
        mock_collection.find.return_value = mock_cursor

        storage.get_recent_scrape_logs("infosys")

        # Should project out _id
        find_call_args = mock_collection.find.call_args[0]
        assert find_call_args[1] == {"_id": 0}
