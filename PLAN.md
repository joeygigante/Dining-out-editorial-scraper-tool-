# Dining Out Editorial Scraper Tool — Implementation Plan

## Goal

Build a Python tool that automatically collects trending dining and food topics from multiple data sources and delivers a consolidated report to the DiningOut editorial team on a recurring basis, enabling faster and more data-informed editorial ideation.

---

## Data Sources (ranked by practicality)

### Tier 1 — Start here (free, high signal, low friction)

| Source | Access Method | Cost | What It Gives You |
|---|---|---|---|
| **Google News RSS** | RSS feed queries (`gnews` or `feedparser`) | Free | Aggregated food/dining headlines from all major publications |
| **Food publication RSS feeds** | Direct RSS/Atom parsing (`feedparser`) | Free | Editorials from Eater, Bon Appetit, The Infatuation, Food52, etc. |
| **Google Trends** | `pytrends` or `pytrends-modern` | Free | Quantitative search interest for food keywords, related queries, trending searches |
| **Reddit** | Official API via `praw` (OAuth, 60 req/min) | Free | Community buzz from r/food, r/cooking, r/restaurants, r/FoodPorn, r/KitchenConfidential, r/fastfood |

### Tier 2 — Add next (more setup or cost, unique signal)

| Source | Access Method | Cost | What It Gives You |
|---|---|---|---|
| **TikTok** | Unofficial `TikTok-Api` library (or apply for official API) | Free | Viral food trends via #FoodTok — arguably the leading indicator of food culture trends |
| **Yelp Insights API** | Official REST API | ~$8-15 per 1,000 calls | Restaurant open/close trends, consumer demand signals, review sentiment |

### Tier 3 — Consider later (expensive or restrictive)

| Source | Access Method | Cost | What It Gives You |
|---|---|---|---|
| **X (Twitter)** | Official API, Basic tier | $100/month | Real-time food conversation, 7-day search window |
| **Instagram** | Graph API (Business account required) | Free | Hashtag engagement data — limited to 30 hashtags/week |
| **Bing News API** | Azure REST API | ~$7 per 25K calls | Structured news search with metadata |

### Not recommended

- **OpenTable** — Gated partner API, designed for reservations, not trend data.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Scheduler (cron)                   │
│              Runs daily / weekly / etc.              │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│                  Collector Layer                     │
│                                                     │
│  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌──────────┐ │
│  │ News/RSS │ │ Google   │ │ Reddit │ │ TikTok   │ │
│  │ Collector│ │ Trends   │ │        │ │          │ │
│  └────┬─────┘ └────┬─────┘ └───┬────┘ └────┬─────┘ │
│       │             │           │            │       │
└───────┼─────────────┼───────────┼────────────┼──────┘
        │             │           │            │
        ▼             ▼           ▼            ▼
┌─────────────────────────────────────────────────────┐
│              Normalizer / Storage                    │
│          (common schema → SQLite or JSON)            │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│               Analysis / Ranking                     │
│  - Keyword extraction (TF-IDF or similar)            │
│  - Topic clustering                                  │
│  - Trend scoring (velocity, cross-source mentions)   │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│               Report Generation                      │
│  - Top trending topics with sources                  │
│  - Rising topics (momentum signals)                  │
│  - Suggested editorial angles                        │
│  - Output: HTML email / Slack message / PDF          │
└─────────────────────────────────────────────────────┘
```

---

## Proposed Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| RSS parsing | `feedparser`, `gnews` |
| Google Trends | `pytrends` (or `pytrends-modern` for async + retries) |
| Reddit | `praw` |
| TikTok | `TikTok-Api` (unofficial) |
| NLP / keyword extraction | `scikit-learn` (TF-IDF), optionally `spaCy` for entity extraction |
| Storage | SQLite (lightweight) or flat JSON files |
| Scheduling | `cron` (system), or `schedule` (Python library), or GitHub Actions |
| Report delivery | Email via `smtplib`/SendGrid, or Slack webhook, or both |
| Configuration | `.env` file for API keys, `config.yaml` for source settings |

---

## Implementation Phases

### Phase 1 — Core pipeline (news + Google Trends)

1. **Project scaffolding**
   - Set up Python project structure, virtual environment, `requirements.txt`
   - Create configuration system (`config.yaml` + `.env`)

2. **News/RSS collector**
   - Scrape Google News RSS for food/dining queries (e.g. "food trends", "restaurant openings", "new cuisine")
   - Parse RSS feeds from Eater, Bon Appetit, The Infatuation, Food52, Serious Eats
   - Normalize all articles into a common schema: `{title, source, url, date, summary}`

3. **Google Trends collector**
   - Query `pytrends` for a curated seed list of food keywords
   - Pull trending searches for the Food & Drink category (`cat=71`)
   - Collect related queries (rising + top) for each seed keyword
   - Handle rate limiting with backoff

4. **Basic trend analysis**
   - Extract keywords from article titles/summaries using TF-IDF
   - Cross-reference with Google Trends rising queries
   - Score topics by: frequency across sources, trend velocity, recency

5. **Report generation**
   - Generate a structured report (Markdown → HTML)
   - Sections: "Top Trending Topics", "Rising Topics", "Source Breakdown"
   - Include links back to original articles

### Phase 2 — Community signals (Reddit)

6. **Reddit collector**
   - Monitor hot/rising posts from key food subreddits
   - Extract post titles, scores, comment counts, and flair
   - Feed into the same normalization pipeline

7. **Enhanced analysis**
   - Add Reddit signal to trend scoring (upvote velocity, comment engagement)
   - Identify topics that are trending on Reddit but haven't hit mainstream news yet (early signals)

### Phase 3 — Social + delivery

8. **TikTok collector** (optional, higher maintenance)
   - Monitor trending hashtags: #FoodTok, #ViralFood, #RecipeTrend
   - Track view counts and engagement for food-tagged content

9. **Automated delivery**
   - Set up scheduled execution (cron or GitHub Actions)
   - Email reports to editorial team
   - Optional: post summary to a Slack channel

10. **Yelp integration** (optional, paid)
    - Pull restaurant open/close trends from Insights API
    - Add market-level signals to reports

---

## Report Output Example

```
═══════════════════════════════════════════════════
  DININGOUT TREND REPORT — Week of Feb 24, 2026
═══════════════════════════════════════════════════

🔥 TOP TRENDING TOPICS

1. Dubai Chocolate
   Sources: Eater, Bon Appetit, Google Trends (↑320%)
   Reddit: 47 posts in r/food this week (avg 2.1k upvotes)
   Angle: The viral pistachio chocolate trend reaches US markets

2. Japanese Milk Bread
   Sources: Food & Wine, Serious Eats, Google Trends (↑180%)
   Angle: Home bakers driving a second wave of shokupan interest

3. Supper Clubs
   Sources: The Infatuation, NY Times, Reddit r/restaurants
   Angle: Underground dining makes a mainstream comeback

📈 RISING (early signals)

4. Mala Sauce (Reddit ↑, not yet in mainstream news)
5. Tinned Fish Restaurants (Google Trends ↑85%)
6. Non-Alcoholic Wine Bars (cross-platform signal)

📰 SOURCE BREAKDOWN
   • 23 articles from Eater (3 city editions)
   • 12 articles from Bon Appetit
   • 8 trending searches on Google Trends (Food & Drink)
   • 156 hot posts across food subreddits
```

---

## File Structure

```
dining-scraper/
├── config/
│   ├── config.yaml          # Source URLs, keywords, subreddits, schedule
│   └── .env                 # API keys (Reddit, Yelp, etc.)
├── src/
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── news_rss.py      # Google News + publication RSS
│   │   ├── google_trends.py # pytrends wrapper
│   │   ├── reddit.py        # PRAW-based collector
│   │   └── tiktok.py        # TikTok collector (Phase 3)
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── keywords.py      # TF-IDF keyword extraction
│   │   ├── scoring.py       # Trend scoring & ranking
│   │   └── clustering.py    # Topic grouping
│   ├── reporting/
│   │   ├── __init__.py
│   │   ├── formatter.py     # Markdown/HTML report builder
│   │   └── delivery.py      # Email/Slack sender
│   ├── storage.py           # SQLite or JSON persistence
│   └── main.py              # Orchestrator / entry point
├── data/                    # Local data storage
├── templates/               # Report HTML templates
├── tests/
├── requirements.txt
└── README.md
```

---

## Key Dependencies

```
feedparser>=6.0
gnews>=0.3
pytrends>=4.9
praw>=7.7
scikit-learn>=1.3
jinja2>=3.1
python-dotenv>=1.0
pyyaml>=6.0
requests>=2.31
```

---

## Decisions to Make Before Coding

1. **Report frequency** — Daily? Weekly? Both (daily brief + weekly deep dive)?
2. **Delivery method** — Email, Slack, both, or a web dashboard?
3. **Seed keyword list** — What initial food/dining keywords should be tracked? (e.g., specific cuisines, ingredients, dining formats)
4. **Geographic focus** — National US? Specific cities? International?
5. **TikTok priority** — Worth the maintenance cost of an unofficial API, or skip for v1?
6. **Yelp budget** — Is the paid Yelp Insights API worth it for the editorial team's needs?
7. **Historical storage** — How far back should trend data be retained for comparison?

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| `pytrends` breaks (Google changes) | Use `pytrends-modern` which has better error handling; fall back to official Google Trends API when it exits alpha |
| Reddit API rate limits hit | PRAW handles this automatically; add caching layer |
| TikTok unofficial API breaks | Isolate TikTok collector so failure doesn't affect the rest of the pipeline |
| RSS feed URLs change | Store feed URLs in config; add health checks that alert when feeds return errors |
| Too much noise in results | Tune TF-IDF parameters; maintain a stop-word list specific to food journalism boilerplate |
| Yelp pricing increases | Keep Yelp as an optional module; core pipeline works without it |
