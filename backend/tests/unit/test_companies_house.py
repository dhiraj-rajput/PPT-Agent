"""
Unit Tests for Companies House Integration
Tests CompaniesHouseClient, CompaniesHouseTendersClient, DocumentParser, and CompetitorProfiler.
"""

import unittest
from app.companies_house.ch_client import CompaniesHouseClient
from app.companies_house.opportunities import CompaniesHouseTendersClient
from app.companies_house.document_parser import CompaniesHouseDocumentParser
from app.companies_house.competitor_profiler import CompaniesHouseCompetitorProfiler


class TestCompaniesHouseIntegration(unittest.TestCase):
    def setUp(self):
        self.client = CompaniesHouseClient(api_key="mock_key")
        self.client.force_mock = True

    def test_get_company_profile(self):
        profile = self.client.get_company_profile("00044008")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.get("company_number"), "00044008")
        self.assertIn("company_name", profile)

    def test_search_companies_mock(self):
        res = self.client.search_companies("Rolls")
        self.assertIn("items", res)

    def test_tenders_enrichment(self):
        tenders_client = CompaniesHouseTendersClient(ch_client=self.client)
        tenders = tenders_client.search_uk_tenders(keyword="IT", limit=2)
        self.assertTrue(len(tenders) > 0)
        self.assertEqual(tenders[0]["source"], "Companies House")

    def test_competitor_profiler(self):
        profiler = CompaniesHouseCompetitorProfiler(ch_client=self.client)
        dossier = profiler.build_competitor_profile("00044008")
        self.assertEqual(dossier["source"], "Companies House")
        self.assertEqual(dossier["company_number"], "00044008")

    def test_document_parser(self):
        parser = CompaniesHouseDocumentParser(api_key="mock_key")
        metadata = parser.get_document_metadata("mock_doc_id")
        # Metadata will return None or dict, should not crash
        self.assertTrue(metadata is None or isinstance(metadata, dict))


if __name__ == "__main__":
    unittest.main()
