"""Collect Google Trends interest data for dining keywords by city."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from pytrends.request import TrendReq

from src.collectors.base import (
    CITY_GEO_CODES,
    BaseCollector,
    City,
    Source,
    TrendItem,
)


class GoogleTrendsCollector(BaseCollector):
    name = "google_trends"

    def __init__(self, config: dict):
        super().__init__(config)
        raw_timeout = config.get("google_trends_timeout", (10, 30))
        # YAML parses [10, 30] as a list, but urllib3 v2+ requires a tuple
        self._timeout = tuple(raw_timeout) if isinstance(raw_timeout, list) else raw_timeout
        self._retries = config.get("google_trends_retries", 3)
        self._batch_size = 5  # pytrends accepts max 5 keywords per request

    def collect(self, keywords: list[str], cities: list[City]) -> list[TrendItem]:
        items: list[TrendItem] = []
        timeframe = self.config.get("google_trends_timeframe", "now 7-d")

        for city in cities:
            geo = CITY_GEO_CODES.get(city, "US")
            batches = [keywords[i : i + self._batch_size] for i in range(0, len(keywords), self._batch_size)]

            for batch in batches:
                try:
                    batch_items = self._fetch_batch(batch, geo, city, timeframe)
                    items.extend(batch_items)
                except (Exception, SystemExit):
                    self.logger.exception("Google Trends failed for %s in %s", batch, city.value)

                # Be polite — Google rate-limits aggressively
                time.sleep(self.config.get("google_trends_delay", 2))

        # Also fetch related queries for top keywords
        top_keywords = keywords[:5]
        for city in cities:
            geo = CITY_GEO_CODES.get(city, "US")
            try:
                related = self._fetch_related_queries(top_keywords, geo, city)
                items.extend(related)
            except (Exception, SystemExit):
                self.logger.exception("Related queries failed for %s", city.value)

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

    def health_check(self) -> bool:
        try:
            pt = self._build_client()
            pt.build_payload(["restaurant"], timeframe="now 1-d", geo="US")
            df = pt.interest_over_time()
            return not df.empty
        except (Exception, SystemExit):
            return False
