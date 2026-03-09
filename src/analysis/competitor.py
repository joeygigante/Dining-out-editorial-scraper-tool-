"""Competitor gap analysis.

Compares what competitor publications (Eater, Westword, 5280, D Magazine,
Houstonia, Atlanta Magazine, The Infatuation) covered this week against
DiningOut's coverage to surface stories DiningOut hasn't written yet.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

COMPETITORS = {
    "eater",
    "westword",
    "5280",
    "d magazine",
    "houstonia",
    "atlanta magazine",
    "bon appetit",
    "infatuation",
}


def analyze_competitor_gaps(items: list[dict]) -> list[dict]:
    """Find stories competitors covered that may represent coverage gaps.

    Returns a list of gap dicts sorted by relevance:
    [
        {
            "competitor": "Eater Denver",
            "title": "New Birria Spot Opens in RiNo",
            "url": "https://...",
            "summary": "...",
            "city": "denver",
            "gap_score": 0.95,
            "similar_items": [],  # any related items from other sources
        },
        ...
    ]
    """
    # Separate competitor items from non-competitor items
    competitor_items = []
    other_items = []

    for item in items:
        metadata = _get_metadata(item)

        feed_name = metadata.get("feed_name", "").lower()
        is_competitor = metadata.get("is_competitor", False)

        if is_competitor or any(comp in feed_name for comp in COMPETITORS):
            competitor_items.append(item)
        else:
            other_items.append(item)

    if not competitor_items:
        return []

    # Use TF-IDF + cosine similarity to find competitor articles
    # that are NOT similar to anything from non-competitor sources
    gaps = _find_gaps(competitor_items, other_items)

    return gaps


def _find_gaps(competitor_items: list[dict], other_items: list[dict]) -> list[dict]:
    """Use text similarity to find competitor stories without matches elsewhere."""
    if not competitor_items:
        return []

    comp_texts = [f"{i.get('title', '')} {i.get('summary', '')}" for i in competitor_items]

    if other_items:
        other_texts = [f"{i.get('title', '')} {i.get('summary', '')}" for i in other_items]
        all_texts = comp_texts + other_texts
    else:
        all_texts = comp_texts

    try:
        vectorizer = TfidfVectorizer(max_features=500, stop_words="english")
        tfidf_matrix = vectorizer.fit_transform(all_texts)
    except ValueError:
        return []

    n_comp = len(competitor_items)

    gaps = []
    for i in range(n_comp):
        item = competitor_items[i]

        if other_items:
            # Compare this competitor article to all non-competitor items
            comp_vec = tfidf_matrix[i]
            other_vecs = tfidf_matrix[n_comp:]
            similarities = cosine_similarity(comp_vec, other_vecs).flatten()
            max_similarity = float(similarities.max()) if len(similarities) > 0 else 0

            # Lower similarity = bigger gap (story not covered elsewhere)
            gap_score = round(1.0 - max_similarity, 2)

            # Find closest matches for context
            similar = []
            if max_similarity > 0.2:
                top_idx = similarities.argsort()[-3:][::-1]
                for idx in top_idx:
                    if similarities[idx] > 0.2:
                        similar.append(
                            {
                                "title": other_items[idx].get("title", ""),
                                "source": other_items[idx].get("source", ""),
                                "similarity": round(float(similarities[idx]), 2),
                            }
                        )
        else:
            gap_score = 1.0
            similar = []

        metadata = _get_metadata(item)

        gaps.append(
            {
                "competitor": metadata.get("feed_name", "Unknown"),
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "summary": item.get("summary", ""),
                "city": item.get("city", "national"),
                "gap_score": gap_score,
                "similar_items": similar,
            }
        )

    # Only return real gaps (not covered elsewhere)
    gaps = [g for g in gaps if g["gap_score"] >= 0.5]
    gaps.sort(key=lambda x: x["gap_score"], reverse=True)

    return gaps


def summarize_competitor_activity(items: list[dict]) -> dict[str, list[dict]]:
    """Group competitor articles by publication and summarize.

    Returns:
    {
        "Eater Denver": [
            {"title": "...", "url": "...", "summary": "...", "city": "denver"},
            ...
        ],
        ...
    }
    """
    by_competitor: dict[str, list[dict]] = defaultdict(list)

    for item in items:
        metadata = _get_metadata(item)

        feed_name = metadata.get("feed_name", "")
        is_competitor = metadata.get("is_competitor", False)

        if not is_competitor and not any(comp in feed_name.lower() for comp in COMPETITORS):
            continue

        by_competitor[feed_name].append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "summary": item.get("summary", ""),
                "city": item.get("city", "national"),
            }
        )

    return dict(by_competitor)


def _get_metadata(item: dict) -> dict:
    """Get parsed metadata from an item, handling both pre-parsed and raw JSON."""
    if "metadata" in item and isinstance(item["metadata"], dict):
        return item["metadata"]
    raw = item.get("metadata_json", "{}")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}
