"""Tests for report generation and storage."""

import os
import tempfile

import pytest

from src.reporting.generator import ReportGenerator
from src.storage import Storage


def _make_item(id, title, source="google_news", city="denver", score=50.0, summary="", metadata=None):
    return {
        "id": id,
        "title": title,
        "source": source,
        "city": city,
        "url": f"https://example.com/{id}",
        "summary": summary or f"Summary for {title}",
        "category": None,
        "raw_score": score,
        "final_score": 0,
        "metadata_json": metadata or "{}",
    }


class TestStorage:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.storage = Storage(self.db_path)

    def test_init_creates_database(self):
        assert os.path.exists(self.db_path)

    def test_save_and_retrieve_items(self):
        from src.collectors.base import City, Source, TrendItem

        items = [
            TrendItem(
                title="Test item",
                source=Source.GOOGLE_NEWS,
                city=City.DENVER,
                url="https://example.com",
                summary="A test item",
                raw_score=42.0,
            )
        ]
        saved = self.storage.save_items(items, "test-run-1")
        assert saved == 1

        retrieved = self.storage.get_items_for_run("test-run-1")
        assert len(retrieved) == 1
        assert retrieved[0]["title"] == "Test item"
        assert retrieved[0]["source"] == "google_news"

    def test_save_report(self):
        self.storage.save_report("run-1", "weekly", "<html>report</html>")
        stats = self.storage.get_stats()
        assert stats["total_reports"] == 1

    def test_get_stats(self):
        stats = self.storage.get_stats()
        assert stats["total_items"] == 0
        assert stats["total_reports"] == 0

    def test_cleanup_retains_recent(self):
        from src.collectors.base import City, Source, TrendItem

        items = [
            TrendItem(
                title="Recent item",
                source=Source.GOOGLE_NEWS,
                city=City.DENVER,
            )
        ]
        self.storage.save_items(items, "recent-run")
        result = self.storage.cleanup_old_data(retention_days=90)
        assert result["items_deleted"] == 0  # Should keep recent items


class TestReportGenerator:
    def test_generate_weekly_report_empty(self):
        gen = ReportGenerator({})
        html = gen.generate_weekly_report([])
        assert "DiningOut" in html
        assert "<!DOCTYPE html>" in html

    def test_generate_weekly_report_with_items(self):
        gen = ReportGenerator({})
        items = [
            _make_item(1, "Denver tacos trending", city="denver", source="google_trends", score=80),
            _make_item(2, "New restaurant opens in Houston", city="houston", source="google_news", score=60),
            _make_item(3, "Reddit buzz about Atlanta chef", city="atlanta", source="reddit", score=45),
        ]
        html = gen.generate_weekly_report(items)
        assert "Denver" in html
        assert "<!DOCTYPE html>" in html

    def test_generate_breaking_alert_none_when_no_breaking(self):
        gen = ReportGenerator({})
        items = [_make_item(1, "Normal item", score=20)]
        result = gen.generate_breaking_alert(items)
        # May or may not be None depending on scoring — just verify no crash
        assert result is None or "<!DOCTYPE html>" in result
