"""Report generator — turns scored/clustered data into HTML reports."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.analysis.competitor import analyze_competitor_gaps, summarize_competitor_activity
from src.analysis.scorer import (
    cluster_items,
    detect_breaking_news,
    generate_story_ideas,
    score_items,
)
from src.collectors.base import City, Source, is_chain_article

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent.parent / "templates"

EVENT_CATEGORIES = {"tacos", "steak", "fried chicken", "seafood", "cocktails"}


class ReportGenerator:
    def __init__(self, config: dict):
        self.config = config
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=True,
        )

    def generate_weekly_report(self, items: list[dict]) -> str:
        """Generate the full weekly HTML report.

        Each analysis step is wrapped so a single failure doesn't prevent
        the report from being generated and emailed.
        """
        scored = score_items(items, self.config)

        clusters = []
        try:
            clusters = cluster_items(scored, self.config)
        except Exception:
            logger.exception("Clustering failed")

        story_ideas = []
        try:
            story_ideas = generate_story_ideas(clusters, self.config)
        except Exception:
            logger.exception("Story idea generation failed")

        breaking = []
        try:
            breaking = detect_breaking_news(scored)
        except Exception:
            logger.exception("Breaking news detection failed")

        gaps = []
        try:
            gaps = analyze_competitor_gaps(scored)
        except Exception:
            logger.exception("Competitor gap analysis failed")

        competitor_activity = {}
        try:
            competitor_activity = summarize_competitor_activity(scored)
        except Exception:
            logger.exception("Competitor activity summary failed")

        # Organize items by city
        city_sections = self._build_city_sections(scored)

        # Extract event intelligence
        event_intel = self._extract_event_items(clusters)

        # TikTok items (separate section) — target cities, no chains
        target_cities = {City.DENVER.value, City.HOUSTON.value, City.DALLAS.value, City.ATLANTA.value}
        tiktok_items = [
            i for i in scored
            if i.get("source") == Source.TIKTOK.value
            and i.get("city") in target_cities
            and not is_chain_article(i.get("title", ""))
        ]
        tiktok_items = self._dedup_by_url(tiktok_items)

        # Count unique sources
        sources = {i.get("source") for i in scored}

        template = self.env.get_template("weekly_report.html")
        html = template.render(
            report_date=datetime.now(tz=timezone.utc).strftime("%B %d, %Y"),
            total_items=len(scored),
            sources_count=len(sources),
            retention_days=self.config.get("retention_days", 90),
            breaking_items=breaking,
            story_ideas=story_ideas,
            city_sections=city_sections,
            event_intel=event_intel,
            competitor_gaps=gaps,
            competitor_activity=competitor_activity,
            tiktok_items=tiktok_items,
        )

        return html

    def generate_breaking_alert(self, items: list[dict]) -> str | None:
        """Generate a mid-week breaking news alert. Returns None if nothing qualifies."""
        scored = score_items(items, self.config)
        breaking = detect_breaking_news(scored, threshold=self.config.get("breaking_threshold", 85))

        if not breaking:
            return None

        template = self.env.get_template("breaking_alert.html")
        html = template.render(
            report_date=datetime.now(tz=timezone.utc).strftime("%B %d, %Y"),
            breaking_items=breaking,
        )

        return html

    def _build_city_sections(self, items: list[dict]) -> dict:
        """Organize scored items into city-first sections with dedup."""
        cities = [City.DENVER, City.HOUSTON, City.DALLAS, City.ATLANTA]
        sections = {}

        for city in cities:
            city_items = [
                i for i in items
                if i.get("city") == city.value
                and not is_chain_article(i.get("title", ""))
            ]

            sections[city.value.title()] = {
                "trends": self._dedup_by_url(
                    [i for i in city_items if i.get("source") == Source.GOOGLE_TRENDS.value]
                ),
                "news": self._dedup_by_url(
                    [i for i in city_items if i.get("source") in (Source.GOOGLE_NEWS.value, Source.RSS_FEED.value)]
                ),
                "reddit": self._dedup_by_url(
                    [i for i in city_items if i.get("source") == Source.REDDIT.value]
                ),
                "tiktok": self._dedup_by_url(
                    [i for i in city_items if i.get("source") == Source.TIKTOK.value]
                ),
            }

        return sections

    @staticmethod
    def _dedup_by_url(items: list[dict]) -> list[dict]:
        """Remove duplicates by URL and by title similarity.

        Two articles about the same story from different outlets (e.g.
        CultureMap vs AOL) have different URLs but nearly identical titles.
        This catches both cases.
        """
        import re as _re

        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        result: list[dict] = []
        for item in items:
            url = item.get("url", "")
            title = item.get("title", "")

            # Normalize title: lowercase, strip source suffix, first 8 words
            title_norm = _re.sub(r"\s*[-–—|]\s*\S+$", "", title.lower())
            title_norm = _re.sub(r"[^a-z0-9 ]", "", title_norm).strip()
            title_key = " ".join(title_norm.split()[:8])

            if url and url in seen_urls:
                continue
            if title_key and title_key in seen_titles:
                continue

            if url:
                seen_urls.add(url)
            if title_key:
                seen_titles.add(title_key)
            result.append(item)
        return result

    def _extract_event_items(self, clusters: list[dict]) -> list[dict]:
        """Pull out cluster items related to DiningOut event categories."""
        event_items = []
        for cluster in clusters:
            label = cluster["label"].lower()
            if any(cat in label for cat in EVENT_CATEGORIES):
                event_items.append(
                    {
                        "title": cluster["label"].title(),
                        "summary": f"{len(cluster['items'])} signals from {', '.join(cluster['sources'])}",
                        "cities": cluster["cities"],
                        "final_score": cluster["top_score"],
                    }
                )
        return event_items
