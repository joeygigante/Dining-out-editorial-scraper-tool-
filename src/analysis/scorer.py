"""Scoring, ranking, and clustering engine for collected trend items.

Uses TF-IDF to find emerging topics across all collected text, then
combines source-specific signals into a final composite score.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.collectors.base import City, Source, is_chain_article

logger = logging.getLogger(__name__)

# Weights for different source types when computing final score
SOURCE_WEIGHTS: dict[str, float] = {
    Source.GOOGLE_NEWS.value: 1.0,
    Source.RSS_FEED.value: 0.8,
    Source.GOOGLE_TRENDS.value: 1.2,
    Source.REDDIT.value: 0.9,
    Source.TIKTOK.value: 0.7,
}

# Food-journalism boilerplate + HTML artifacts to filter out of TF-IDF
STOP_WORDS = [
    "restaurant", "restaurants", "food", "dining", "new", "best",
    "chef", "menu", "eat", "eating", "dish", "dishes", "recipe",
    "recipes", "cook", "cooking", "meal", "meals", "review",
    "according", "also", "said", "year", "week", "time", "like",
    # HTML artifacts that leak through RSS summaries
    "nbsp", "amp", "quot", "font", "color", "href", "http", "https",
    "www", "com", "html", "target", "blank", "div", "span", "style",
]


def score_items(items: list[dict], config: dict) -> list[dict]:
    """Score and rank a list of trend items.

    Takes raw DB rows (dicts) and returns them with `final_score` populated.
    """
    if not items:
        return items

    # Parse metadata_json into a usable dict for templates and downstream code
    for item in items:
        if "metadata" not in item and "metadata_json" in item:
            try:
                item["metadata"] = json.loads(item["metadata_json"] or "{}")
            except (json.JSONDecodeError, TypeError):
                item["metadata"] = {}

    # Step 1: TF-IDF relevance
    tfidf_scores = _compute_tfidf_scores(items, config)

    # Step 2: Composite score
    for item in items:
        item_id = item["id"]
        source = item["source"]
        raw = item.get("raw_score", 0) or 0

        source_weight = SOURCE_WEIGHTS.get(source, 1.0)
        tfidf_boost = tfidf_scores.get(item_id, 0)

        # Composite: 50% raw source score + 30% TF-IDF relevance + 20% source weight
        final = (raw * 0.5) + (tfidf_boost * 30) + (source_weight * 20)
        item["final_score"] = round(final, 2)

    # Step 3: Normalize to 0-100
    scores = [i["final_score"] for i in items]
    max_score = max(scores) if scores else 1
    if max_score > 0:
        for item in items:
            item["final_score"] = round((item["final_score"] / max_score) * 100, 1)

    items.sort(key=lambda x: x["final_score"], reverse=True)
    return items


def cluster_items(items: list[dict], config: dict) -> list[dict]:
    """Group similar items into topic clusters.

    Returns a list of cluster dicts:
    [
        {
            "cluster_id": 0,
            "label": "birria tacos Denver",
            "items": [...],
            "top_score": 95.2,
            "cities": ["denver"],
            "sources": ["google_news", "reddit"],
        },
        ...
    ]
    """
    def _single_cluster(items_list):
        """Fallback: put all items in one cluster."""
        items_list.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        return [
            {
                "cluster_id": 0,
                "label": items_list[0]["title"][:60] if items_list else "No data",
                "items": items_list,
                "top_score": items_list[0].get("final_score", 0) if items_list else 0,
                "cities": list({i["city"] for i in items_list}),
                "sources": list({i["source"] for i in items_list}),
            }
        ]

    if len(items) < 3:
        return _single_cluster(items)

    texts = [f"{i.get('title', '')} {i.get('summary', '')}" for i in items]

    try:
        vectorizer = TfidfVectorizer(
            max_features=500,
            stop_words="english",
            min_df=1,
            max_df=0.95,
        )
        tfidf_matrix = vectorizer.fit_transform(texts)

        if tfidf_matrix.shape[1] == 0:
            logger.warning("TF-IDF produced empty vocabulary — skipping clustering")
            return _single_cluster(items)

        # Determine number of clusters dynamically
        n_items = len(items)
        n_clusters = max(2, min(n_items // 3, config.get("max_clusters", 15)))

        similarity = cosine_similarity(tfidf_matrix)
        distance = 1 - similarity
        np.fill_diagonal(distance, 0)
        distance = np.clip(distance, 0, None)
        # Replace any NaN with 1.0 (max distance)
        distance = np.nan_to_num(distance, nan=1.0)

        clustering = AgglomerativeClustering(
            n_clusters=n_clusters,
            metric="precomputed",
            linkage="average",
        )
        labels = clustering.fit_predict(distance)
    except Exception:
        logger.exception("Clustering failed — returning items as single cluster")
        return _single_cluster(items)

    # Build cluster objects
    cluster_map: dict[int, list[dict]] = defaultdict(list)
    for idx, label in enumerate(labels):
        cluster_map[int(label)].append(items[idx])

    feature_names = vectorizer.get_feature_names_out()

    clusters = []
    for cluster_id, cluster_items_list in cluster_map.items():
        cluster_items_list.sort(key=lambda x: x.get("final_score", 0), reverse=True)

        # Generate label from top TF-IDF terms of cluster items
        try:
            cluster_texts = [f"{i.get('title', '')} {i.get('summary', '')}" for i in cluster_items_list]
            cluster_tfidf = vectorizer.transform(cluster_texts)
            mean_vector = cluster_tfidf.mean(axis=0).A1
            top_indices = mean_vector.argsort()[-3:][::-1]
            label = " ".join(feature_names[i] for i in top_indices)
        except Exception:
            label = cluster_items_list[0].get("title", "Unknown")[:60] if cluster_items_list else "Unknown"

        clusters.append(
            {
                "cluster_id": cluster_id,
                "label": label,
                "items": cluster_items_list,
                "top_score": cluster_items_list[0].get("final_score", 0),
                "cities": list({i["city"] for i in cluster_items_list}),
                "sources": list({i["source"] for i in cluster_items_list}),
            }
        )

    clusters.sort(key=lambda c: c["top_score"], reverse=True)
    return clusters


def detect_breaking_news(items: list[dict], threshold: float = 85.0) -> list[dict]:
    """Identify items that qualify as breaking news for mid-week alerts.

    Breaking = high score + appeared in multiple sources + recent.
    """
    breaking = []
    # Group by rough title similarity
    title_groups: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        # Normalize title for grouping
        key = re.sub(r"[^a-z0-9 ]", "", item.get("title", "").lower()).strip()
        key = " ".join(key.split()[:5])  # First 5 words
        title_groups[key].append(item)

    for key, group in title_groups.items():
        if len(group) < 2:
            continue
        sources = {i["source"] for i in group}
        if len(sources) < 2:
            continue
        top_item = max(group, key=lambda x: x.get("final_score", 0))
        if top_item.get("final_score", 0) >= threshold:
            top_item["breaking_sources"] = list(sources)
            top_item["breaking_mentions"] = len(group)
            breaking.append(top_item)

    breaking.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    return breaking



# Cities we don't cover — if an article headline is about one of these
# and doesn't mention one of ours, skip it for story ideas.
_NON_TARGET_CITIES = {
    "new york", "nyc", "brooklyn", "manhattan",
    "los angeles", "la", "chicago", "san francisco",
    "seattle", "portland", "miami", "boston",
    "philadelphia", "phoenix", "minneapolis",
    "nashville", "detroit", "pittsburgh",
    "australia", "sydney", "melbourne",
    "london", "uk", "paris", "tokyo", "canada", "toronto",
    "san antonio",
}
_TARGET_CITIES = {"denver", "houston", "dallas", "atlanta", "fort worth", "texas", "colorado", "georgia"}

# Map geographic keywords in text → canonical city value
_CITY_EXTRACT_MAP = {
    "denver": "denver",
    "colorado": "denver",
    "houston": "houston",
    "dallas": "dallas",
    "fort worth": "dallas",
    "north texas": "dallas",
    "dfw": "dallas",
    "atlanta": "atlanta",
}


def _headline_is_non_target(title: str, summary: str = "") -> bool:
    """Return True if headline is about a city/region we don't cover."""
    t = f"{title} {summary}".lower()
    has_target = any(tc in t for tc in _TARGET_CITIES)
    if has_target:
        return False
    return any(ntc in t for ntc in _NON_TARGET_CITIES)


def _extract_cities_from_text(text: str) -> list[str]:
    """Extract target cities mentioned in text. Returns deduped list."""
    t = text.lower()
    seen: set[str] = set()
    cities: list[str] = []
    for keyword, city_val in _CITY_EXTRACT_MAP.items():
        if keyword in t and city_val not in seen:
            seen.add(city_val)
            cities.append(city_val)
    return cities


def generate_story_ideas(clusters: list[dict], config: dict) -> list[dict]:
    """Turn trend clusters into actionable editorial story ideas.

    Key design decisions:
    - Cities are derived from the top item's content, NOT from all cluster members
    - Chain restaurant articles are filtered out (DiningOut = independent restaurants)
    - Non-target city content is filtered using both title and summary
    - Each idea includes a URL so editors can click through for context
    - Titles are NOT truncated so editors see the full headline
    """
    ideas = []
    target_city_values = {"denver", "houston", "dallas", "atlanta"}
    event_keywords = config.get("event_keywords", {
        "tacos": "TOP TACO",
        "steak": "RARE",
        "fried chicken": "CHICKEN FIGHT!",
        "seafood": "SURF",
    })

    for cluster in clusters:
        label = cluster["label"].lower()
        top_score = cluster["top_score"]

        if top_score < 20:
            continue

        # Find the best item that passes all relevance filters
        top_item = None
        for item in cluster["items"]:
            title = item.get("title", "")
            summary = item.get("summary", "")
            if _headline_is_non_target(title, summary):
                continue
            if is_chain_article(title):
                continue
            top_item = item
            break
        if top_item is None:
            continue

        top_title = top_item.get("title", cluster["label"])
        top_url = top_item.get("url", "")
        top_summary = top_item.get("summary", "")

        # Double-check: skip chains and non-target content
        if is_chain_article(top_title):
            continue
        if _headline_is_non_target(top_title, top_summary):
            continue

        # --- CITY ASSIGNMENT: derive from content, not cluster ---
        # Check what cities are actually mentioned in the article text
        content_text = f"{top_title} {top_summary}"
        mentioned_cities = _extract_cities_from_text(content_text)
        mentioned_cities = [c for c in mentioned_cities if c in target_city_values]

        if mentioned_cities:
            relevant_cities = mentioned_cities
        else:
            # No city explicitly mentioned in text — use the item's assigned city
            item_city = top_item.get("city", "")
            if item_city in target_city_values:
                relevant_cities = [item_city]
            else:
                # Generic article with no city tie — skip unless very high signal
                if len(cluster["sources"]) >= 3 and top_score >= 70:
                    # National trend worth noting — pick first target city from cluster
                    cluster_target = [c for c in cluster["cities"] if c in target_city_values]
                    relevant_cities = cluster_target[:1] if cluster_target else []
                if not relevant_cities:
                    continue

        priority = "high" if top_score >= 70 else "medium" if top_score >= 40 else "low"
        city_display = ", ".join(
            c.replace("_", " ").title() for c in relevant_cities
        )

        # One story idea per cluster (not per city)
        ideas.append(
            {
                "headline": top_title,
                "url": top_url,
                "type": "trending_topic",
                "supporting_data": (
                    f"{len(cluster['items'])} signals across "
                    f"{len(cluster['sources'])} sources in {city_display} "
                    f"(score: {top_score})"
                ),
                "cities": relevant_cities,
                "priority": priority,
                "cluster_id": cluster["cluster_id"],
            }
        )

        # Check for event tie-in
        combined_text = f"{label} {top_title.lower()}"
        for kw, event_name in event_keywords.items():
            if kw in combined_text:
                ideas.append(
                    {
                        "headline": f"{event_name} Intel: {top_title}",
                        "url": top_url,
                        "type": "event_intel",
                        "supporting_data": f"Related to {event_name} — '{kw}' trending in {city_display}",
                        "cities": relevant_cities,
                        "priority": "high",
                        "cluster_id": cluster["cluster_id"],
                    }
                )

        # Check for openings/closings
        opening_signals = ["opening", "opened", "new restaurant", "coming soon", "first look"]
        closing_signals = ["closing", "closed", "shutting", "last day", "farewell"]
        if any(sig in combined_text for sig in opening_signals):
            ideas.append(
                {
                    "headline": f"Restaurant Openings: {top_title}",
                    "url": top_url,
                    "type": "openings_roundup",
                    "supporting_data": f"{len(cluster['items'])} mentions across sources in {city_display}",
                    "cities": relevant_cities,
                    "priority": "high",
                    "cluster_id": cluster["cluster_id"],
                }
            )
        elif any(sig in combined_text for sig in closing_signals):
            ideas.append(
                {
                    "headline": f"Notable Closings: {top_title}",
                    "url": top_url,
                    "type": "closings_roundup",
                    "supporting_data": f"{len(cluster['items'])} mentions across sources in {city_display}",
                    "cities": relevant_cities,
                    "priority": "medium",
                    "cluster_id": cluster["cluster_id"],
                }
            )

    # Deduplicate by headline
    seen = set()
    unique_ideas = []
    for idea in ideas:
        if idea["headline"] not in seen:
            seen.add(idea["headline"])
            unique_ideas.append(idea)

    unique_ideas.sort(key=lambda x: {"high": 3, "medium": 2, "low": 1}.get(x["priority"], 0), reverse=True)
    return unique_ideas


def _compute_tfidf_scores(items: list[dict], config: dict) -> dict[int, float]:
    """Compute TF-IDF relevance scores for each item.

    Returns a mapping of item DB ID -> TF-IDF score (0-1).
    """
    texts = [f"{i.get('title', '')} {i.get('summary', '')}" for i in items]
    ids = [i["id"] for i in items]

    if not texts:
        return {}

    vectorizer = TfidfVectorizer(
        max_features=config.get("tfidf_max_features", 1000),
        stop_words=STOP_WORDS + (config.get("extra_stop_words") or []),
        min_df=1,
        max_df=0.9,
    )

    try:
        tfidf_matrix = vectorizer.fit_transform(texts)
    except ValueError:
        return {}

    # Score = mean TF-IDF value across all features for each document
    scores = {}
    for idx, item_id in enumerate(ids):
        row = tfidf_matrix.getrow(idx).toarray().flatten()
        scores[item_id] = float(row.mean()) if len(row) > 0 else 0.0

    return scores
