"""Tests for collector modules."""

from unittest.mock import MagicMock, patch

import pytest

from src.collectors.base import City, Source, TrendItem
from src.collectors.news_rss import NewsRSSCollector, _detect_city
from src.collectors.google_trends import GoogleTrendsCollector
from src.collectors.reddit import (
    RedditCollector,
    _engagement_score,
    _rss_score,
    _google_reddit_score,
)
from src.collectors.tiktok import TikTokCollector, _virality_score, _google_tiktok_score


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
        assert len(Source) == 5
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
        import time
        mock_entry = MagicMock()
        mock_entry.get.side_effect = lambda k, d="": {
            "title": "Denver restaurant opens",
            "link": "https://example.com",
            "summary": "A new restaurant in Denver",
        }.get(k, d)
        mock_entry.published_parsed = time.gmtime()  # Current time = recent
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

    @patch("src.collectors.google_trends.time.sleep")
    @patch("src.collectors.google_trends.TrendReq")
    def test_backoff_retries_then_succeeds(self, mock_trendreq, mock_sleep):
        """pytrends fails twice then succeeds on third attempt."""
        import pandas as pd

        mock_instance = MagicMock()
        # Fail twice, succeed on third
        mock_instance.interest_over_time.side_effect = [
            Exception("Rate limited"),
            Exception("Rate limited"),
            pd.DataFrame({"tacos": [50, 60, 70]}, index=pd.date_range("2024-01-01", periods=3)),
        ]
        mock_instance.related_queries.return_value = {}
        mock_trendreq.return_value = mock_instance

        collector = GoogleTrendsCollector({
            "google_trends_delay": 0,
            "google_trends_max_retries": 3,
        })
        items = collector.collect(["tacos"], [City.DENVER])
        assert any("tacos" in item.title for item in items)

    @patch("src.collectors.google_trends.time.sleep")
    @patch("src.collectors.google_trends.TrendReq")
    def test_backoff_exhausted_returns_none(self, mock_trendreq, mock_sleep):
        """All retries fail — _fetch_batch_with_backoff returns None."""
        mock_instance = MagicMock()
        mock_instance.interest_over_time.side_effect = Exception("Blocked")
        mock_instance.related_queries.side_effect = Exception("Blocked")
        mock_trendreq.return_value = mock_instance

        collector = GoogleTrendsCollector({
            "google_trends_delay": 0,
            "google_trends_max_retries": 2,
        })
        result = collector._fetch_batch_with_backoff(
            ["tacos"], "US", City.DENVER, "now 7-d"
        )
        assert result is None

    @patch("src.collectors.google_trends.urlopen")
    @patch("src.collectors.google_trends.time.sleep")
    @patch("src.collectors.google_trends.TrendReq")
    def test_rss_fallback_on_total_failure(self, mock_trendreq, mock_sleep, mock_urlopen):
        """When pytrends is completely blocked, RSS fallback kicks in."""
        mock_instance = MagicMock()
        mock_instance.interest_over_time.side_effect = Exception("Blocked")
        mock_instance.related_queries.side_effect = Exception("Blocked")
        mock_trendreq.return_value = mock_instance

        # Mock RSS response with a food-related trend
        rss_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:ht="https://trends.google.com/trending/rss">
          <channel>
            <item>
              <title>New Taco Restaurant Chain</title>
              <ht:approx_traffic>500,000+</ht:approx_traffic>
            </item>
            <item>
              <title>Unrelated Sports News</title>
              <ht:approx_traffic>1,000,000+</ht:approx_traffic>
            </item>
          </channel>
        </rss>"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = rss_xml
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        collector = GoogleTrendsCollector({
            "google_trends_delay": 0,
            "google_trends_max_retries": 1,
        })
        items = collector.collect(["tacos"], [City.DENVER])
        # Should have the taco trend from RSS, not the sports one
        assert len(items) > 0
        assert any("Taco" in item.title for item in items)
        assert all(item.metadata.get("fallback") is True for item in items)

    def test_parse_traffic(self):
        collector = GoogleTrendsCollector({"google_trends_delay": 0})
        assert collector._parse_traffic("500,000+") == 500_000
        assert collector._parse_traffic("2M+") == 2_000_000
        assert collector._parse_traffic("10K+") == 10_000
        assert collector._parse_traffic("") == 0
        assert collector._parse_traffic("not a number") == 0


class TestRedditCollector:
    def test_engagement_score(self):
        score = _engagement_score(100, 50)
        assert 0 <= score <= 100
        # More engagement = higher score
        assert _engagement_score(1000, 200) > _engagement_score(10, 2)

    def test_engagement_score_zero(self):
        assert _engagement_score(0, 0) == 0.0

    def test_rss_score_high_signals(self):
        score = _rss_score(
            "Best new restaurant in Denver",
            "A hidden gem with great food",
        )
        # "best", "restaurant", "food", "new" all present
        assert score >= 40.0

    def test_rss_score_baseline(self):
        score = _rss_score("Random post", "Nothing relevant")
        # Only gets base 20 points
        assert score == 20.0

    def test_rss_score_cap(self):
        score = _rss_score(
            "Best favorite recommend top must try hidden gem",
            "restaurant food chef opening new review",
        )
        assert score <= 100.0

    def test_google_reddit_score_high(self):
        score = _google_reddit_score(
            "Redditors recommend the best Denver restaurants",
            "Top food picks from Reddit",
        )
        assert score >= 40.0

    def test_google_reddit_score_baseline(self):
        score = _google_reddit_score("Unrelated article", "No signals")
        assert score == 15.0

    @patch("src.collectors.reddit.feedparser.parse")
    def test_google_reddit_returns_items(self, mock_parse):
        import time
        mock_entry = MagicMock()
        mock_entry.get.side_effect = lambda k, d="": {
            "title": "Best Denver restaurants according to Reddit",
            "link": "https://example.com/article",
            "summary": "Reddit users share their favorite Denver food spots",
        }.get(k, d)
        mock_entry.published_parsed = time.gmtime()
        mock_entry.updated_parsed = None

        mock_feed = MagicMock()
        mock_feed.entries = [mock_entry]
        mock_parse.return_value = mock_feed

        collector = RedditCollector({"reddit_google_max_results": 5})
        # Call the Google-for-Reddit method directly
        items = collector._collect_google_reddit(["tacos"], [City.DENVER])
        assert len(items) > 0
        assert all(i.metadata.get("method") == "google_news" for i in items)

    @patch("src.collectors.reddit.feedparser.parse")
    def test_google_reddit_handles_error(self, mock_parse):
        mock_parse.side_effect = Exception("Network error")
        collector = RedditCollector({"reddit_google_max_results": 5})
        items = collector._collect_google_reddit(["tacos"], [City.DENVER])
        assert isinstance(items, list)


class TestTikTokCollector:
    def test_virality_score(self):
        score = _virality_score(10000, 500, 100)
        assert 0 <= score <= 100

    def test_virality_score_zero(self):
        assert _virality_score(0, 0, 0) == 0.0

    def test_google_tiktok_score_viral(self):
        score = _google_tiktok_score(
            "This Denver taco spot went viral on TikTok",
            "The restaurant gained millions of views",
        )
        # Should score high — "viral", "tiktok", "restaurant" all present
        assert score >= 40.0

    def test_google_tiktok_score_baseline(self):
        score = _google_tiktok_score("Unrelated article", "No relevant terms")
        # Should be low — only gets the base 10 points
        assert score == 10.0

    def test_google_tiktok_score_cap(self):
        # Even with every signal, should cap at 100
        score = _google_tiktok_score(
            "viral trending blew up went viral tiktok famous million views tiktok",
            "restaurant food chef dining opening best new tiktok",
        )
        assert score <= 100.0

    def test_collect_disabled(self):
        collector = TikTokCollector({"tiktok_enabled": False})
        items = collector.collect(["tacos"], [City.DENVER])
        assert items == []

    @patch("src.collectors.tiktok.feedparser.parse")
    def test_google_tiktok_returns_items(self, mock_parse):
        import time
        mock_entry = MagicMock()
        mock_entry.get.side_effect = lambda k, d="": {
            "title": "Denver restaurant goes viral on TikTok",
            "link": "https://example.com/article",
            "summary": "A taco spot in Denver blew up on TikTok this week",
        }.get(k, d)
        mock_entry.published_parsed = time.gmtime()  # Current time = recent
        mock_entry.updated_parsed = None

        mock_feed = MagicMock()
        mock_feed.entries = [mock_entry]
        mock_parse.return_value = mock_feed

        collector = TikTokCollector({
            "tiktok_enabled": True,
            "tiktok_direct_enabled": False,  # Skip direct API
            "tiktok_google_max_results": 5,
        })
        items = collector.collect(["tacos"], [City.DENVER])
        assert len(items) > 0
        # All items should use the google_news method
        assert all(i.metadata.get("method") == "google_news" for i in items)

    @patch("src.collectors.tiktok.feedparser.parse")
    def test_google_tiktok_handles_error(self, mock_parse):
        mock_parse.side_effect = Exception("Network error")
        collector = TikTokCollector({
            "tiktok_enabled": True,
            "tiktok_direct_enabled": False,
            "tiktok_google_max_results": 5,
        })
        # Should not raise — returns empty list
        items = collector.collect(["tacos"], [City.DENVER])
        assert isinstance(items, list)
