"""Collect restaurant trend data from Yelp Fusion API.

Tier 2 source — requires a Yelp API key (free tier: 500 calls/day).
Tracks new/trending restaurants and review activity by city.
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from src.collectors.base import BaseCollector, City, Source, TrendItem

_YELP_SEARCH_URL = "https://api.yelp.com/v3/businesses/search"

CITY_LOCATIONS = {
    City.DENVER: "Denver, CO",
    City.HOUSTON: "Houston, TX",
    City.DALLAS: "Dallas, TX",
    City.ATLANTA: "Atlanta, GA",
}


class YelpCollector(BaseCollector):
    name = "yelp"

    def collect(self, keywords: list[str], cities: list[City]) -> list[TrendItem]:
        api_key = self.config.get("yelp_api_key")
        if not api_key:
            self.logger.info("Yelp collector skipped — no API key configured")
            return []

        items: list[TrendItem] = []
        limit = self.config.get("yelp_results_per_query", 10)

        for city in cities:
            if city == City.NATIONAL:
                continue
            location = CITY_LOCATIONS.get(city)
            if not location:
                continue

            # Search for newly opened / hot restaurants
            items.extend(self._search_hot_new(api_key, location, city, limit))

            # Search for keyword-specific restaurants
            for kw in keywords[:8]:  # Limit to conserve API calls
                items.extend(self._search_keyword(api_key, kw, location, city, limit))

        self.logger.info("Yelp collected %d items", len(items))
        return items

    def _search_hot_new(
        self,
        api_key: str,
        location: str,
        city: City,
        limit: int,
    ) -> list[TrendItem]:
        """Find hot & new restaurants in a city."""
        items: list[TrendItem] = []
        try:
            params = {
                "location": location,
                "categories": "restaurants",
                "sort_by": "rating",
                "limit": limit,
                "attributes": "hot_and_new",
            }
            data = self._api_call(api_key, params)

            for biz in data.get("businesses", []):
                items.append(self._biz_to_item(biz, city, "hot_and_new"))
        except Exception:
            self.logger.exception("Yelp hot_and_new search failed for %s", location)
        return items

    def _search_keyword(
        self,
        api_key: str,
        keyword: str,
        location: str,
        city: City,
        limit: int,
    ) -> list[TrendItem]:
        """Search restaurants by keyword (e.g., 'tacos', 'fried chicken')."""
        items: list[TrendItem] = []
        try:
            params = {
                "term": keyword,
                "location": location,
                "categories": "restaurants",
                "sort_by": "review_count",
                "limit": limit,
            }
            data = self._api_call(api_key, params)

            for biz in data.get("businesses", []):
                items.append(self._biz_to_item(biz, city, keyword))
        except Exception:
            self.logger.exception("Yelp keyword search failed for '%s' in %s", keyword, location)
        return items

    def _api_call(self, api_key: str, params: dict) -> dict:
        timeout = self.config.get("yelp_timeout", 15)
        resp = requests.get(
            _YELP_SEARCH_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            params=params,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _biz_to_item(biz: dict, city: City, category: str) -> TrendItem:
        rating = biz.get("rating", 0)
        review_count = biz.get("review_count", 0)
        categories = ", ".join(c.get("title", "") for c in biz.get("categories", []))

        return TrendItem(
            title=biz.get("name", "Unknown"),
            source=Source.YELP,
            city=city,
            url=biz.get("url"),
            summary=f"{categories} — {rating}★ ({review_count} reviews)",
            published=datetime.now(tz=timezone.utc),
            raw_score=_yelp_score(rating, review_count),
            category=category,
            metadata={
                "yelp_id": biz.get("id"),
                "rating": rating,
                "review_count": review_count,
                "categories": categories,
                "price": biz.get("price", ""),
                "is_closed": biz.get("is_closed", False),
                "location": biz.get("location", {}),
            },
        )

    def health_check(self) -> bool:
        api_key = self.config.get("yelp_api_key")
        if not api_key:
            return False
        try:
            params = {"location": "Denver, CO", "categories": "restaurants", "limit": 1}
            data = self._api_call(api_key, params)
            return len(data.get("businesses", [])) > 0
        except Exception:
            return False


def _yelp_score(rating: float, review_count: int) -> float:
    """Score a Yelp business on 0-100 scale.

    High rating + high review count = high score.
    """
    import math

    rating_component = (rating / 5.0) * 50
    volume_component = min(math.log1p(review_count) * 8, 50)
    return rating_component + volume_component
