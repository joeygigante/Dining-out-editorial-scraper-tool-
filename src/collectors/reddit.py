"""Collect trending dining discussions from Reddit city and food subreddits.

Two collection strategies that run in parallel:

1. **RSS feeds** — Uses Reddit's public ``.rss`` endpoints (e.g.
   ``reddit.com/r/Denver/.rss``) which are served through a different
   infrastructure than the ``.json`` API and are less aggressively blocked
   on cloud IPs.  Falls back to the ``.json`` endpoint if RSS fails.

2. **Google-for-Reddit** — Searches Google News RSS for articles *about*
   Reddit food discussions (e.g. "reddit best restaurants Denver").  This
   catches editorial content like "Redditors' favorite Denver taco spots"
   and works from any IP.

Tier 2 source — all failures are logged but never crash the pipeline.
"""

from __future__ import annotations

import math
import re
import time
from datetime import datetime, timedelta, timezone
from time import mktime
from urllib.parse import quote_plus

import feedparser
import requests
from bs4 import BeautifulSoup

from src.collectors.base import (
    CITY_SUBREDDITS,
    BaseCollector,
    City,
    Source,
    TrendItem,
    is_chain_article,
    mentions_target_city,
)

# National food subreddits to always scan
FOOD_SUBREDDITS = ["food", "FoodPorn", "restaurants", "Cooking", "AskCulinary"]

_USER_AGENT = "DiningOutScraper/1.0 (editorial trend research; no login)"

# Google News RSS — "when:7d" restricts to past 7 days
_GOOGLE_NEWS_URL = "https://news.google.com/rss/search?q={query}+when:7d&hl=en-US&gl=US&ceid=US:en"

# City display names
_CITY_LABELS: dict[City, str] = {
    City.DENVER: "Denver",
    City.HOUSTON: "Houston",
    City.DALLAS: "Dallas",
    City.ATLANTA: "Atlanta",
}

# Google-for-Reddit query templates, searched per-city
_GOOGLE_REDDIT_QUERIES: list[str] = [
    "reddit {keyword} restaurant {city}",
    "reddit best {keyword} {city}",
    "reddit food {city} recommendation",
    "reddit restaurant recommendation {city}",
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


def _parse_date(entry) -> datetime | None:
    """Parse a feedparser entry's date."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        return datetime.fromtimestamp(mktime(entry.updated_parsed), tz=timezone.utc)
    return None


def _is_recent(pub_date: datetime | None, max_days: int = _MAX_AGE_DAYS) -> bool:
    """Return True if the item was published within the last max_days days."""
    if pub_date is None:
        return False
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=max_days)
    return pub_date >= cutoff


class RedditCollector(BaseCollector):
    """Reddit collector with two strategies: RSS feeds + Google-for-Reddit.

    Strategy 1 (RSS): Fetches subreddit RSS feeds which are less aggressively
    blocked from cloud IPs than the .json API.  Falls back to .json if needed.

    Strategy 2 (Google): Searches Google News for articles about Reddit food
    discussions.  Always available — catches editorial roundups like
    "Redditors' favorite Denver restaurants".
    """

    name = "reddit"

    def collect(self, keywords: list[str], cities: list[City]) -> list[TrendItem]:
        items: list[TrendItem] = []
        kw_lower = [k.lower() for k in keywords]

        # Strategy 1: Direct subreddit scraping via RSS (then .json fallback)
        rss_count = 0
        for city in cities:
            subs = CITY_SUBREDDITS.get(city, [])
            for sub_name in subs:
                new_items = self._scan_subreddit_rss(sub_name, city, kw_lower)
                rss_count += len(new_items)
                items.extend(new_items)

        for sub_name in FOOD_SUBREDDITS:
            new_items = self._scan_subreddit_rss(sub_name, City.NATIONAL, kw_lower)
            rss_count += len(new_items)
            items.extend(new_items)

        # Strategy 2: Google News search for Reddit content (always runs)
        google_items = self._collect_google_reddit(keywords, cities)
        items.extend(google_items)

        self.logger.info(
            "Reddit collected %d items (%d from RSS/JSON, %d from Google-for-Reddit)",
            len(items), rss_count, len(google_items),
        )
        return items

    # ------------------------------------------------------------------
    # Strategy 1: RSS feeds with .json fallback
    # ------------------------------------------------------------------

    def _scan_subreddit_rss(
        self,
        sub_name: str,
        city: City,
        keywords: list[str],
    ) -> list[TrendItem]:
        """Fetch posts from a subreddit via RSS, falling back to .json."""
        items: list[TrendItem] = []

        # Try RSS first
        posts = self._fetch_rss(sub_name)

        # Fall back to .json if RSS returned nothing
        if not posts:
            json_posts = self._fetch_json(sub_name)
            return self._process_json_posts(json_posts, sub_name, city, keywords)

        # Process RSS entries
        for entry in posts:
            title = _strip_html(entry.get("title", ""))
            if not title:
                continue

            summary = _strip_html(entry.get("summary", ""))[:1000]
            combined = f"{title} {summary}".lower()

            # Keyword matching
            matched_keywords = [kw for kw in keywords if kw in combined]

            # For city subs, keep food-adjacent posts even without keyword match
            is_city_sub = city != City.NATIONAL
            food_signals = [
                "restaurant", "food", "dining", "eat", "chef",
                "menu", "brunch", "bar", "opening", "closing", "kitchen",
            ]
            has_food_signal = any(sig in combined for sig in food_signals)

            if not matched_keywords and not (is_city_sub and has_food_signal):
                continue

            # Skip chain restaurant content
            if is_chain_article(title):
                continue

            # For national subs, require target city mention
            if not is_city_sub and not mentions_target_city(combined):
                continue

            pub_date = _parse_date(entry)
            if not _is_recent(pub_date):
                continue

            link = entry.get("link", "")

            items.append(
                TrendItem(
                    title=title,
                    source=Source.REDDIT,
                    city=city,
                    url=link,
                    summary=summary[:500],
                    published=pub_date,
                    raw_score=_rss_score(title, summary),
                    metadata={
                        "subreddit": sub_name,
                        "method": "rss",
                        "matched_keywords": matched_keywords,
                    },
                )
            )

        return items

    def _fetch_rss(self, sub_name: str) -> list[dict]:
        """Fetch a subreddit's RSS feed.

        RSS feeds use different infrastructure than .json and are
        less aggressively blocked on cloud IPs.
        """
        timeout = self.config.get("reddit_timeout", 15)
        delay = self.config.get("reddit_delay", 1.0)
        headers = {"User-Agent": _USER_AGENT}

        for base in ("https://old.reddit.com", "https://www.reddit.com"):
            url = f"{base}/r/{sub_name}/.rss"
            try:
                resp = requests.get(url, headers=headers, timeout=timeout)
                if resp.status_code == 403:
                    self.logger.debug("RSS 403 from %s for r/%s, trying next", base, sub_name)
                    continue
                resp.raise_for_status()
                time.sleep(delay)

                feed = feedparser.parse(resp.text)
                if feed.entries:
                    return [
                        {
                            "title": e.get("title", ""),
                            "summary": e.get("summary", ""),
                            "link": e.get("link", ""),
                            "published_parsed": getattr(e, "published_parsed", None),
                            "updated_parsed": getattr(e, "updated_parsed", None),
                        }
                        for e in feed.entries
                    ]
            except Exception:
                self.logger.debug("RSS fetch failed from %s for r/%s", base, sub_name)
                continue

        self.logger.debug("RSS failed for r/%s — will try .json fallback", sub_name)
        return []

    def _fetch_json(self, sub_name: str) -> list[dict]:
        """Fetch hot posts from a subreddit using the .json endpoint.

        Fallback for when RSS doesn't work.
        """
        limit = self.config.get("reddit_posts_per_sub", 25)
        params = {"limit": min(limit, 100), "raw_json": 1}
        timeout = self.config.get("reddit_timeout", 15)
        delay = self.config.get("reddit_delay", 1.0)
        headers = {"User-Agent": _USER_AGENT}

        for base in ("https://old.reddit.com", "https://www.reddit.com"):
            url = f"{base}/r/{sub_name}/hot.json"
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=timeout)
                if resp.status_code == 403:
                    self.logger.debug("JSON 403 from %s for r/%s, trying next", base, sub_name)
                    continue
                resp.raise_for_status()
                time.sleep(delay)
                data = resp.json()
                return data.get("data", {}).get("children", [])
            except Exception:
                self.logger.debug("JSON fetch failed from %s for r/%s", base, sub_name)
                continue

        self.logger.warning("Reddit blocked all endpoints for r/%s", sub_name)
        return []

    def _process_json_posts(
        self,
        posts: list[dict],
        sub_name: str,
        city: City,
        keywords: list[str],
    ) -> list[TrendItem]:
        """Process posts from the .json endpoint into TrendItems."""
        items: list[TrendItem] = []

        for post in posts:
            data = post.get("data", {})
            title = data.get("title", "")
            selftext = data.get("selftext", "")[:1000]
            combined = f"{title} {selftext}".lower()

            matched_keywords = [kw for kw in keywords if kw in combined]

            is_city_sub = city != City.NATIONAL
            food_signals = [
                "restaurant", "food", "dining", "eat", "chef",
                "menu", "brunch", "bar", "opening", "closing", "kitchen",
            ]
            has_food_signal = any(sig in combined for sig in food_signals)

            if not matched_keywords and not (is_city_sub and has_food_signal):
                continue

            if is_chain_article(title):
                continue

            if not is_city_sub and not mentions_target_city(combined):
                continue

            score = data.get("score", 0)
            comment_count = data.get("num_comments", 0)
            permalink = data.get("permalink", "")

            created_utc = data.get("created_utc", 0)
            published = (
                datetime.fromtimestamp(created_utc, tz=timezone.utc)
                if created_utc
                else None
            )

            if not _is_recent(published):
                continue

            items.append(
                TrendItem(
                    title=title,
                    source=Source.REDDIT,
                    city=city,
                    url=f"https://reddit.com{permalink}",
                    summary=selftext[:500],
                    published=published,
                    raw_score=_engagement_score(score, comment_count),
                    metadata={
                        "subreddit": sub_name,
                        "method": "json",
                        "upvotes": score,
                        "comments": comment_count,
                        "matched_keywords": matched_keywords,
                        "upvote_ratio": data.get("upvote_ratio", 0),
                    },
                )
            )

        return items

    # ------------------------------------------------------------------
    # Strategy 2: Google News search for Reddit content
    # ------------------------------------------------------------------

    def _collect_google_reddit(
        self, keywords: list[str], cities: list[City]
    ) -> list[TrendItem]:
        """Search Google News for articles about Reddit food discussions.

        Catches content like:
        - "Redditors' favorite Denver taco spots"
        - "Best restaurants in Houston according to Reddit"
        - "Reddit food recommendations Dallas"
        """
        items: list[TrendItem] = []
        seen_urls: set[str] = set()
        max_per_query = self.config.get("reddit_google_max_results", 5)

        for city in cities:
            if city == City.NATIONAL:
                continue
            city_name = _CITY_LABELS.get(city, "")

            for template in _GOOGLE_REDDIT_QUERIES:
                if "{keyword}" in template:
                    search_keywords = keywords[:6]
                else:
                    search_keywords = [""]

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
                            combined = f"{title} {summary}".lower()

                            # Must mention Reddit to be relevant
                            if "reddit" not in combined:
                                continue

                            if is_chain_article(title):
                                continue

                            if not mentions_target_city(combined):
                                continue

                            raw_url = entry.get("link", "")

                            if raw_url in seen_urls:
                                continue
                            seen_urls.add(raw_url)

                            items.append(
                                TrendItem(
                                    title=title,
                                    source=Source.REDDIT,
                                    city=city,
                                    url=raw_url,
                                    summary=summary,
                                    published=pub_date,
                                    raw_score=_google_reddit_score(title, summary),
                                    category=kw if kw else "reddit_discussion",
                                    metadata={
                                        "method": "google_news",
                                        "query": query_str,
                                        "keyword": kw,
                                    },
                                )
                            )
                    except Exception:
                        self.logger.warning(
                            "Google-for-Reddit search failed for '%s'", query_str
                        )

        return items

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """Check that at least one strategy is working."""
        # Google News is always available as fallback
        try:
            url = _GOOGLE_NEWS_URL.format(query=quote_plus("reddit food restaurant"))
            feed = feedparser.parse(url)
            if feed.entries:
                return True
        except Exception:
            pass

        # Also check RSS
        try:
            posts = self._fetch_rss("food")
            if posts:
                return True
        except Exception:
            pass

        # Last resort: .json
        try:
            posts = self._fetch_json("food")
            return len(posts) > 0
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _engagement_score(upvotes: int, comments: int) -> float:
    """Normalize Reddit engagement to 0-100 scale.

    Combines upvotes and comments with diminishing returns.
    A post with 100 upvotes and 50 comments ~ score 65.
    """
    up_score = math.log1p(upvotes) * 8
    comment_score = math.log1p(comments) * 12  # Comments signal strong interest
    return min(up_score + comment_score, 100.0)


def _rss_score(title: str, summary: str) -> float:
    """Score an RSS-sourced Reddit post on 0-100 scale.

    RSS feeds don't include upvote/comment counts, so we score
    based on content signals instead.
    """
    text = f"{title} {summary}".lower()
    score = 20.0  # Base score

    # Strong engagement signals in title
    strong = ["best", "favorite", "recommend", "top", "must try", "hidden gem"]
    for signal in strong:
        if signal in text:
            score += 15.0

    # Food/dining signals
    medium = ["restaurant", "food", "chef", "opening", "new", "review"]
    for signal in medium:
        if signal in text:
            score += 5.0

    return min(score, 100.0)


def _google_reddit_score(title: str, summary: str) -> float:
    """Score a Google News article about Reddit discussions on 0-100 scale."""
    text = f"{title} {summary}".lower()
    score = 15.0  # Base score

    # Strong signals — article is about Reddit food recommendations
    strong = ["reddit", "redditor", "recommend", "favorite", "best", "top"]
    for signal in strong:
        if signal in text:
            score += 12.0

    # Medium signals — food/dining terms
    medium = ["restaurant", "food", "chef", "dining", "opening"]
    for signal in medium:
        if signal in text:
            score += 5.0

    return min(score, 100.0)
