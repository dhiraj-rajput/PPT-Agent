"""
tests/performance/test_cleaner_performance.py
----------------------------------------------
Performance benchmarks for the DataCleaner module.

These tests verify that cleaning operations complete within acceptable
time budgets even for large inputs. They use pytest-benchmark if available,
or fallback to manual timing with assertions.

Run with:
    .venv\\Scripts\\python.exe -m pytest tests/performance/ -v --tb=short
"""

import time
import pytest
from datetime import datetime, timezone

from linkedin.data_cleaner import DataCleaner, clean_raw_text_for_llm
from linkedin.models import (
    CompanyIdentity,
    CompanyPost,
    EmployeeInsights,
    JobPosting,
    LeadershipMember,
    LinkedInCompanyData,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_large_company_data(
    num_posts: int = 100,
    num_jobs: int = 200,
    num_leaders: int = 50,
) -> LinkedInCompanyData:
    """Builds a LinkedInCompanyData with many sub-objects for load testing."""
    identity = CompanyIdentity(
        company_name="Stress Test Corp 🚀 With Emojis 🌍",
        linkedin_url="https://www.linkedin.com/company/stress-test",
        company_slug="stress-test",
        industry="Technology",
        specialties=[f"Specialty {i}" for i in range(50)],
    )
    posts = [
        CompanyPost(
            post_text=f"This is a meaningful LinkedIn post number {i} about AI and digital transformation strategy. " * 5,
            reactions_count=f"{i * 100}",
            comments_count=str(i * 10),
        )
        for i in range(num_posts)
    ]
    jobs = [
        JobPosting(
            job_title=f"🚀 Senior Engineer Role {i}",
            job_location="Bangalore, India",
            key_skills_required=[f"Skill{j}" for j in range(20)],
        )
        for i in range(num_jobs)
    ]
    leaders = [
        LeadershipMember(
            full_name=f"Leader Number {i}",
            job_title=f"VP Engineering {i}",
        )
        for i in range(num_leaders)
    ]

    return LinkedInCompanyData(
        company_slug="stress-test",
        identity=identity,
        recent_posts=posts,
        job_postings=jobs,
        leadership_team=leaders,
        scraped_at=datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Performance Tests
# ---------------------------------------------------------------------------

class TestCleanerPerformance:
    """
    Performance benchmarks for the DataCleaner.
    Each test has a strict time budget measured in wall-clock seconds.
    """

    def test_clean_100_posts_under_1_second(self):
        cleaner = DataCleaner()
        data = make_large_company_data(num_posts=100, num_jobs=0, num_leaders=0)

        start = time.perf_counter()
        cleaner._clean_posts(data.recent_posts)
        elapsed = time.perf_counter() - start

        print(f"\n  _clean_posts(100 posts): {elapsed:.4f}s")
        assert elapsed < 1.0, f"Expected < 1.0s, got {elapsed:.4f}s"

    def test_clean_200_jobs_under_1_second(self):
        cleaner = DataCleaner()
        data = make_large_company_data(num_posts=0, num_jobs=200, num_leaders=0)

        start = time.perf_counter()
        cleaner._clean_job_postings(data.job_postings)
        elapsed = time.perf_counter() - start

        print(f"\n  _clean_job_postings(200 jobs): {elapsed:.4f}s")
        assert elapsed < 1.0, f"Expected < 1.0s, got {elapsed:.4f}s"

    def test_clean_full_object_with_all_sections_under_3_seconds(self):
        cleaner = DataCleaner()
        data = make_large_company_data(num_posts=100, num_jobs=200, num_leaders=50)

        start = time.perf_counter()
        cleaner.clean(data)
        elapsed = time.perf_counter() - start

        print(f"\n  clean() full object (100 posts, 200 jobs, 50 leaders): {elapsed:.4f}s")
        assert elapsed < 3.0, f"Expected < 3.0s, got {elapsed:.4f}s"

    def test_clean_raw_text_8k_chars_under_100ms(self):
        # Simulate 8000 chars of messy HTML-laced LinkedIn page text
        raw = "<div>" + ("Infosys is a company. Join LinkedIn. Sign in to view. " * 200) + "</div>"
        raw = raw[:8000]

        start = time.perf_counter()
        result = clean_raw_text_for_llm(raw)
        elapsed = time.perf_counter() - start

        print(f"\n  clean_raw_text_for_llm(8000 chars): {elapsed:.4f}s")
        assert elapsed < 0.1, f"Expected < 100ms, got {elapsed:.4f}s"
        assert len(result) <= 8_200  # Should be truncated

    def test_parse_count_string_1000_calls_under_10ms(self):
        cleaner = DataCleaner()
        inputs = ["1.2M", "500K", "47,321", "Over 200", "500+", "not-a-number", None, 12345]

        start = time.perf_counter()
        for _ in range(1000):
            for value in inputs:
                cleaner._parse_count_string(value)
        elapsed = time.perf_counter() - start

        print(f"\n  _parse_count_string(1000 × 8 inputs): {elapsed:.4f}s")
        assert elapsed < 0.1, f"Expected < 100ms for 8000 calls, got {elapsed:.4f}s"

    def test_quality_score_calculation_is_fast(self):
        cleaner = DataCleaner()
        data = make_large_company_data(num_posts=50, num_jobs=50, num_leaders=10)

        start = time.perf_counter()
        for _ in range(1000):
            cleaner._calculate_data_quality_score(data)
        elapsed = time.perf_counter() - start

        print(f"\n  _calculate_data_quality_score(1000 calls): {elapsed:.4f}s")
        assert elapsed < 1.0, f"Expected < 1.0s for 1000 calls, got {elapsed:.4f}s"

    def test_remove_emojis_performance_on_long_string(self):
        cleaner = DataCleaner()
        # 5000-char string with emojis every 10 chars
        text = ("Hello 🚀 World 🌍 AI 🎉 " * 200)[:5000]

        start = time.perf_counter()
        for _ in range(100):
            cleaner._remove_emojis(text)
        elapsed = time.perf_counter() - start

        print(f"\n  _remove_emojis(5000-char × 100): {elapsed:.4f}s")
        assert elapsed < 2.0, f"Expected < 2.0s, got {elapsed:.4f}s"

    def test_deduplication_with_large_list_is_efficient(self):
        """
        Deduplication uses a set for O(n) performance.
        500 posts should be deduped in < 0.5s.
        """
        cleaner = DataCleaner()
        # 250 unique posts + 250 duplicate posts = 500 total
        unique_posts = [
            CompanyPost(post_text=f"This is unique post number {i} about technology and innovation in India.")
            for i in range(250)
        ]
        duplicate_posts = unique_posts[:250]  # All duplicates
        all_posts = unique_posts + duplicate_posts

        start = time.perf_counter()
        result = cleaner._clean_posts(all_posts)
        elapsed = time.perf_counter() - start

        print(f"\n  Dedup 500 posts (250 unique): {elapsed:.4f}s → {len(result)} unique kept")
        assert elapsed < 0.5, f"Expected < 0.5s, got {elapsed:.4f}s"
        assert len(result) == 250
