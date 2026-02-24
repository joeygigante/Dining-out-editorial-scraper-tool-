# DiningOut Editorial Scraper — Setup Guide

Step-by-step instructions to get the scraper running from scratch.

---

## Prerequisites

- Python 3.11+
- A terminal / command line
- ~30 minutes for account setup

---

## Step 1: Install Python Dependencies

```bash
cd Dining-out-editorial-scraper-tool-
pip install -r requirements.txt
```

If you get an error about `sgmllib3k`, run this first:
```bash
pip install 'setuptools==67.8.0'
pip install -r requirements.txt
```

---

## Step 2: Create Your .env File

```bash
cp .env.example .env
```

Open `.env` in a text editor. You'll fill in the values from the steps below.

---

## Step 3: Reddit API Credentials (Free)

Reddit gives you free API access. Here's exactly how to get it:

1. Go to https://www.reddit.com/prefs/apps
2. If you don't have a Reddit account, create one (takes 1 minute)
3. Scroll to the bottom of the page and click **"create another app..."**
4. Fill in the form:
   - **name**: `DiningOutScraper` (or anything you want)
   - **App type**: Select **"script"** (the third option)
   - **description**: `Editorial trend scraper for DiningOut`
   - **about url**: leave blank
   - **redirect uri**: `http://localhost:8080` (required but we won't use it)
5. Click **"create app"**
6. You'll see your new app. The credentials are:
   - **client_id**: The string of characters directly under "personal use script" (looks like `aBcDeFgHiJkLmN`)
   - **client_secret**: The string next to "secret" (looks like `xYz123AbC456dEf789GhI`)

7. Add them to your `.env` file:
   ```
   REDDIT_CLIENT_ID=aBcDeFgHiJkLmN
   REDDIT_CLIENT_SECRET=xYz123AbC456dEf789GhI
   ```

**Rate limits**: Reddit allows 60 requests/minute for script apps. Our scraper uses ~20 requests per run, so you'll never hit this.

---

## Step 4: Yelp API Key (Free)

Yelp's free tier gives 500 API calls/day. Our scraper uses ~40-80 calls per weekly run.

1. Go to https://www.yelp.com/developers
2. Click **"Get Started"** or **"Create App"**
3. If you don't have a Yelp account, create one
4. Fill in the app form:
   - **App Name**: `DiningOut Scraper`
   - **Industry**: `Journalism / Media`
   - **Contact Email**: your work email
   - **Description**: `Track restaurant trends for editorial coverage`
5. Agree to the terms and click **"Create New App"**
6. On the next page, you'll see your **API Key** — it's a long string starting with something like `bEaR...`
7. Add it to your `.env` file:
   ```
   YELP_API_KEY=bEaR1234567890abcdefghijklmnop
   ```

**Cost**: Free. The free tier (500 calls/day) is more than enough. If you ever need more, paid plans start at ~$1/month.

---

## Step 5: Email Delivery Setup

You have two options. **Option A (Gmail)** is the easiest to set up. **Option B (SendGrid)** is more reliable for production.

### Option A: Gmail SMTP (Easiest)

This uses a Gmail account to send the reports. You'll need to create an "App Password" since Google blocks regular password login for scripts.

1. Go to https://myaccount.google.com/security
2. Make sure **2-Step Verification** is turned ON (required for app passwords)
   - If it's off, click it and follow the setup (takes 2 minutes)
3. Go to https://myaccount.google.com/apppasswords
   - Or: Security > 2-Step Verification > scroll to bottom > "App passwords"
4. Under "Select app", choose **"Mail"**
5. Under "Select device", choose **"Other"** and type `DiningOut Scraper`
6. Click **"Generate"**
7. Google will show you a **16-character password** like `abcd efgh ijkl mnop`
   - Copy it (remove the spaces)
   - **This is shown only once** — save it somewhere safe

8. Add to your `.env` file:
   ```
   SMTP_USER=yourname@gmail.com
   SMTP_PASSWORD=abcdefghijklmnop
   SMTP_HOST=smtp.gmail.com
   ```

9. In `config/config.yaml`, update:
   ```yaml
   email_method: smtp
   email_from: "yourname@gmail.com"
   ```

### Option B: SendGrid API (More Reliable)

SendGrid's free tier allows 100 emails/day — plenty for weekly reports to 7 people.

1. Go to https://signup.sendgrid.com/
2. Create a free account
3. Complete email verification
4. In the SendGrid dashboard, go to **Settings > API Keys**
5. Click **"Create API Key"**
   - Name: `DiningOut Scraper`
   - Permissions: **"Restricted Access"** > toggle ON **"Mail Send"** only
6. Click **"Create & View"**
7. Copy the API key (starts with `SG.`)
   - **This is shown only once**

8. **Verify a sender identity** (required by SendGrid):
   - Go to **Settings > Sender Authentication**
   - Click **"Verify a Single Sender"**
   - Fill in your sending email address and name
   - Check your inbox and click the verification link

9. Add to your `.env` file:
   ```
   SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

10. In `config/config.yaml`, update:
    ```yaml
    email_method: sendgrid
    email_from: "trends@yourdomain.com"
    ```

---

## Step 6: Configure Recipients

Open `config/config.yaml` and add your team's email addresses:

```yaml
email_recipients:
  - editor1@diningout.com
  - editor2@diningout.com
  - editor3@diningout.com
  - editor4@diningout.com
  - editor5@diningout.com
  - editor6@diningout.com
  - editor7@diningout.com
```

---

## Step 7: Test Everything

Run these commands in order:

### 7a. Check that all data sources are reachable
```bash
python main.py health
```

You should see output like:
```
  news_rss: OK
  google_trends: OK
  reddit: OK
  tiktok: OK        (may show FAIL — that's fine, it's best-effort)
  yelp: OK
  storage: {'total_items': 0, 'total_reports': 0, ...}
```

If any show FAIL, double-check the credentials in your `.env` file.

### 7b. Collect data without sending email
```bash
python main.py collect
```

This pulls data from all sources and saves it to the database. You should see something like:
```
Collection complete: 247 items saved as run collect-20260224-143022-a1b2c3
```

### 7c. Generate a report and preview it
```bash
python main.py report -o test_report.html
```

Open `test_report.html` in your browser to preview the email report. Check that:
- City sections have data
- Story ideas look reasonable
- Competitor watch section shows articles
- The layout looks good in your email client

### 7d. Send a test email (to yourself first)

Temporarily change `email_recipients` in config.yaml to just your own email:
```yaml
email_recipients:
  - you@youremail.com
```

Then run:
```bash
python main.py run-weekly
```

Check your inbox (and spam folder). Once the email looks good, add back the full recipient list.

---

## Step 8: Automate It

Choose one of these options to run the scraper automatically:

### Option A: Built-in Scheduler (Simplest)

Just run this on any machine that stays on:
```bash
python main.py schedule
```

This runs the weekly report Monday at 7:00 AM and the mid-week alert Wednesday at 12:00 PM. Press Ctrl+C to stop.

To run it in the background on a Linux/Mac server:
```bash
nohup python main.py schedule > scraper.log 2>&1 &
```

### Option B: Cron Job (Reliable)

On a Linux/Mac machine, run `crontab -e` and add:
```cron
# Weekly report: Monday at 7am
0 7 * * 1 cd /path/to/Dining-out-editorial-scraper-tool- && python main.py run-weekly >> /var/log/diningout-scraper.log 2>&1

# Mid-week alert: Wednesday at noon
0 12 * * 3 cd /path/to/Dining-out-editorial-scraper-tool- && python main.py run-alert >> /var/log/diningout-scraper.log 2>&1
```

Replace `/path/to/` with the actual path to the project.

### Option C: GitHub Actions (Free, No Server Needed)

Create `.github/workflows/scraper.yml` in the repo — this runs the scraper on GitHub's servers for free. Let me know if you want me to set this up.

---

## Customization

### Add or remove keywords
Edit the `keywords` list in `config/config.yaml`. Good candidates:
- Food categories trending in your markets
- Cuisine types (birria, ramen, Korean BBQ, etc.)
- Industry terms (michelin, james beard, food truck, pop-up)

### Add new RSS feeds
Add entries to `rss_feeds` in `config/config.yaml`:
```yaml
rss_feeds:
  # ... existing feeds ...
  D Magazine Food: "https://www.dmagazine.com/food-drink/feed/"
  Houstonia Food: "https://www.houstoniamag.com/food/rss"
```

### Change report schedule
Edit `weekly_day`, `weekly_time`, `midweek_day`, `midweek_time` in `config/config.yaml`.

### Adjust sensitivity
- `breaking_threshold: 85.0` — Lower this (e.g., 70) to get more mid-week alerts, raise it (e.g., 95) for fewer
- `google_news_max_results: 10` — Increase for more coverage, decrease for less noise
- `reddit_posts_per_sub: 25` — Same idea

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` again |
| Reddit shows FAIL in health check | Double-check `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` in `.env` |
| Yelp shows FAIL | Check that `YELP_API_KEY` in `.env` is correct and the app is approved |
| TikTok shows FAIL | This is expected — TikTok's unofficial API is unreliable. The rest of the pipeline still works. |
| Email not received | Check spam folder. For Gmail: make sure you used an App Password, not your regular password. For SendGrid: verify your sender identity. |
| Google Trends returns empty | Google rate-limits aggressively. Try increasing `google_trends_delay` to 5 or 10. |
| `sgmllib3k` install error | Run `pip install 'setuptools==67.8.0'` first, then retry |
| Report looks empty | Run `python main.py collect` first to populate the database, then `python main.py report` |
