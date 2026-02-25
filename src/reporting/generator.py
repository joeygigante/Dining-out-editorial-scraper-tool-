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
from src.collectors.base import City, Source

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
        """Generate the full weekly HTML report."""
        scored = score_items(items, self.config)
        clusters = cluster_items(scored, self.config)
        story_ideas = generate_story_ideas(clusters, self.config)
        breaking = detect_breaking_news(scored)
        gaps = analyze_competitor_gaps(scored)
        competitor_activity = summarize_competitor_activity(scored)

        # Organize items by city
        city_sections = self._build_city_sections(scored)

        # Extract event intelligence
        event_intel = self._extract_event_items(clusters)

        # TikTok items (separate section)
        tiktok_items = [i for i in scored if i.get("source") == Source.TIKTOK.value]

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
        """Organize scored items into city-first sections."""
        cities = [City.DENVER, City.HOUSTON, City.DALLAS, City.ATLANTA]
        sections = {}

        for city in cities:
            city_items = [i for i in items if i.get("city") == city.value]

            sections[city.value.title()] = {
                "trends": [i for i in city_items if i.get("source") == Source.GOOGLE_TRENDS.value],
                "news": [
                    i
                    for i in city_items
                    if i.get("source") in (Source.GOOGLE_NEWS.value, Source.RSS_FEED.value)
                ],
                "reddit": [i for i in city_items if i.get("source") == Source.REDDIT.value],
                "tiktok": [i for i in city_items if i.get("source") == Source.TIKTOK.value],
            }

        return sections

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
