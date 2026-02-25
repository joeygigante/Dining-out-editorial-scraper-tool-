from src.collectors.base import BaseCollector, TrendItem
from src.collectors.news_rss import NewsRSSCollector
from src.collectors.google_trends import GoogleTrendsCollector
from src.collectors.reddit import RedditCollector
from src.collectors.tiktok import TikTokCollector

__all__ = [
    "BaseCollector",
    "TrendItem",
    "NewsRSSCollector",
    "GoogleTrendsCollector",
    "RedditCollector",
    "TikTokCollector",
]
