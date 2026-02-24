"""Collect trending dining content from TikTok.

Tier 2 source — uses unofficial methods with graceful degradation.
If TikTok collection fails, the rest of the pipeline continues unaffected.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import requests

from src.collectors.base import BaseCollector, City, Source, TrendItem

# Unofficial TikTok web API endpoint for search
_TIKTOK_SEARCH_URL = "https://www.tiktok.com/api/search/general/full/"

_TIKTOK_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.tiktok.com/",
}


class TikTokCollector(BaseCollector):
    """Best-effort TikTok collector.

    This uses TikTok's unofficial web API which can break at any time.
    All methods are wrapped in try/except so failures are logged but
    never crash the pipeline.
    """

    name = "tiktok"

    def collect(self, keywords: list[str], cities: list[City]) -> list[TrendItem]:
        if not self.config.get("tiktok_enabled", True):
            self.logger.info("TikTok collector disabled in config")
            return []

        items: list[TrendItem] = []
        city_labels = {
            City.DENVER: "Denver",
            City.HOUSTON: "Houston",
            City.DALLAS: "Dallas",
            City.ATLANTA: "Atlanta",
        }
        max_results = self.config.get("tiktok_max_results", 5)

        for city in cities:
            if city == City.NATIONAL:
                continue
            city_name = city_labels.get(city, "")
            for kw in keywords[:10]:  # Limit queries to avoid rate limiting
                query = f"{kw} {city_name} food"
                try:
                    results = self._search(query, max_results)
                    for r in results:
                        items.append(
                            TrendItem(
                                title=r.get("title", query),
                                source=Source.TIKTOK,
                                city=city,
                                url=r.get("url"),
                                summary=r.get("description", "")[:500],
                                published=r.get("published"),
                                raw_score=r.get("score", 0),
                                category=kw,
                                metadata={
                                    "keyword": kw,
                                    "views": r.get("views", 0),
                                    "likes": r.get("likes", 0),
                                    "shares": r.get("shares", 0),
                                },
                            )
                        )
                except Exception:
                    self.logger.warning(
                        "TikTok search failed for '%s' — this is expected if the API changed",
                        query,
                    )

        self.logger.info("TikTok collected %d items (best-effort)", len(items))
        return items

    def _search(self, query: str, max_results: int) -> list[dict]:
        """Search TikTok via the unofficial web API.

        Returns a simplified list of dicts with title, url, description,
        views, likes, shares, published, score.
        """
        params = {
            "keyword": query,
            "offset": 0,
            "count": max_results,
            "search_source": "normal_search",
        }
        timeout = self.config.get("tiktok_timeout", 15)

        resp = requests.get(
            _TIKTOK_SEARCH_URL,
            params=params,
            headers=_TIKTOK_HEADERS,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("data", []):
            item_info = item.get("item", {})
            if not item_info:
                continue
            stats = item_info.get("stats", {})
            views = stats.get("playCount", 0)
            likes = stats.get("diggCount", 0)
            shares = stats.get("shareCount", 0)

            results.append(
                {
                    "title": item_info.get("desc", "")[:200],
                    "description": item_info.get("desc", ""),
                    "url": f"https://www.tiktok.com/@{item_info.get('author', {}).get('uniqueId', '')}/video/{item_info.get('id', '')}",
                    "views": views,
                    "likes": likes,
                    "shares": shares,
                    "published": datetime.fromtimestamp(
                        item_info.get("createTime", 0), tz=timezone.utc
                    )
                    if item_info.get("createTime")
                    else None,
                    "score": _virality_score(views, likes, shares),
                }
            )

        return results

    def health_check(self) -> bool:
        try:
            resp = requests.get(
                "https://www.tiktok.com/",
                headers=_TIKTOK_HEADERS,
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False


def _virality_score(views: int, likes: int, shares: int) -> float:
    """Score a TikTok video's relevance on 0-100 scale."""
    import math

    v = math.log1p(views) * 3
    l = math.log1p(likes) * 5
    s = math.log1p(shares) * 10  # Shares are the strongest signal
    return min(v + l + s, 100.0)
