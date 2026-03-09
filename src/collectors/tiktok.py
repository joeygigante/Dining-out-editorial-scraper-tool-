"""Collect trending dining content related to TikTok.

Two collection strategies that run in parallel:

1. **Direct TikTok scraping** — Uses the unofficial ``TikTokApi`` library
   (Playwright-based) to search TikTok for food/dining hashtags.  This is an
   *optional* dependency: if the library isn't installed or the scrape fails,
   the pipeline keeps running.

2. **Google-for-TikTok** — Searches Google News RSS for articles *about*
   TikTok food trends (e.g. "tiktok viral restaurant Denver").  This is free,
   requires no credentials, and catches exactly the editorial-useful content
   like "This Denver taco spot just blew up on TikTok".

Tier 2 source — all failures are logged but never crash the pipeline.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timedelta, timezone
from time import mktime
from urllib.parse import quote_plus

import feedparser
import requests
from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector, City, Source, TrendItem, is_chain_article, mentions_target_city

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional: TikTokApi (unofficial library)
# ---------------------------------------------------------------------------
try:
    from TikTokApi import TikTokApi  # type: ignore[import-untyped]

    _HAS_TIKTOK_API = True
except ImportError:
    _HAS_TIKTOK_API = False

# Google News RSS — "when:7d" restricts to past 7 days
_GOOGLE_NEWS_URL = "https://news.google.com/rss/search?q={query}+when:7d&hl=en-US&gl=US&ceid=US:en"

# City display names
_CITY_LABELS: dict[City, str] = {
    City.DENVER: "Denver",
    City.HOUSTON: "Houston",
    City.DALLAS: "Dallas",
    City.ATLANTA: "Atlanta",
}

# Google-for-TikTok query templates.  Each is searched per-city.
_GOOGLE_TIKTOK_QUERIES: list[str] = [
    "tiktok {keyword} {city}",
    "tiktok viral restaurant {city}",
    "tiktok food trend {city}",
]

# Maximum age for items (days)
_MAX_AGE_DAYS = 7


def _strip_html(text: str) -> str:
    """Strip HTML tags and decode entities from a string."""
    if not text:
        return text
    soup = BeautifulSoup(text, "html.parser")
    clean = soup.get_text(separator=" ")
    return re.sub(r"\s+", " ", clean).strip()


def _resolve_google_news_url(google_url: str) -> str:
    """Try to resolve a Google News redirect URL to the actual article URL."""
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


def _is_recent(pub_date: datetime | None, max_days: int = _MAX_AGE_DAYS) -> bool:
    """Return True if the item was published within the last max_days days."""
    if pub_date is None:
        return False  # Reject undated items
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=max_days)
    return pub_date >= cutoff


# Major cities NOT in our target list
_NON_TARGET_CITIES = {
    "new york", "nyc", "brooklyn", "manhattan",
    "los angeles", "la", "chicago", "san francisco",
    "seattle", "portland", "miami", "boston",
    "philadelphia", "phoenix", "minneapolis",
    "nashville", "detroit", "pittsburgh",
    "australia", "london", "uk", "paris", "tokyo",
}


def _is_about_non_target_city(title: str) -> bool:
    """Return True if the title is clearly about a city we don't cover."""
    title_lower = title.lower()
    target_cities = {"denver", "houston", "dallas", "atlanta", "fort worth", "texas", "colorado", "georgia"}
    has_target = any(tc in title_lower for tc in target_cities)
    if has_target:
        return False
    return any(ntc in title_lower for ntc in _NON_TARGET_CITIES)


class TikTokCollector(BaseCollector):
    """Best-effort TikTok collector with two strategies.

    Strategy 1 (direct): Uses the ``TikTokApi`` library to search TikTok
    directly.  Requires ``pip install TikTokApi`` and a working Playwright
    install.  Optionally accepts an ``ms_token`` cookie for better results.

    Strategy 2 (google): Searches Google News for articles about TikTok food
    trends.  Always available — no API key or extra install needed.
    """

    name = "tiktok"

    def collect(self, keywords: list[str], cities: list[City]) -> list[TrendItem]:
        if not self.config.get("tiktok_enabled", True):
            self.logger.info("TikTok collector disabled in config")
            return []

        items: list[TrendItem] = []

        # Strategy 1: Direct TikTok scraping (optional)
        if _HAS_TIKTOK_API and self.config.get("tiktok_direct_enabled", True):
            items.extend(self._collect_direct(keywords, cities))

        # Strategy 2: Google News search for TikTok content (always runs)
        items.extend(self._collect_google_tiktok(keywords, cities))

        self.logger.info(
            "TikTok collected %d items (%s direct API %s)",
            len(items),
            "with" if _HAS_TIKTOK_API else "without",
            "available" if _HAS_TIKTOK_API else "— install TikTokApi for direct results",
        )
        return items

    # ------------------------------------------------------------------
    # Strategy 1: Direct TikTok search via unofficial API
    # ------------------------------------------------------------------

    def _collect_direct(self, keywords: list[str], cities: list[City]) -> list[TrendItem]:
        """Search TikTok directly using the TikTokApi library."""
        items: list[TrendItem] = []
        max_results = self.config.get("tiktok_max_results", 5)
        ms_token = self.config.get("tiktok_ms_token", "")

        for city in cities:
            if city == City.NATIONAL:
                continue
            city_name = _CITY_LABELS.get(city, "")

            for kw in keywords[:10]:  # Limit queries to avoid rate-limiting
                query = f"{kw} {city_name} food"
                try:
                    results = self._search_tiktok_api(query, max_results, ms_token)
                    for r in results:
                        pub_date = r.get("published")
                        if not _is_recent(pub_date):
                            continue
                        items.append(
                            TrendItem(
                                title=r.get("title", query),
                                source=Source.TIKTOK,
                                city=city,
                                url=r.get("url"),
                                summary=r.get("description", "")[:500],
                                published=pub_date,
                                raw_score=r.get("score", 0),
                                category=kw,
                                metadata={
                                    "method": "direct_api",
                                    "keyword": kw,
                                    "views": r.get("views", 0),
                                    "likes": r.get("likes", 0),
                                    "shares": r.get("shares", 0),
                                },
                            )
                        )
                except Exception:
                    self.logger.warning(
                        "TikTok direct search failed for '%s' — falling back to Google",
                        query,
                    )

        return items

    def _search_tiktok_api(
        self, query: str, max_results: int, ms_token: str
    ) -> list[dict]:
        """Run a TikTok search via the unofficial TikTokApi library.

        Uses synchronous helpers wrapping the async library.
        Returns a simplified list of dicts.
        """
        import asyncio

        async def _do_search() -> list[dict]:
            results: list[dict] = []
            async with TikTokApi() as api:
                if ms_token:
                    await api.create_sessions(
                        ms_tokens=[ms_token],
                        num_sessions=1,
                        sleep_after=3,
                    )
                else:
                    await api.create_sessions(
                        num_sessions=1,
                        sleep_after=3,
                    )

                count = 0
                async for video in api.search.videos(query, count=max_results):
                    info = video.as_dict
                    stats = info.get("stats", {})
                    views = stats.get("playCount", 0)
                    likes = stats.get("diggCount", 0)
                    shares = stats.get("shareCount", 0)
                    author_id = info.get("author", {}).get("uniqueId", "")
                    video_id = info.get("id", "")

                    results.append(
                        {
                            "title": info.get("desc", "")[:200],
                            "description": info.get("desc", ""),
                            "url": f"https://www.tiktok.com/@{author_id}/video/{video_id}",
                            "views": views,
                            "likes": likes,
                            "shares": shares,
                            "published": (
                                datetime.fromtimestamp(
                                    info.get("createTime", 0), tz=timezone.utc
                                )
                                if info.get("createTime")
                                else None
                            ),
                            "score": _virality_score(views, likes, shares),
                        }
                    )
                    count += 1
                    if count >= max_results:
                        break
            return results

        # Run the async search in a new event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're inside an existing event loop — create a new one in a thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _do_search())
                return future.result(timeout=self.config.get("tiktok_timeout", 30))
        else:
            return asyncio.run(_do_search())

    # ------------------------------------------------------------------
    # Strategy 2: Google News search for TikTok-related articles
    # ------------------------------------------------------------------

    def _collect_google_tiktok(
        self, keywords: list[str], cities: list[City]
    ) -> list[TrendItem]:
        """Search Google News for articles about TikTok food trends.

        This catches content like:
        - "This Denver taco spot just went viral on TikTok"
        - "TikTok's favorite Houston restaurants for 2025"
        - "The TikTok fried chicken trend hits Atlanta"
        """
        items: list[TrendItem] = []
        seen_urls: set[str] = set()
        max_per_query = self.config.get("tiktok_google_max_results", 5)

        # Build search queries: combine templates x cities x keywords
        for city in cities:
            if city == City.NATIONAL:
                continue
            city_name = _CITY_LABELS.get(city, "")

            # Always search the broad viral/trend queries per city
            for template in _GOOGLE_TIKTOK_QUERIES:
                # For keyword-specific template, cycle through keywords
                if "{keyword}" in template:
                    search_keywords = keywords[:8]  # Limit to avoid hammering
                else:
                    search_keywords = [""]  # Template doesn't need a keyword

                for kw in search_keywords:
                    query_str = template.format(keyword=kw, city=city_name).strip()
                    encoded = quote_plus(query_str)
                    url = _GOOGLE_NEWS_URL.format(query=encoded)

                    try:
                        feed = feedparser.parse(url)
                        for entry in feed.entries[:max_per_query]:
                            pub_date = _parse_date(entry)
                            if not _is_recent(pub_date):
                                continue

                            title = _strip_html(entry.get("title", ""))
                            summary = _strip_html(entry.get("summary", ""))[:500]

                            # Must actually mention TikTok to be relevant
                            combined = f"{title} {summary}".lower()
                            if "tiktok" not in combined and "tik tok" not in combined:
                                continue

                            # Skip articles about non-target cities
                            if _is_about_non_target_city(title):
                                continue

                            # Skip chain restaurant articles
                            if is_chain_article(title):
                                continue

                            # Must mention a target city/region
                            if not mentions_target_city(combined):
                                continue

                            raw_url = entry.get("link", "")
                            resolved_url = _resolve_google_news_url(raw_url)

                            # Deduplicate
                            if resolved_url in seen_urls:
                                continue
                            seen_urls.add(resolved_url)

                            items.append(
                                TrendItem(
                                    title=title,
                                    source=Source.TIKTOK,
                                    city=city,
                                    url=resolved_url,
                                    summary=summary,
                                    published=pub_date,
                                    raw_score=_google_tiktok_score(title, summary),
                                    category=kw if kw else "tiktok_trend",
                                    metadata={
                                        "method": "google_news",
                                        "query": query_str,
                                        "keyword": kw,
                                    },
                                )
                            )
                    except Exception:
                        self.logger.warning(
                            "Google-for-TikTok search failed for '%s'", query_str
                        )

        return items

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """Check that at least one strategy is working."""
        # Google News is always available as fallback
        try:
            url = _GOOGLE_NEWS_URL.format(query=quote_plus("tiktok food trend"))
            feed = feedparser.parse(url)
            if feed.entries:
                return True
        except Exception:
            pass

        # Also check direct API if available
        if _HAS_TIKTOK_API:
            try:
                resp = requests.get(
                    "https://www.tiktok.com/",
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
                    },
                    timeout=10,
                )
                return resp.status_code == 200
            except Exception:
                pass

        return False


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _virality_score(views: int, likes: int, shares: int) -> float:
    """Score a TikTok video's relevance on 0-100 scale."""
    v = math.log1p(views) * 3
    l = math.log1p(likes) * 5
    s = math.log1p(shares) * 10  # Shares are the strongest signal
    return min(v + l + s, 100.0)


def _google_tiktok_score(title: str, summary: str) -> float:
    """Score a Google News article about TikTok trends on 0-100 scale.

    Higher scores for articles that are more clearly about viral TikTok food.
    """
    text = f"{title} {summary}".lower()

    score = 10.0  # Base score for any result

    # Strong signals — article is specifically about TikTok food content
    strong = ["viral", "trending", "blew up", "went viral", "tiktok famous", "million views"]
    for signal in strong:
        if signal in text:
            score += 20.0

    # Medium signals — food/dining terms
    medium = ["restaurant", "food", "chef", "dining", "opening", "best", "new"]
    for signal in medium:
        if signal in text:
            score += 5.0

    # Weak signals — general TikTok mention
    if "tiktok" in text or "tik tok" in text:
        score += 10.0

    return min(score, 100.0)


def _parse_date(entry) -> datetime | None:
    """Parse a feedparser entry's date."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        return datetime.fromtimestamp(mktime(entry.updated_parsed), tz=timezone.utc)
    return None
