"""Base collector interface and shared data model."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


logger = logging.getLogger(__name__)


class Source(str, Enum):
    GOOGLE_NEWS = "google_news"
    RSS_FEED = "rss_feed"
    GOOGLE_TRENDS = "google_trends"
    REDDIT = "reddit"
    TIKTOK = "tiktok"


class City(str, Enum):
    DENVER = "denver"
    HOUSTON = "houston"
    DALLAS = "dallas"
    ATLANTA = "atlanta"
    NATIONAL = "national"


# Google Trends geo codes for DMA (Designated Market Area)
CITY_GEO_CODES = {
    City.DENVER: "US-CO-751",
    City.HOUSTON: "US-TX-618",
    City.DALLAS: "US-TX-623",
    City.ATLANTA: "US-GA-524",
    City.NATIONAL: "US",
}

# Reddit city subreddits
CITY_SUBREDDITS = {
    City.DENVER: ["Denver", "denverfood"],
    City.HOUSTON: ["houston", "HoustonFood"],
    City.DALLAS: ["Dallas", "dallasfood"],
    City.ATLANTA: ["Atlanta", "atlantaeats"],
}


@dataclass
class TrendItem:
    """A single trend signal collected from any source."""

    title: str
    source: Source
    city: City
    url: Optional[str] = None
    summary: Optional[str] = None
    category: Optional[str] = None  # e.g. "tacos", "openings", "chef"
    published: Optional[datetime] = None
    collected_at: datetime = field(default_factory=datetime.utcnow)
    raw_score: float = 0.0  # Source-specific relevance signal
    metadata: dict = field(default_factory=dict)

    @property
    def source_name(self) -> str:
        return self.source.value


class BaseCollector(ABC):
    """Interface that every data-source collector must implement."""

    name: str = "base"

    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger(f"collector.{self.name}")

    @abstractmethod
    def collect(self, keywords: list[str], cities: list[City]) -> list[TrendItem]:
        """Collect trend items for the given keywords and cities.

        Must not raise — log errors and return partial results.
        """

    def health_check(self) -> bool:
        """Return True if this collector's data source is reachable."""
        return True
