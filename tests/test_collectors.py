"""Tests for collector modules."""

from unittest.mock import MagicMock, patch

import pytest

from src.collectors.base import City, Source, TrendItem
from src.collectors.news_rss import NewsRSSCollector, _detect_city
from src.collectors.google_trends import GoogleTrendsCollector
from src.collectors.reddit import RedditCollector, _engagement_score
from src.collectors.tiktok import TikTokCollector, _virality_score
from src.collectors.yelp import YelpCollector, _yelp_score


class TestTrendItem:
    def test_create_basic(self):
        item = TrendItem(
            title="Test trend",
            source=Source.GOOGLE_NEWS,
            city=City.DENVER,
        )
        assert item.title == "Test trend"
        assert item.source == Source.GOOGLE_NEWS
        assert item.city == City.DENVER
        assert item.raw_score == 0.0
        assert item.source_name == "google_news"

    def test_metadata_defaults_to_empty_dict(self):
        item = TrendItem(title="Test", source=Source.REDDIT, city=City.HOUSTON)
        assert item.metadata == {}

    def test_all_sources_exist(self):
        assert len(Source) == 6
        assert Source.GOOGLE_NEWS.value == "google_news"
        assert Source.TIKTOK.value == "tiktok"

    def test_all_cities_exist(self):
        assert len(City) == 5
        assert City.NATIONAL.value == "national"


class TestNewsRSSCollector:
    def test_detect_city_denver(self):
        assert _detect_city("Eater Denver", "New restaurant opens") == City.DENVER

    def test_detect_city_houston(self):
        assert _detect_city("Some Feed", "Houston chef wins award") == City.HOUSTON

    def test_detect_city_westword_maps_to_denver(self):
        assert _detect_city("Westword Food", "Best tacos") == City.DENVER

    def test_detect_city_unknown_returns_national(self):
        assert _detect_city("Random Feed", "Random title") == City.NATIONAL

    @patch("src.collectors.news_rss.feedparser.parse")
    def test_collect_returns_items(self, mock_parse):
        mock_entry = MagicMock()
        mock_entry.get.side_effect = lambda k, d="": {
            "title": "Denver restaurant opens",
            "link": "https://example.com",
            "summary": "A new restaurant in Denver",
        }.get(k, d)
        mock_entry.published_parsed = None
        mock_entry.updated_parsed = None

        mock_feed = MagicMock()
        mock_feed.entries = [mock_entry]
        mock_feed.bozo = False
        mock_parse.return_value = mock_feed

        collector = NewsRSSCollector({"google_news_max_results": 5})
        items = collector.collect(["restaurant"], [City.DENVER])
        assert len(items) > 0

    @patch("src.collectors.news_rss.feedparser.parse")
    def test_collect_handles_parse_error(self, mock_parse):
        mock_parse.side_effect = Exception("Network error")
        collector = NewsRSSCollector({"google_news_max_results": 5})
        # Should not raise — returns empty list
        items = collector.collect(["restaurant"], [City.DENVER])
        assert isinstance(items, list)


class TestGoogleTrendsCollector:
    @patch("src.collectors.google_trends.TrendReq")
    def test_collect_empty_results(self, mock_trendreq):
        import pandas as pd
        mock_instance = MagicMock()
        mock_instance.interest_over_time.return_value = pd.DataFrame()
        mock_instance.related_queries.return_value = {}
        mock_trendreq.return_value = mock_instance

        collector = GoogleTrendsCollector({"google_trends_delay": 0})
        items = collector.collect(["tacos"], [City.DENVER])
        assert isinstance(items, list)


class TestRedditCollector:
    def test_engagement_score(self):
        score = _engagement_score(100, 50)
        assert 0 <= score <= 100
        # More engagement = higher score
        assert _engagement_score(1000, 200) > _engagement_score(10, 2)

    def test_engagement_score_zero(self):
        assert _engagement_score(0, 0) == 0.0


class TestTikTokCollector:
    def test_virality_score(self):
        score = _virality_score(10000, 500, 100)
        assert 0 <= score <= 100

    def test_virality_score_zero(self):
        assert _virality_score(0, 0, 0) == 0.0

    def test_collect_disabled(self):
        collector = TikTokCollector({"tiktok_enabled": False})
        items = collector.collect(["tacos"], [City.DENVER])
        assert items == []


class TestYelpCollector:
    def test_yelp_score(self):
        score = _yelp_score(4.5, 200)
        assert 0 <= score <= 100

    def test_yelp_score_zero(self):
        score = _yelp_score(0, 0)
        assert score == 0.0

    def test_collect_no_api_key(self):
        collector = YelpCollector({})
        items = collector.collect(["tacos"], [City.DENVER])
        assert items == []
