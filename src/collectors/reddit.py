"""Collect trending dining discussions from Reddit city and food subreddits.

Uses Reddit's public JSON endpoints (append ``.json`` to any subreddit URL).
No API key, no OAuth, no PRAW dependency — just plain HTTP requests with a
polite User-Agent.  Rate-limited to ~1 req/sec to stay under Reddit's
unauthenticated limit.
"""

from __future__ import annotations

import math
import time
from datetime import datetime, timezone

import requests

from src.collectors.base import (
    CITY_SUBREDDITS,
    BaseCollector,
    City,
    Source,
    TrendItem,
)

# National food subreddits to always scan
FOOD_SUBREDDITS = ["food", "FoodPorn", "restaurants", "Cooking", "AskCulinary"]

_USER_AGENT = "DiningOutScraper/1.0 (editorial trend research; no login)"


class RedditCollector(BaseCollector):
    name = "reddit"

    def collect(self, keywords: list[str], cities: list[City]) -> list[TrendItem]:
        items: list[TrendItem] = []
        limit = self.config.get("reddit_posts_per_sub", 25)
        kw_lower = [k.lower() for k in keywords]

        # City-specific subreddits
        for city in cities:
            subs = CITY_SUBREDDITS.get(city, [])
            for sub_name in subs:
                items.extend(self._scan_subreddit(sub_name, city, kw_lower, limit))

        # National food subreddits
        for sub_name in FOOD_SUBREDDITS:
            items.extend(self._scan_subreddit(sub_name, City.NATIONAL, kw_lower, limit))

        self.logger.info("Reddit collected %d items", len(items))
        return items

    def _scan_subreddit(
        self,
        sub_name: str,
        city: City,
        keywords: list[str],
        limit: int,
    ) -> list[TrendItem]:
        items: list[TrendItem] = []
        try:
            posts = self._fetch_json(sub_name, limit)

            for post in posts:
                data = post.get("data", {})
                title = data.get("title", "")
                selftext = data.get("selftext", "")[:1000]
                title_lower = title.lower()
                selftext_lower = selftext.lower()
                combined = f"{title_lower} {selftext_lower}"

                matched_keywords = [kw for kw in keywords if kw in combined]

                # For city subs, keep all food-adjacent posts even without keyword match
                is_city_sub = city != City.NATIONAL
                food_signals = [
                    "restaurant",
                    "food",
                    "dining",
                    "eat",
                    "chef",
                    "menu",
                    "brunch",
                    "bar",
                    "opening",
                    "closing",
                    "kitchen",
                ]
                has_food_signal = any(sig in combined for sig in food_signals)

                if not matched_keywords and not (is_city_sub and has_food_signal):
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
                            "upvotes": score,
                            "comments": comment_count,
                            "matched_keywords": matched_keywords,
                            "upvote_ratio": data.get("upvote_ratio", 0),
                        },
                    )
                )
        except Exception:
            self.logger.exception("Reddit scan failed for r/%s", sub_name)

        return items

    def _fetch_json(self, sub_name: str, limit: int) -> list[dict]:
        """Fetch hot posts from a subreddit using the public .json endpoint.

        Tries old.reddit.com first (less aggressive bot blocking on cloud IPs),
        then falls back to www.reddit.com.
        """
        params = {"limit": min(limit, 100), "raw_json": 1}
        timeout = self.config.get("reddit_timeout", 15)
        delay = self.config.get("reddit_delay", 1.0)
        headers = {"User-Agent": _USER_AGENT}

        for base in ("https://old.reddit.com", "https://www.reddit.com"):
            url = f"{base}/r/{sub_name}/hot.json"
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=timeout)
                resp.raise_for_status()
                time.sleep(delay)
                data = resp.json()
                return data.get("data", {}).get("children", [])
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 403:
                    self.logger.debug("403 from %s for r/%s, trying next", base, sub_name)
                    continue
                raise

        # Both bases returned 403
        self.logger.warning("Reddit blocked all endpoints for r/%s", sub_name)
        return []

    def health_check(self) -> bool:
        try:
            posts = self._fetch_json("food", 1)
            return len(posts) > 0
        except Exception:
            return False


def _engagement_score(upvotes: int, comments: int) -> float:
    """Normalize Reddit engagement to 0-100 scale.

    Combines upvotes and comments with diminishing returns.
    A post with 100 upvotes and 50 comments ~ score 65.
    """
    up_score = math.log1p(upvotes) * 8
    comment_score = math.log1p(comments) * 12  # Comments signal strong interest
    return min(up_score + comment_score, 100.0)
