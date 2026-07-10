"""
tests/unit/test_rfp_pipeline.py
-------------------------------
Unit tests for the SAM.gov Opportunities, Entity Management,
competitor extraction, and profiling modules.
"""

import pytest
from unittest.mock import MagicMock, patch

from api.sam_gov.opportunities import SAMOpportunitiesClient
from api.sam_gov.sam_client import SAMEntityClient
from api.sam_gov.competitors import CompetitorExtractor
from api.sam_gov.competitor_profiler import CompetitorProfiler


class TestSAMOpportunitiesClient:
    def test_mock_fallback_search(self):
        client = SAMOpportunitiesClient(api_key=None)
        results = client.search_opportunities(query="analytics", use_mock=True)
        
        assert len(results) > 0
        assert any("analytics" in opp["title"].lower() for opp in results)

    def test_structure_rfp_profile(self):
        client = SAMOpportunitiesClient(api_key=None)
        opp = {
            "opportunityId": "test-id-123",
            "solicitationNumber": "TEST-RFP-001",
            "title": "Data Engineering Services",
            "type": "Solicitation",
            "postedDate": "2026-06-01",
            "responseDeadline": "2026-07-31",
            "department": "Department of Commerce",
            "subTier": "Census Bureau",
            "office": "Acquisition Division",
            "description": "Provide data engineering support.",
            "naicsCode": "541512",
            "setAside": "Total Small Business",
            "placeOfPerformance": {
                "city": "Suitland",
                "state": "MD",
                "zip": "20746"
            },
            "pointOfContact": [
                {
                    "name": "Jane Doe",
                    "email": "jane.doe@commerce.gov",
                    "phone": "301-555-0199"
                }
            ],
            "award": {
                "awardee": {
                    "legalBusinessName": "DataCorp Inc",
                    "uei": "UEI_DATACORP1",
                    "cageCode": "12345"
                },
                "amount": "$1,000,000.00",
                "date": "2026-07-01",
                "number": "COMM-26-C-0001"
            }
        }
        
        profile = client.structure_rfp_profile(opp)
        assert profile["opportunity_id"] == "test-id-123"
        assert profile["solicitation_number"] == "TEST-RFP-001"
        assert profile["title"] == "Data Engineering Services"
        assert profile["naics"] == "541512"
        assert profile["set_aside"] == "Total Small Business"
        assert "Suitland, MD, 20746" in profile["place_of_performance"]
        assert len(profile["pocs"]) == 1
        assert profile["pocs"][0]["name"] == "Jane Doe"
        assert profile["award"]["awardee_name"] == "DataCorp Inc"
        assert profile["award"]["amount"] == "$1,000,000.00"


class TestSAMEntityClient:
    def test_mock_entity_lookup(self):
        client = SAMEntityClient(api_key=None)
        details = client.get_entity_details("UEI_GUIDEHOUSE1", use_mock=True)
        
        assert details is not None
        assert details["entityRegistration"]["legalBusinessName"] == "Guidehouse LLP"
        assert details["coreData"]["physicalAddress"]["city"] == "McLean"


class TestCompetitorExtractor:
    def test_mock_competitor_extraction(self):
        extractor = CompetitorExtractor()
        results = extractor.find_competitors_and_bids("N00164-26-R-0001", use_mock=True)
        
        assert len(results) > 0
        assert any(c["company_name"] == "Booz Allen Hamilton Inc." for c in results)
        assert any(c["protest_status"] == "Protester" for c in results)


class TestCompetitorProfiler:
    @patch("api.sam_gov.competitor_profiler.CompetitorProfiler._extract_profile_via_search")
    def test_profiler_limits_and_caching(self, mock_extract):
        # Setup mock profile extraction
        mock_extract.return_value = {
            "company_name": "Test Competitor",
            "website": "https://testcomp.com",
            "industry": "IT"
        }
        
        # Instantiate profiler with limit = 1 and no database client connection
        profiler = CompetitorProfiler(limit=1, cache_days=7)
        profiler.db = None # force no cache check
        
        competitors = [
            {"company_name": "Comp A"},
            {"company_name": "Comp B"},
        ]
        
        profiles = profiler.profile_competitors(competitors)
        
        # Only Comp A should have been actively profiled because limit is 1
        assert len(profiles) == 1
        assert mock_extract.call_count == 1
        mock_extract.assert_called_once_with("Comp A", use_mock=False)


class TestDocumentParser:
    def test_html_parsing(self):
        from api.sam_gov.document_parser import DocumentParser
        parser = DocumentParser()
        html = b"<html><body><h1>Title</h1><p>This is a test paragraph.</p></body></html>"
        text = parser.extract_text_from_html(html)
        assert "Title" in text
        assert "This is a test paragraph." in text

