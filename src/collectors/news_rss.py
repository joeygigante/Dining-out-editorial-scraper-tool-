"""Collect trending dining/food articles from Google News and publication RSS feeds."""

from __future__ import annotations

from datetime import datetime, timezone
from time import mktime
from urllib.parse import quote_plus

import feedparser

from src.collectors.base import BaseCollector, City, Source, TrendItem

# Google News RSS search template — free, no API key needed
_GOOGLE_NEWS_URL = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

# Default publication feeds (can be overridden in config)
DEFAULT_FEEDS: dict[str, str] = {
    "Eater Denver": "https://denver.eater.com/rss/index.xml",
    "Eater Houston": "https://houston.eater.com/rss/index.xml",
    "Eater Dallas": "https://dallas.eater.com/rss/index.xml",
    "Eater Atlanta": "https://atlanta.eater.com/rss/index.xml",
    "Eater National": "https://www.eater.com/rss/index.xml",
    "Bon Appetit": "https://www.bonappetit.com/feed/rss",
    "Westword Food": "https://www.westword.com/restaurants/rss",
    "5280 Food": "https://www.5280.com/feed/",
}

# Map publication names to cities for automatic tagging
_FEED_CITY_MAP: dict[str, City] = {
    "Denver": City.DENVER,
    "Houston": City.HOUSTON,
    "Dallas": City.DALLAS,
    "Atlanta": City.ATLANTA,
    "Westword": City.DENVER,
    "5280": City.DENVER,
}


def _detect_city(feed_name: str, title: str) -> City:
    """Guess which city a feed entry belongs to."""
    text = f"{feed_name} {title}".lower()
    for label, city in _FEED_CITY_MAP.items():
        if label.lower() in text:
            return city
    return City.NATIONAL


def _parse_date(entry) -> datetime | None:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        return datetime.fromtimestamp(mktime(entry.updated_parsed), tz=timezone.utc)
    return None


class NewsRSSCollector(BaseCollector):
    name = "news_rss"

    def collect(self, keywords: list[str], cities: list[City]) -> list[TrendItem]:
        items: list[TrendItem] = []

        # 1. Google News keyword searches (city-scoped)
        items.extend(self._collect_google_news(keywords, cities))

        # 2. Publication RSS feeds
        items.extend(self._collect_publication_feeds(keywords))

        self.logger.info("NewsRSS collected %d items", len(items))
        return items

    # ------------------------------------------------------------------
    # Google News
    # ------------------------------------------------------------------

    def _collect_google_news(self, keywords: list[str], cities: list[City]) -> list[TrendItem]:
        items: list[TrendItem] = []
        city_names = {
            City.DENVER: "Denver",
            City.HOUSTON: "Houston",
            City.DALLAS: "Dallas",
            City.ATLANTA: "Atlanta",
        }
        max_per_query = self.config.get("google_news_max_results", 10)

        for city in cities:
            if city == City.NATIONAL:
                continue
            city_label = city_names.get(city, "")
            for kw in keywords:
                query = quote_plus(f"{kw} {city_label} restaurant")
                url = _GOOGLE_NEWS_URL.format(query=query)
                try:
                    feed = feedparser.parse(url)
                    for entry in feed.entries[:max_per_query]:
                        items.append(
                            TrendItem(
                                title=entry.get("title", ""),
                                source=Source.GOOGLE_NEWS,
                                city=city,
                                url=entry.get("link"),
                                summary=entry.get("summary", "")[:500],
                                published=_parse_date(entry),
                                raw_score=1.0,
                                metadata={"keyword": kw, "query": query},
                            )
                        )
                except Exception:
                    self.logger.exception("Google News fetch failed for %s %s", kw, city_label)
        return items

    # ------------------------------------------------------------------
    # Publication RSS
    # ------------------------------------------------------------------

    def _collect_publication_feeds(self, keywords: list[str]) -> list[TrendItem]:
        feeds: dict[str, str] = self.config.get("rss_feeds", DEFAULT_FEEDS)
        items: list[TrendItem] = []

        kw_lower = [k.lower() for k in keywords]

        for feed_name, feed_url in feeds.items():
            try:
                feed = feedparser.parse(feed_url)
                if feed.bozo and not feed.entries:
                    self.logger.warning("Feed %s returned an error: %s", feed_name, feed.bozo_exception)
                    continue

                for entry in feed.entries:
                    title = entry.get("title", "")
                    summary = entry.get("summary", "")[:500]
                    text = f"{title} {summary}".lower()

                    # Keep entries that match any keyword, or keep all competitor entries
                    is_competitor = any(
                        comp in feed_name.lower()
                        for comp in ("eater", "westword", "5280", "d magazine", "houstonia", "atlanta magazine")
                    )
                    matches_keyword = any(kw in text for kw in kw_lower)

                    if not (matches_keyword or is_competitor):
                        continue

                    items.append(
                        TrendItem(
                            title=title,
                            source=Source.RSS_FEED,
                            city=_detect_city(feed_name, title),
                            url=entry.get("link"),
                            summary=summary,
                            published=_parse_date(entry),
                            raw_score=1.5 if matches_keyword else 0.5,
                            metadata={
                                "feed_name": feed_name,
                                "is_competitor": is_competitor,
                            },
                        )
                    )
            except Exception:
                self.logger.exception("RSS feed fetch failed for %s", feed_name)

        return items

    def health_check(self) -> bool:
        try:
            feed = feedparser.parse(_GOOGLE_NEWS_URL.format(query="restaurant"))
            return len(feed.entries) > 0
        except Exception:
            return False
