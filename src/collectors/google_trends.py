"""Collect Google Trends interest data for dining keywords by city.

Uses pytrends as the primary source with exponential backoff on rate limits.
Falls back to the Google Trends Daily Trends RSS feed when pytrends is blocked.
"""

from __future__ import annotations

import random
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

from pytrends.request import TrendReq

from src.collectors.base import (
    CITY_GEO_CODES,
    BaseCollector,
    City,
    Source,
    TrendItem,
)

# Google Trends Daily Trends RSS URL (public, no auth required)
_DAILY_TRENDS_RSS = "https://trends.google.com/trending/rss?geo={geo_country}"


def _has_word_match(text: str, signals: set[str]) -> bool:
    """Check if any signal appears as a whole word in text.

    Uses word-boundary regex to avoid false positives like
    "bar" matching inside "barreda".
    """
    for signal in signals:
        if re.search(rf"\b{re.escape(signal)}\b", text):
            return True
    return False


class GoogleTrendsCollector(BaseCollector):
    name = "google_trends"

    def __init__(self, config: dict):
        super().__init__(config)
        raw_timeout = config.get("google_trends_timeout", (10, 30))
        # YAML parses [10, 30] as a list, but urllib3 v2+ requires a tuple
        self._timeout = tuple(raw_timeout) if isinstance(raw_timeout, list) else raw_timeout
        self._retries = config.get("google_trends_retries", 3)
        self._batch_size = 5  # pytrends accepts max 5 keywords per request
        self._max_backoff_retries = config.get("google_trends_max_retries", 3)

    def collect(self, keywords: list[str], cities: list[City]) -> list[TrendItem]:
        items: list[TrendItem] = []
        timeframe = self.config.get("google_trends_timeframe", "now 7-d")
        pytrends_failed_all = True

        for city in cities:
            geo = CITY_GEO_CODES.get(city, "US")
            batches = [keywords[i : i + self._batch_size] for i in range(0, len(keywords), self._batch_size)]

            for batch in batches:
                batch_items = self._fetch_batch_with_backoff(batch, geo, city, timeframe)
                if batch_items is not None and len(batch_items) > 0:
                    items.extend(batch_items)
                    pytrends_failed_all = False

                # Be polite — Google rate-limits aggressively
                delay = self.config.get("google_trends_delay", 5)
                if delay > 0:
                    # Add jitter: ±30% randomization to avoid lockstep patterns
                    jitter = delay * 0.3 * (2 * random.random() - 1)
                    time.sleep(max(1, delay + jitter))

        # Also fetch related queries for top keywords
        top_keywords = keywords[:5]
        for city in cities:
            geo = CITY_GEO_CODES.get(city, "US")
            try:
                related = self._fetch_related_queries(top_keywords, geo, city)
                if related:
                    items.extend(related)
                    pytrends_failed_all = False
            except (Exception, SystemExit):
                self.logger.exception("Related queries failed for %s", city.value)

        # If pytrends was completely blocked, fall back to RSS daily trends
        if pytrends_failed_all:
            self.logger.warning(
                "pytrends returned no data — falling back to Google Trends RSS"
            )
            rss_items = self._fetch_daily_trends_rss(keywords, cities)
            items.extend(rss_items)

        self.logger.info("Google Trends collected %d items", len(items))
        return items

    def _build_client(self) -> TrendReq:
        return TrendReq(
            hl="en-US",
            tz=360,
            timeout=self._timeout,
            retries=self._retries,
            backoff_factor=1.0,
        )

    def _fetch_batch_with_backoff(
        self,
        keywords: list[str],
        geo: str,
        city: City,
        timeframe: str,
    ) -> Optional[list[TrendItem]]:
        """Fetch a batch with exponential backoff on failure."""
        for attempt in range(self._max_backoff_retries):
            try:
                return self._fetch_batch(keywords, geo, city, timeframe)
            except (Exception, SystemExit):
                wait = (2 ** attempt) + random.random()
                if attempt < self._max_backoff_retries - 1:
                    self.logger.warning(
                        "Google Trends attempt %d/%d failed for %s in %s — "
                        "retrying in %.1fs",
                        attempt + 1,
                        self._max_backoff_retries,
                        keywords,
                        city.value,
                        wait,
                    )
                    time.sleep(wait)
                else:
                    self.logger.error(
                        "Google Trends failed after %d attempts for %s in %s",
                        self._max_backoff_retries,
                        keywords,
                        city.value,
                    )
        return None

    def _fetch_batch(
        self,
        keywords: list[str],
        geo: str,
        city: City,
        timeframe: str,
    ) -> list[TrendItem]:
        pytrends = self._build_client()
        pytrends.build_payload(keywords, cat=71, timeframe=timeframe, geo=geo)  # cat 71 = Food & Drink

        df = pytrends.interest_over_time()
        if df.empty:
            return []

        items: list[TrendItem] = []
        for kw in keywords:
            if kw not in df.columns:
                continue
            series = df[kw]
            mean_interest = float(series.mean())
            latest = float(series.iloc[-1]) if len(series) > 0 else 0
            trend_direction = latest - mean_interest

            items.append(
                TrendItem(
                    title=f"'{kw}' trending in {city.value}",
                    source=Source.GOOGLE_TRENDS,
                    city=city,
                    summary=f"Average interest: {mean_interest:.0f}, Latest: {latest:.0f}, Change: {trend_direction:+.0f}",
                    published=datetime.now(tz=timezone.utc),
                    raw_score=latest,
                    category=kw,
                    metadata={
                        "keyword": kw,
                        "mean_interest": mean_interest,
                        "latest_interest": latest,
                        "trend_direction": trend_direction,
                        "geo": geo,
                    },
                )
            )
        return items

    def _fetch_related_queries(
        self,
        keywords: list[str],
        geo: str,
        city: City,
    ) -> list[TrendItem]:
        pytrends = self._build_client()
        pytrends.build_payload(keywords, cat=71, timeframe="now 7-d", geo=geo)
        related = pytrends.related_queries()

        items: list[TrendItem] = []
        for kw, tables in related.items():
            rising = tables.get("rising")
            if rising is None or rising.empty:
                continue
            for _, row in rising.head(5).iterrows():
                query = row.get("query", "")
                value = row.get("value", 0)
                items.append(
                    TrendItem(
                        title=f"Rising query: '{query}' (related to '{kw}')",
                        source=Source.GOOGLE_TRENDS,
                        city=city,
                        summary=f"Rising value: {value}",
                        published=datetime.now(tz=timezone.utc),
                        raw_score=min(float(value), 100),
                        category=kw,
                        metadata={
                            "type": "rising_query",
                            "parent_keyword": kw,
                            "rising_value": value,
                            "geo": geo,
                        },
                    )
                )
        return items

    # ------------------------------------------------------------------
    # RSS fallback — Google Trends Daily Trends (public, no rate limit)
    # ------------------------------------------------------------------

    def _fetch_daily_trends_rss(
        self,
        keywords: list[str],
        cities: list[City],
    ) -> list[TrendItem]:
        """Fetch Google's daily trending searches RSS and filter for dining-related topics."""
        items: list[TrendItem] = []
        keyword_set = {kw.lower() for kw in keywords}

        try:
            url = _DAILY_TRENDS_RSS.format(geo_country="US")
            req = Request(url, headers={"User-Agent": "DiningOutScraper/1.0"})
            with urlopen(req, timeout=15) as resp:
                xml_data = resp.read()

            root = ET.fromstring(xml_data)
            # Google Trends RSS uses the ht namespace
            ns = {"ht": "https://trends.google.com/trending/rss"}

            for item_el in root.findall(".//item"):
                title_el = item_el.find("title")
                if title_el is None or not title_el.text:
                    continue

                title = title_el.text.strip()
                title_lower = title.lower()

                # Check traffic volume if available
                traffic_el = item_el.find("ht:approx_traffic", ns)
                traffic_str = traffic_el.text if traffic_el is not None else "0"
                traffic = self._parse_traffic(traffic_str)

                # Check if this trending topic is food/dining related
                # Match against our keywords OR common dining terms
                # Use word-boundary matching to avoid false positives
                # (e.g. "bar" matching inside "barreda")
                dining_signals = {
                    "restaurant", "food", "chef", "dining", "eat",
                    "menu", "cook", "recipe", "kitchen", "bar",
                    "grill", "cafe", "bistro", "bakery",
                }
                all_signals = keyword_set | dining_signals

                matched = _has_word_match(title_lower, all_signals)
                if not matched:
                    # Also check the news items within the trend
                    news_titles = [
                        n.get("title", "").lower()
                        for n in item_el.findall("ht:news_item", ns)
                    ]
                    matched = any(
                        _has_word_match(nt, all_signals)
                        for nt in news_titles
                    )

                if matched:
                    # Find which keyword matched best
                    matched_kw = next(
                        (kw for kw in keywords if kw.lower() in title_lower),
                        "general dining",
                    )

                    # Assign to all cities since daily trends are national
                    for city in cities:
                        items.append(
                            TrendItem(
                                title=f"Trending: '{title}'",
                                source=Source.GOOGLE_TRENDS,
                                city=city,
                                summary=f"Google Daily Trend — approx {traffic_str} searches",
                                published=datetime.now(tz=timezone.utc),
                                raw_score=min(traffic / 10000, 100),
                                category=matched_kw,
                                metadata={
                                    "type": "daily_trend_rss",
                                    "traffic": traffic_str,
                                    "fallback": True,
                                },
                            )
                        )
        except (URLError, ET.ParseError, OSError):
            self.logger.exception("Google Trends RSS fallback also failed")

        self.logger.info("Google Trends RSS fallback found %d items", len(items))
        return items

    @staticmethod
    def _parse_traffic(traffic_str: str) -> float:
        """Parse traffic strings like '500,000+' or '2M+' into numeric values."""
        s = traffic_str.replace(",", "").replace("+", "").strip()
        if not s:
            return 0
        multiplier = 1
        if s.endswith("M"):
            multiplier = 1_000_000
            s = s[:-1]
        elif s.endswith("K"):
            multiplier = 1_000
            s = s[:-1]
        try:
            return float(s) * multiplier
        except ValueError:
            return 0

    def health_check(self) -> bool:
        try:
            pt = self._build_client()
            pt.build_payload(["restaurant"], timeframe="now 1-d", geo="US")
            df = pt.interest_over_time()
            return not df.empty
        except (Exception, SystemExit):
            return False
