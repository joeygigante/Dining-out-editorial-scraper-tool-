"""Main pipeline orchestrator.

Coordinates the full flow: collect -> store -> analyze -> report -> deliver.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from src.collectors.base import BaseCollector, City
from src.collectors.google_trends import GoogleTrendsCollector
from src.collectors.news_rss import NewsRSSCollector
from src.collectors.reddit import RedditCollector
from src.collectors.tiktok import TikTokCollector
from src.collectors.yelp import YelpCollector
from src.reporting.email_sender import EmailSender
from src.reporting.generator import ReportGenerator
from src.storage import Storage

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates a single scraper run: collect, analyze, report, deliver."""

    def __init__(self, config: dict):
        self.config = config
        self.storage = Storage(config.get("db_path", "data/trends.db"))
        self.generator = ReportGenerator(config)
        self.sender = EmailSender(config)

    def run_weekly(self) -> dict:
        """Execute the full weekly pipeline. Returns a summary dict."""
        run_id = f"weekly-{datetime.now(tz=timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        logger.info("Starting weekly run: %s", run_id)

        # Step 1: Collect from all sources
        items = self._collect_all()
        logger.info("Collected %d total items", len(items))

        # Step 2: Store raw items
        saved = self.storage.save_items(items, run_id)
        logger.info("Saved %d items to database", saved)

        # Step 3: Score, generate report
        db_items = self.storage.get_items_for_run(run_id)
        html = self.generator.generate_weekly_report(db_items)

        # Step 4: Store report
        self.storage.save_report(run_id, "weekly", html)

        # Step 5: Send email
        subject = f"DiningOut Trends — Week of {datetime.now(tz=timezone.utc).strftime('%B %d, %Y')}"
        sent = self.sender.send_report(html, subject)

        # Step 6: Cleanup old data
        cleanup = self.storage.cleanup_old_data()

        summary = {
            "run_id": run_id,
            "items_collected": len(items),
            "items_saved": saved,
            "email_sent": sent,
            "cleanup": cleanup,
        }
        logger.info("Weekly run complete: %s", summary)
        return summary

    def run_midweek_alert(self) -> dict:
        """Execute the mid-week breaking news check."""
        run_id = f"midweek-{datetime.now(tz=timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        logger.info("Starting mid-week alert check: %s", run_id)

        # Collect from fast sources only (skip Yelp/TikTok to keep it quick)
        items = self._collect_fast()
        logger.info("Collected %d items for alert check", len(items))

        saved = self.storage.save_items(items, run_id)
        db_items = self.storage.get_items_for_run(run_id)

        html = self.generator.generate_breaking_alert(db_items)

        sent = False
        if html:
            subject = f"DiningOut Breaking Alert — {datetime.now(tz=timezone.utc).strftime('%B %d')}"
            sent = self.sender.send_report(html, subject)
            self.storage.save_report(run_id, "breaking_alert", html)
            logger.info("Breaking alert sent")
        else:
            logger.info("No breaking news detected — no alert sent")

        return {
            "run_id": run_id,
            "items_collected": len(items),
            "alert_sent": sent,
        }

    def run_collect_only(self) -> dict:
        """Collect data without generating a report (for testing)."""
        run_id = f"collect-{datetime.now(tz=timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        items = self._collect_all()
        saved = self.storage.save_items(items, run_id)
        return {"run_id": run_id, "items_collected": len(items), "items_saved": saved}

    def generate_report_only(self, run_id: str | None = None) -> str:
        """Generate report from existing data (no collection)."""
        if run_id:
            items = self.storage.get_items_for_run(run_id)
        else:
            items = self.storage.get_items_by_period(days=7)
        return self.generator.generate_weekly_report(items)

    def health_check(self) -> dict:
        """Check the health of all configured collectors."""
        collectors = self._build_collectors()
        results = {}
        for c in collectors:
            try:
                results[c.name] = c.health_check()
            except Exception:
                results[c.name] = False
        results["storage"] = self.storage.get_stats()
        return results

    def _collect_all(self) -> list:
        """Collect from all enabled sources."""
        collectors = self._build_collectors()
        keywords = self.config.get("keywords", [])
        cities = [City(c) for c in self.config.get("cities", ["denver", "houston", "dallas", "atlanta"])]

        all_items = []
        for collector in collectors:
            try:
                items = collector.collect(keywords, cities)
                all_items.extend(items)
                logger.info("%s: collected %d items", collector.name, len(items))
            except Exception:
                logger.exception("Collector %s failed", collector.name)

        return all_items

    def _collect_fast(self) -> list:
        """Collect from fast sources only (RSS + Google News)."""
        keywords = self.config.get("keywords", [])
        cities = [City(c) for c in self.config.get("cities", ["denver", "houston", "dallas", "atlanta"])]

        collector = NewsRSSCollector(self.config)
        try:
            return collector.collect(keywords, cities)
        except Exception:
            logger.exception("Fast collection failed")
            return []

    def _build_collectors(self) -> list[BaseCollector]:
        """Build list of enabled collectors based on config."""
        collectors: list[BaseCollector] = [
            NewsRSSCollector(self.config),
            GoogleTrendsCollector(self.config),
        ]

        # Reddit — requires API credentials
        if self.config.get("reddit_client_id"):
            collectors.append(RedditCollector(self.config))
        else:
            logger.info("Reddit collector skipped — no credentials")

        # TikTok — Tier 2, graceful degradation
        if self.config.get("tiktok_enabled", True):
            collectors.append(TikTokCollector(self.config))

        # Yelp — Tier 2, requires API key
        if self.config.get("yelp_api_key"):
            collectors.append(YelpCollector(self.config))
        else:
            logger.info("Yelp collector skipped — no API key")

        return collectors
