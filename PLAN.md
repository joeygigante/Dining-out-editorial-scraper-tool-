# Dining Out Editorial Scraper Tool — Implementation Plan

## Goal

Build a Python tool that automatically collects trending dining and food topics from multiple data sources and delivers a consolidated report to the DiningOut editorial team on a recurring basis, enabling faster and more data-informed editorial ideation.

---

## About DiningOut — Context Driving This Plan

**DiningOut** is a regional U.S. food and dining media brand founded in 1998, headquartered in Denver, CO. It operates as both a print/digital publication and an events company under the umbrella **DiningOut Global**.

### Key facts that shape the tool design:

- **Multi-city, not national.** Active editorial markets: **Denver** (flagship), **Houston**, **Dallas**, **Atlanta**. Expanding into **Phoenix** and **NYC** via events. Each city has its own editorial coverage.
- **Lean editorial team.** ~28 employees total, likely fewer than 10 on editorial. A Texas Editor covers Houston/Dallas. Denver has the deepest coverage. A time-saving trend tool has outsized value for a team this small.
- **Promotional editorial tone.** DiningOut celebrates and promotes the independent restaurant scene — new openings, chef profiles, "best of" lists, neighborhood guides. They are not a critical review publication with star ratings.
- **Core content types that a trend tool should feed:**
  - Weekly restaurant openings/closings roundups
  - "Best of" curated lists (best tacos, best BBQ, best happy hours, etc.)
  - Neighborhood dining guides
  - Chef/owner profiles and interviews
  - Food trend reporting and seasonal coverage
  - Event tie-in content (tacos, steak, fried chicken, seafood, cocktails)
- **Events are a major business line.** DiningOut produces TOP TACO, CHICKEN FIGHT!, RARE (steak), and SURF (seafood) festivals across their cities. Trend data around these categories directly informs event planning.
- **Dual audience.** Content serves both consumers (diners/foodies) and the restaurant industry (marketing resource for independent restaurants).
- **Competitors to monitor:** Eater (city editions for Denver, Dallas, Houston, Atlanta), The Infatuation, 5280 Magazine, Westword, D Magazine, Houstonia, Atlanta Magazine.

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
   - Scrape Google News RSS for city-specific dining queries:
     - `"Denver restaurants"`, `"Houston dining"`, `"Dallas food scene"`, `"Atlanta restaurants"`
     - `"restaurant openings Denver"`, `"restaurant openings Houston"`, etc.
     - `"food trends 2026"`, `"new cuisine"`, `"chef spotlight"`
   - Parse RSS feeds from DiningOut's direct competitors in each market:
     - **National:** Eater (national + city editions for Denver, Dallas, Houston, Atlanta), Bon Appetit, The Infatuation, Food52, Serious Eats
     - **Denver:** Westword food section, 5280 Magazine, Denver Post food
     - **Houston:** Houstonia Magazine, Houston Chronicle food
     - **Dallas:** D Magazine dining, Dallas Morning News food
     - **Atlanta:** Atlanta Magazine dining, Atlanta Journal-Constitution food
   - Normalize all articles into a common schema: `{title, source, url, date, summary, city}`

3. **Google Trends collector**
   - Query `pytrends` for a curated seed list of food keywords
   - Pull trending searches for the Food & Drink category (`cat=71`)
   - **Run queries with geographic filters for each DiningOut market** (`geo='US-CO'`, `geo='US-TX'`, `geo='US-GA'`)
   - Collect related queries (rising + top) for each seed keyword
   - Track DiningOut's event-relevant categories specifically: tacos, steak, fried chicken, seafood, cocktails
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
   - Monitor hot/rising posts from key food subreddits (r/food, r/cooking, r/restaurants, r/FoodPorn, r/KitchenConfidential, r/fastfood)
   - **Add city-specific subreddits:** r/Denver, r/denverfood, r/Houston, r/houstonfood, r/Dallas, r/dallasfoodies, r/Atlanta, r/atlantaeats
   - Extract post titles, scores, comment counts, and flair
   - Feed into the same normalization pipeline

7. **Enhanced analysis**
   - Add Reddit signal to trend scoring (upvote velocity, comment engagement)
   - Identify topics that are trending on Reddit but haven't hit mainstream news yet (early signals)
   - **Flag trends relevant to DiningOut's event categories** (tacos, steak, fried chicken, seafood, cocktails) with a special "event intel" tag

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
═══════════════════════════════════════════════════════════════
  DININGOUT TREND REPORT — Week of Feb 24, 2026
═══════════════════════════════════════════════════════════════

NATIONAL TRENDS

  1. Dubai Chocolate
     Sources: Eater, Bon Appetit, Google Trends (up 320%)
     Reddit: 47 posts in r/food this week (avg 2.1k upvotes)
     Content angle: "Best of" list — where to find Dubai chocolate in each city
     Competitor coverage: Eater (national feature), Bon Appetit (recipe)

  2. Non-Alcoholic Wine Bars
     Sources: The Infatuation, Food & Wine, Google Trends (up 140%)
     Content angle: Neighborhood guide tie-in — NA options in RiNo, Uptown, etc.

  3. Supper Clubs
     Sources: NY Times, Reddit r/restaurants
     Content angle: Chef profile series — local chefs hosting pop-ups

CITY SPOTLIGHTS

  DENVER
  - 4 new restaurant openings this week (Eater Denver, Westword)
  - "Birria" search interest up 90% in Colorado (Google Trends)
  - r/denverfood buzzing about a new RiNo ramen spot (340 upvotes)
  - Suggested: Openings roundup + RiNo guide update

  HOUSTON
  - "Best queso" trending in Houston searches (Google Trends)
  - Houstonia published "12 New Patios" — gap for DiningOut coverage
  - Suggested: "Best Queso in Houston" list

  DALLAS
  - D Magazine ran a Knox-Henderson dining guide this week
  - 2 new openings covered by Eater Dallas
  - Suggested: Competing Knox-Henderson guide or chef profile

  ATLANTA
  - Atlanta Magazine featured a Buford Highway deep-dive
  - Trending on r/atlantaeats: Ethiopian cuisine (3 posts, 500+ upvotes)
  - Suggested: "Best Ethiopian in Atlanta" list

EVENT INTEL (for TOP TACO / RARE / CHICKEN FIGHT! planning)

  - "Birria tacos" search interest up 90% nationally — consider for TOP TACO
  - "Smashburger vs steak" debate trending on r/food — RARE angle?
  - Nashville hot chicken continuing to trend — CHICKEN FIGHT! relevance

RISING (early signals, not yet mainstream)

  - Mala Sauce (Reddit up, no mainstream news coverage yet)
  - Tinned Fish Restaurants (Google Trends up 85%)
  - "Omakase at home" kits (TikTok + Reddit crossover)

COMPETITOR WATCH

  Articles published this week by competitors in DiningOut markets:
  - Eater Denver: 8 articles (3 openings, 2 guides, 3 news)
  - Eater Dallas: 5 articles
  - Eater Houston: 4 articles
  - Westword: 3 food articles
  - 5280: 1 dining feature
  - D Magazine: 2 restaurant articles
  - Houstonia: 3 food articles
  - Atlanta Magazine: 2 dining features

SOURCE TOTALS
  - 34 articles from competitor publications
  - 12 trending searches on Google Trends (Food & Drink)
  - 210 hot posts across food + city subreddits
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

### Already answered by research:

- **Geographic focus** — Denver (primary), Houston, Dallas, Atlanta. Expand to Phoenix and NYC as events grow there.
- **Seed keyword list** — Start with DiningOut's event categories (tacos, steak, fried chicken, seafood, cocktails) plus general dining terms (restaurant openings, new restaurants, chef, brunch, happy hour, patio dining, fine dining, fast casual). Add city-specific terms per market.
- **Content alignment** — Reports should suggest specific DiningOut content types: "best of" lists, neighborhood guides, openings roundups, chef profiles, event intel.

### Still need input from the team:

1. **Report frequency** — Recommendation: weekly report (Monday morning) with a lighter mid-week alert for breaking news (new openings, viral moments). The lean team likely can't act on daily reports.
2. **Delivery method** — Email is the safest bet for a ~28-person company. Does the team use Slack? If so, a Slack channel (#editorial-trends) would add real-time value.
3. **TikTok priority** — Recommendation: skip for v1. The unofficial API is fragile and DiningOut's editorial style (local restaurant coverage) is less dependent on TikTok virality than a national publication would be. Add in v2 once the core pipeline proves useful.
4. **Yelp budget** — Recommendation: skip Yelp Insights for v1. The free sources (RSS + Google Trends + Reddit) cover the most actionable signals. Yelp's open/close data overlaps with what Eater and local news already report via RSS.
5. **Competitor monitoring depth** — Should the report just count competitor articles, or also summarize/excerpt them? Full summarization is more useful but adds complexity.
6. **Who receives the report?** — All editorial staff? Just editors? City-specific reports to city-specific editors (e.g., Texas Editor gets only Houston/Dallas)?
7. **Historical storage** — Recommendation: 90 days of trend data to enable week-over-week and month-over-month comparisons.

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

---

## DiningOut-Specific Tailoring Suggestions

Based on research into DiningOut's editorial model, audience, and business:

### 1. City-first report structure
DiningOut's editorial team is organized by city (Texas Editor, Denver staff, etc.). The report should be structured **city-first**, not topic-first. Each city section should surface what's relevant to that market's editor, with a national trends section at the top for cross-cutting stories. Optionally, generate separate per-city reports that can be sent to the relevant editor.

### 2. Competitor gap analysis
DiningOut competes with Eater city editions, Westword, 5280, D Magazine, Houstonia, and Atlanta Magazine. The most immediately actionable feature of this tool is showing **what competitors published this week that DiningOut hasn't covered yet**. This turns the report from "interesting data" into "here's what you should write about today."

### 3. Event category tracking
TOP TACO, RARE, CHICKEN FIGHT!, and SURF are major revenue drivers. The scraper should permanently track trend data for tacos, steak, fried chicken, seafood, and cocktails — even outside of event season — so the team can spot rising themes that inform next year's event programming and related editorial.

### 4. "Best of" list generator
DiningOut's bread and butter is curated lists ("Best Salads in Houston," "Denver's Fried Chicken Hall of Fame"). When the tool detects a food category trending in a specific city, it should automatically suggest a "Best of" list idea: *"'Birria' is trending +90% in Denver searches — consider: 'Best Birria in Denver' list."*

### 5. Openings/closings feed
DiningOut already publishes weekly openings/closings roundups for Denver. The scraper can automate the research step by aggregating restaurant opening/closing mentions from local news RSS feeds, Reddit city subreddits, and Google News across all four markets — saving the editor manual research time each week.

### 6. Passbook intelligence
DiningOut sells a restaurant coupon "Passbook" product in Denver. If Yelp integration is added later, tracking which restaurants are trending in reviews/ratings could inform Passbook partner outreach — approach rising restaurants for inclusion while they're generating buzz.

### 7. Newsletter content
DiningOut promotes a newsletter for "the latest chef and restaurant news + early access to event presale tickets." The trend report's top items could be repurposed directly as newsletter content or editorial hooks, reducing the effort to produce the weekly newsletter.

### 8. Start lean, prove value fast
With a team of ~28 (and <10 editorial), the tool should prioritize **immediately actionable output** over comprehensive data. A weekly email with 5 trend-driven article ideas and a competitor coverage gap list is more valuable than a 50-item data dump. Start with Phase 1 (RSS + Google Trends) — this alone covers the most useful signals at zero API cost — and add Reddit/TikTok only after the team confirms the reports are useful.
