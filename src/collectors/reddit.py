"""Collect trending dining discussions from Reddit city and food subreddits."""

from __future__ import annotations

from datetime import datetime, timezone

import praw

from src.collectors.base import (
    CITY_SUBREDDITS,
    BaseCollector,
    City,
    Source,
    TrendItem,
)

# National food subreddits to always scan
FOOD_SUBREDDITS = ["food", "FoodPorn", "restaurants", "Cooking", "AskCulinary"]


class RedditCollector(BaseCollector):
    name = "reddit"

    def __init__(self, config: dict):
        super().__init__(config)
        self._reddit: praw.Reddit | None = None

    def _get_client(self) -> praw.Reddit:
        if self._reddit is None:
            self._reddit = praw.Reddit(
                client_id=self.config["reddit_client_id"],
                client_secret=self.config["reddit_client_secret"],
                user_agent=self.config.get("reddit_user_agent", "DiningOutScraper/1.0"),
            )
        return self._reddit

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
            reddit = self._get_client()
            subreddit = reddit.subreddit(sub_name)

            for post in subreddit.hot(limit=limit):
                title_lower = post.title.lower()
                selftext_lower = (post.selftext or "")[:1000].lower()
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

                score = post.score
                comment_count = post.num_comments

                items.append(
                    TrendItem(
                        title=post.title,
                        source=Source.REDDIT,
                        city=city,
                        url=f"https://reddit.com{post.permalink}",
                        summary=(post.selftext or "")[:500],
                        published=datetime.fromtimestamp(post.created_utc, tz=timezone.utc),
                        raw_score=_engagement_score(score, comment_count),
                        metadata={
                            "subreddit": sub_name,
                            "upvotes": score,
                            "comments": comment_count,
                            "matched_keywords": matched_keywords,
                            "upvote_ratio": post.upvote_ratio,
                        },
                    )
                )
        except Exception:
            self.logger.exception("Reddit scan failed for r/%s", sub_name)

        return items

    def health_check(self) -> bool:
        try:
            reddit = self._get_client()
            # Quick check: can we reach Reddit?
            sub = reddit.subreddit("food")
            next(sub.hot(limit=1))
            return True
        except Exception:
            return False


def _engagement_score(upvotes: int, comments: int) -> float:
    """Normalize Reddit engagement to 0-100 scale.

    Combines upvotes and comments with diminishing returns.
    A post with 100 upvotes and 50 comments ≈ score 65.
    """
    import math

    up_score = math.log1p(upvotes) * 8
    comment_score = math.log1p(comments) * 12  # Comments signal strong interest
    return min(up_score + comment_score, 100.0)
