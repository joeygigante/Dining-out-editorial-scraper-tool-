"""Base collector interface and shared data model."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
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


# ---------------------------------------------------------------------------
# Chain restaurant brands to filter (DiningOut focuses on independent restaurants)
# ---------------------------------------------------------------------------
CHAIN_RESTAURANTS = {
    "mcdonald", "burger king", "wendy's", "wendys", "taco bell",
    "taco cabana", "chipotle", "chili's", "chilis", "olive garden",
    "applebee", "texas roadhouse", "outback steakhouse", "longhorn steakhouse",
    "red lobster", "cracker barrel", "denny's", "dennys", "ihop",
    "waffle house", "buffalo wild wings", "wingstop", "popeye",
    "chick-fil-a", "chickfila", "panda express", "five guys",
    "shake shack", "in-n-out", "whataburger", "starbucks", "dunkin",
    "panera", "subway", "domino's", "dominos", "pizza hut", "papa john",
    "little caesars", "jack in the box", "sonic drive", "arby's", "arbys",
    "raising cane", "sweetgreen", "noodles & company",
    "cheesecake factory", "ruth's chris", "ruths chris",
    "p.f. chang", "pf chang", "golden corral", "bob evans",
}


def is_chain_article(title: str) -> bool:
    """Return True if the title is primarily about a chain restaurant."""
    t = title.lower()
    return any(chain in t for chain in CHAIN_RESTAURANTS)


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
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
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
