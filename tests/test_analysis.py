"""Tests for analysis modules."""

import pytest

from src.analysis.scorer import (
    cluster_items,
    detect_breaking_news,
    generate_story_ideas,
    score_items,
)
from src.analysis.competitor import analyze_competitor_gaps, summarize_competitor_activity


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


class TestScorer:
    def test_score_items_empty(self):
        assert score_items([], {}) == []

    def test_score_items_normalizes(self):
        items = [
            _make_item(1, "Denver tacos trend", score=80),
            _make_item(2, "Houston steak trend", source="google_trends", score=40),
            _make_item(3, "Low relevance item", score=5),
        ]
        scored = score_items(items, {})
        assert scored[0]["final_score"] == 100.0  # Highest normalized to 100
        assert all(0 <= i["final_score"] <= 100 for i in scored)
        # Items are sorted by score descending
        assert scored[0]["final_score"] >= scored[1]["final_score"]

    def test_score_items_single_item(self):
        items = [_make_item(1, "Single item")]
        scored = score_items(items, {})
        assert len(scored) == 1
        assert scored[0]["final_score"] == 100.0


class TestClustering:
    def test_cluster_few_items(self):
        items = [_make_item(1, "Tacos in Denver", score=80)]
        clusters = cluster_items(items, {})
        assert len(clusters) == 1
        assert len(clusters[0]["items"]) == 1

    def test_cluster_multiple_items(self):
        items = [
            _make_item(1, "Best tacos in Denver RiNo neighborhood", summary="A roundup of taco spots in Denver"),
            _make_item(2, "New taco restaurant opens in Denver", summary="Taco joint in RiNo"),
            _make_item(3, "Denver birria tacos trending", summary="Birria tacos are popular"),
            _make_item(4, "Houston steak restaurant review", summary="A premium steakhouse in Houston", city="houston"),
            _make_item(5, "Houston BBQ scene growing", summary="Barbecue restaurants expand", city="houston"),
            _make_item(6, "Atlanta chef wins award", summary="James Beard finalist from Atlanta", city="atlanta"),
        ]
        clusters = cluster_items(items, {})
        assert len(clusters) >= 2
        # Each cluster should have at least one item
        assert all(len(c["items"]) > 0 for c in clusters)


class TestBreakingNews:
    def test_no_breaking_news(self):
        items = [_make_item(1, "Normal story", score=30)]
        items[0]["final_score"] = 30
        assert detect_breaking_news(items) == []

    def test_breaking_requires_multiple_sources(self):
        # Titles must share first 5 words to be grouped together
        items = [
            _make_item(1, "Big restaurant opening in Denver", source="google_news", score=90),
            _make_item(2, "Big restaurant opening in Denver announced", source="rss_feed", score=85),
        ]
        items[0]["final_score"] = 95
        items[1]["final_score"] = 90
        breaking = detect_breaking_news(items)
        assert len(breaking) >= 1


class TestStoryIdeas:
    def test_generate_ideas_from_clusters(self):
        clusters = [
            {
                "cluster_id": 0,
                "label": "tacos birria denver",
                "items": [_make_item(1, "Best Tacos in Denver", city="denver")],
                "top_score": 85,
                "cities": ["denver"],
                "sources": ["google_news", "reddit"],
            }
        ]
        ideas = generate_story_ideas(clusters, {})
        assert len(ideas) > 0
        # Headline should be the full item title (not truncated)
        assert any("Best Tacos in Denver" in i["headline"] for i in ideas)
        # Should include a URL for click-through context
        assert all(i.get("url") for i in ideas)
        # Cities should be derived from content, not cluster-wide
        assert all("denver" in i["cities"] for i in ideas)

    def test_event_intel_ideas(self):
        clusters = [
            {
                "cluster_id": 0,
                "label": "fried chicken trends",
                "items": [_make_item(1, "Fried chicken spots in Denver", city="denver")],
                "top_score": 75,
                "cities": ["denver"],
                "sources": ["google_trends"],
            }
        ]
        ideas = generate_story_ideas(clusters, {
            "event_keywords": {"fried chicken": "CHICKEN FIGHT!"}
        })
        assert any("CHICKEN FIGHT!" in i["headline"] for i in ideas)


class TestCompetitorAnalysis:
    def test_no_competitor_items(self):
        items = [_make_item(1, "Our article", metadata='{"feed_name": "DiningOut"}')]
        gaps = analyze_competitor_gaps(items)
        assert gaps == []

    def test_summarize_competitor_activity(self):
        items = [
            _make_item(1, "Eater article", metadata='{"feed_name": "Eater Denver", "is_competitor": true}'),
            _make_item(2, "Our article", metadata='{"feed_name": "DiningOut"}'),
        ]
        activity = summarize_competitor_activity(items)
        assert "Eater Denver" in activity
        assert len(activity["Eater Denver"]) == 1
