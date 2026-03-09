"""Collect trending dining/food articles from Google News and publication RSS feeds."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from time import mktime
from urllib.parse import quote_plus

import feedparser
import requests
from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector, City, Source, TrendItem, is_chain_article

# Google News RSS search template — free, no API key needed
# "when:7d" restricts results to the past 7 days
_GOOGLE_NEWS_URL = "https://news.google.com/rss/search?q={query}+when:7d&hl=en-US&gl=US&ceid=US:en"

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
    "D Magazine Food": "https://www.dmagazine.com/publications/d-magazine/rss/",
    "Houstonia Food": "https://www.houstoniamag.com/feed/rss/",
    "Atlanta Magazine": "https://www.atlantamagazine.com/feed/",
    "The Infatuation": "https://www.theinfatuation.com/rss",
    "Infatuation Denver": "https://www.theinfatuation.com/denver/rss",
    "Infatuation Houston": "https://www.theinfatuation.com/houston/rss",
    "Infatuation Dallas": "https://www.theinfatuation.com/dallas-fort-worth/rss",
    "Infatuation Atlanta": "https://www.theinfatuation.com/atlanta/rss",
}

# Map publication names to cities for automatic tagging
_FEED_CITY_MAP: dict[str, City] = {
    "Denver": City.DENVER,
    "Houston": City.HOUSTON,
    "Dallas": City.DALLAS,
    "Atlanta": City.ATLANTA,
    "Westword": City.DENVER,
    "5280": City.DENVER,
    "D Magazine": City.DALLAS,
    "Houstonia": City.HOUSTON,
    "Atlanta Magazine": City.ATLANTA,
    "Infatuation Denver": City.DENVER,
    "Infatuation Houston": City.HOUSTON,
    "Infatuation Dallas": City.DALLAS,
    "Infatuation Atlanta": City.ATLANTA,
    # Geographic terms for cross-checking article titles
    "Colorado": City.DENVER,
    "Texas": City.DALLAS,
    "North Texas": City.DALLAS,
    "Fort Worth": City.DALLAS,
    "DFW": City.DALLAS,
    "Georgia": City.ATLANTA,
}

# Maximum age for items (days)
_MAX_AGE_DAYS = 7


# Major cities NOT in our target list — if an article title mentions these
# but NOT one of our cities, it's probably not relevant.
_NON_TARGET_CITIES = {
    "new york", "nyc", "brooklyn", "manhattan",
    "los angeles", "la", "chicago", "san francisco",
    "seattle", "portland", "miami", "boston",
    "philadelphia", "phoenix", "minneapolis",
    "nashville", "detroit", "pittsburgh",
    "australia", "london", "uk", "paris", "tokyo",
}


def _detect_city(feed_name: str, title: str) -> City:
    """Guess which city a feed entry belongs to."""
    text = f"{feed_name} {title}".lower()
    for label, city in _FEED_CITY_MAP.items():
        if label.lower() in text:
            return city
    return City.NATIONAL


def _is_about_non_target_city(title: str) -> bool:
    """Return True if the title is clearly about a city we don't cover."""
    title_lower = title.lower()
    # Check if any target city is mentioned
    target_cities = {"denver", "houston", "dallas", "atlanta", "fort worth", "texas", "colorado", "georgia"}
    has_target = any(tc in title_lower for tc in target_cities)
    if has_target:
        return False
    # Check if a non-target city is mentioned
    return any(ntc in title_lower for ntc in _NON_TARGET_CITIES)


def _parse_date(entry) -> datetime | None:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        return datetime.fromtimestamp(mktime(entry.updated_parsed), tz=timezone.utc)
    return None


def _is_recent(pub_date: datetime | None, max_days: int = _MAX_AGE_DAYS) -> bool:
    """Return True if the item was published within the last max_days days."""
    if pub_date is None:
        return False  # Reject undated items — we only want fresh content
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=max_days)
    return pub_date >= cutoff


def _strip_html(text: str) -> str:
    """Strip HTML tags and decode entities from a string."""
    if not text:
        return text
    soup = BeautifulSoup(text, "html.parser")
    clean = soup.get_text(separator=" ")
    # Collapse multiple whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _resolve_google_news_url(google_url: str) -> str:
    """Try to resolve a Google News redirect URL to the actual article URL.

    Falls back to the original URL if resolution fails.
    """
    if not google_url or "news.google.com" not in google_url:
        return google_url
    try:
        resp = requests.head(
            google_url,
            allow_redirects=True,
            timeout=5,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.url and "news.google.com" not in resp.url:
            return resp.url
    except Exception:
        pass
    return google_url


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
        seen_urls: set[str] = set()
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
                        pub_date = _parse_date(entry)
                        if not _is_recent(pub_date):
                            continue

                        title = _strip_html(entry.get("title", ""))

                        # Skip articles clearly about cities we don't cover
                        if _is_about_non_target_city(title):
                            continue

                        # Skip chain restaurant articles (DiningOut = independent restaurants)
                        if is_chain_article(title):
                            continue

                        raw_url = entry.get("link", "")
                        resolved_url = _resolve_google_news_url(raw_url)

                        # Deduplicate by URL
                        if resolved_url in seen_urls:
                            continue
                        seen_urls.add(resolved_url)

                        clean_summary = _strip_html(entry.get("summary", ""))

                        # Cross-check city: if another target city is named
                        # in the title but not the search city, reassign
                        actual_city = _detect_city("", title)
                        if actual_city != City.NATIONAL:
                            assigned_city = actual_city
                        else:
                            assigned_city = city

                        items.append(
                            TrendItem(
                                title=title,
                                source=Source.GOOGLE_NEWS,
                                city=assigned_city,
                                url=resolved_url,
                                summary=clean_summary[:500],
                                published=pub_date,
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
        seen_urls: set[str] = set()

        kw_lower = [k.lower() for k in keywords]

        for feed_name, feed_url in feeds.items():
            try:
                feed = feedparser.parse(feed_url)
                if feed.bozo and not feed.entries:
                    self.logger.warning("Feed %s returned an error: %s", feed_name, feed.bozo_exception)
                    continue

                for entry in feed.entries:
                    pub_date = _parse_date(entry)
                    if not _is_recent(pub_date):
                        continue

                    title = entry.get("title", "")
                    raw_summary = entry.get("summary", "")[:500]
                    clean_summary = _strip_html(raw_summary)
                    text = f"{title} {clean_summary}".lower()

                    # Keep entries that match any keyword, or keep all competitor entries
                    is_competitor = any(
                        comp in feed_name.lower()
                        for comp in (
                            "eater", "westword", "5280", "d magazine",
                            "houstonia", "atlanta magazine", "bon appetit",
                            "infatuation",
                        )
                    )
                    matches_keyword = any(kw in text for kw in kw_lower)

                    if not (matches_keyword or is_competitor):
                        continue

                    entry_url = entry.get("link", "")
                    if entry_url in seen_urls:
                        continue
                    seen_urls.add(entry_url)

                    items.append(
                        TrendItem(
                            title=title,
                            source=Source.RSS_FEED,
                            city=_detect_city(feed_name, title),
                            url=entry_url,
                            summary=clean_summary,
                            published=pub_date,
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
