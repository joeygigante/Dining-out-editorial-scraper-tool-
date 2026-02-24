# DiningOut Editorial Scraper — Beginner Setup Guide

This guide assumes you've never done anything like this before. Every step is
explained in plain language. Budget about 45 minutes to go through the whole
thing.

**What we're doing:** Setting up a program on your computer that automatically
checks a bunch of websites (Google News, Reddit, Yelp, etc.) for food/restaurant
trends in Denver, Houston, Dallas, and Atlanta, then emails your team a nicely
formatted report every Monday morning.

---

## Before You Start — What You Need

- A Mac or Windows computer
- A web browser (Chrome, Safari, etc.)
- About 45 minutes
- You'll create free accounts on 2-3 websites (Reddit, Yelp, and optionally SendGrid)

---

## Part 1: Install Python (the programming language this tool runs on)

### On Mac:

1. Open the **Terminal** app
   - Press **Command + Space** to open Spotlight search
   - Type **Terminal** and press Enter
   - A window with a black or white background and a blinking cursor will open
   - **This is where you'll type commands throughout this guide**

2. Type this and press Enter:
   ```
   python3 --version
   ```
3. If you see something like `Python 3.11.6` — you already have Python. Skip to Part 2.
4. If you see "command not found" — you need to install Python:
   - Go to https://www.python.org/downloads/
   - Click the big yellow **"Download Python"** button
   - Open the downloaded file and follow the installer (just click "Continue" / "Agree" / "Install" through each screen)
   - Close and reopen Terminal, then try `python3 --version` again

### On Windows:

1. Open **Command Prompt**
   - Press the **Windows key** on your keyboard
   - Type **cmd** and press Enter
   - A black window with a blinking cursor will open
   - **This is where you'll type commands throughout this guide**

2. Type this and press Enter:
   ```
   python --version
   ```
3. If you see something like `Python 3.11.6` — you already have Python. Skip to Part 2.
4. If you see "not recognized" or it opens the Microsoft Store:
   - Go to https://www.python.org/downloads/
   - Click the big yellow **"Download Python"** button
   - Open the downloaded file
   - **IMPORTANT:** On the first screen, check the box that says **"Add Python to PATH"** (at the bottom) before clicking "Install Now"
   - Close and reopen Command Prompt, then try `python --version` again

---

## Part 2: Download This Project

You need to get the project files onto your computer.

### Easiest way — download as a ZIP:

1. Go to the GitHub page for this project
2. Click the green **"Code"** button
3. Click **"Download ZIP"**
4. Find the downloaded ZIP file (probably in your Downloads folder)
5. Unzip it (double-click on Mac, or right-click > "Extract All" on Windows)
6. You'll now have a folder called something like `Dining-out-editorial-scraper-tool-`

### Now open Terminal/Command Prompt and navigate to that folder:

**On Mac** (if the folder is in your Downloads):
```
cd ~/Downloads/Dining-out-editorial-scraper-tool-
```

**On Windows** (if the folder is in your Downloads):
```
cd C:\Users\YourName\Downloads\Dining-out-editorial-scraper-tool-
```
(Replace `YourName` with your actual Windows username)

**How to verify you're in the right folder:** Type `ls` (Mac) or `dir` (Windows) and press Enter. You should see files like `main.py`, `requirements.txt`, `PLAN.md`, etc.

---

## Part 3: Install the Tool's Dependencies

The tool needs some extra software packages. This one command installs all of them.

**On Mac**, type:
```
pip3 install -r requirements.txt
```

**On Windows**, type:
```
pip install -r requirements.txt
```

You'll see a bunch of text scrolling by — that's normal. Wait until it finishes and you see the blinking cursor again.

**If you see an error about `sgmllib3k`**, run this first, then try again:
```
pip3 install 'setuptools==67.8.0'
pip3 install -r requirements.txt
```
(On Windows, use `pip` instead of `pip3`)

---

## Part 4: Create Your Secrets File

The tool needs passwords and API keys to talk to Reddit, Yelp, and your email.
These go in a file called `.env` that stays on your computer and is never uploaded
anywhere.

**On Mac:**
```
cp .env.example .env
```

**On Windows:**
```
copy .env.example .env
```

Now open the `.env` file in a text editor:
- **On Mac:** `open -a TextEdit .env`
- **On Windows:** `notepad .env`

You'll see a file that looks like this:
```
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
YELP_API_KEY=your_yelp_api_key
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_HOST=smtp.gmail.com
```

**Leave this file open** — you'll paste in real values in the next steps.

---

## Part 5: Set Up Reddit (free, ~5 minutes)

Reddit lets you pull data from its site for free. You just need to register
your "app" with them so they know who's making the requests.

### Step 5a: Create a Reddit account (if you don't have one)

1. Go to https://www.reddit.com
2. Click **"Sign Up"** in the top right
3. Follow the prompts — you just need an email, username, and password
4. Verify your email if asked

### Step 5b: Register your app with Reddit

1. Make sure you're logged into Reddit
2. Go to this page: https://www.reddit.com/prefs/apps
3. Scroll all the way down to the bottom of the page
4. Click the button that says **"are you a developer? create an app..."** (or "create another app...")
5. You'll see a form. Fill it in exactly like this:

   | Field | What to type |
   |---|---|
   | **name** | `DiningOutScraper` |
   | **App type** | Click the circle next to **"script"** |
   | **description** | `Trend scraper for editorial team` |
   | **about url** | Leave blank |
   | **redirect uri** | `http://localhost:8080` |

6. Click **"create app"**

### Step 5c: Find your credentials

After clicking "create app", you'll see a box with your app info. Here's how to
find the two pieces of information you need:

```
DiningOutScraper
personal use script
aBcDeFgHiJkLmN          <--- THIS is your Client ID
                              (the random letters/numbers right under
                               "personal use script")

secret: xYz123AbC...    <--- THIS is your Client Secret
                              (the value after the word "secret")
```

### Step 5d: Paste them into your .env file

Go back to the `.env` file you opened earlier. Replace the placeholder text:

**Before:**
```
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
```

**After** (using your actual values):
```
REDDIT_CLIENT_ID=aBcDeFgHiJkLmN
REDDIT_CLIENT_SECRET=xYz123AbC456dEf789GhI
```

**Important:** No spaces around the `=` sign, and no quotes around the values.

---

## Part 6: Set Up Yelp (free, ~5 minutes)

Yelp lets you look up restaurant data through their API. The free tier gives you
500 lookups per day — we only need about 50 per week.

### Step 6a: Create a Yelp developer account

1. Go to https://www.yelp.com/developers
2. If you have a Yelp account, click **"Log In"**. If not, click **"Sign Up"**
3. After logging in, look for a button that says **"Create App"** or **"Get Started"**

### Step 6b: Create your app

Fill in the form:

| Field | What to type |
|---|---|
| **App Name** | `DiningOut Scraper` |
| **Industry** | Select `Journalism / Media` (or whatever's closest) |
| **Contact Email** | Your work email |
| **Description** | `Track restaurant trends for editorial coverage` |

Check the box to agree to the terms, then click **"Create New App"**.

### Step 6c: Get your API key

After creating the app, you'll see a page with your **API Key**. It's a long
string of random characters. It might look something like:
```
bEaR1a2b3c4d5e6f7g8h9i0jklmnopqrstuvwxyz
```

### Step 6d: Paste it into your .env file

In your `.env` file, replace:

**Before:**
```
YELP_API_KEY=your_yelp_api_key
```

**After:**
```
YELP_API_KEY=bEaR1a2b3c4d5e6f7g8h9i0jklmnopqrstuvwxyz
```

---

## Part 7: Set Up Email Sending (free, ~10 minutes)

The tool needs to send emails to your editorial team. The easiest way is to
use a Gmail account. The tool will send emails *from* this Gmail address.

**You can use your personal Gmail or create a new one just for this tool.**
Creating a new one (like `diningout.trends@gmail.com`) is a nice option because
the reports will come from a recognizable address.

### Step 7a: Turn on 2-Step Verification (if not already on)

Google requires this before they'll let you create an app password.

1. Go to https://myaccount.google.com/security
2. Look for **"2-Step Verification"** (it's under "How you sign in to Google")
3. If it says **"On"** — great, skip to Step 7b
4. If it says **"Off"** — click on it and follow the prompts:
   - Google will ask for your phone number
   - They'll send you a code via text message
   - Enter the code
   - Click "Turn On"
   - This takes about 2 minutes

### Step 7b: Create an App Password

An "App Password" is a special password that lets the scraper tool send emails
from your Gmail account. It's different from your regular Gmail password.

1. Go to https://myaccount.google.com/apppasswords
   - If that link doesn't work, go to: myaccount.google.com > Security > 2-Step Verification > scroll to the very bottom > "App passwords"
2. You'll see a page that says "App passwords"
3. In the text field that says **"App name"**, type: `DiningOut Scraper`
4. Click **"Create"**
5. A popup will appear showing a **16-character password** that looks like:
   ```
   abcd efgh ijkl mnop
   ```
6. **Copy this password** (write it down too — it's shown only this one time!)
   - Remove the spaces so it's just: `abcdefghijklmnop`

### Step 7c: Paste into your .env file

In your `.env` file, replace:

**Before:**
```
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_HOST=smtp.gmail.com
```

**After** (using your actual Gmail and the app password you just created):
```
SMTP_USER=diningout.trends@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
SMTP_HOST=smtp.gmail.com
```

### Step 7d: Save and close the .env file

Make sure you've saved the file (Ctrl+S on Windows, Command+S on Mac).

Your `.env` file should now look something like this (with your real values):
```
REDDIT_CLIENT_ID=aBcDeFgHiJkLmN
REDDIT_CLIENT_SECRET=xYz123AbC456dEf789GhI
YELP_API_KEY=bEaR1a2b3c4d5e6f7g8h9i0jklmnopqrstuvwxyz
SMTP_USER=diningout.trends@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
SMTP_HOST=smtp.gmail.com
```

---

## Part 8: Add Your Team's Email Addresses

Now you need to tell the tool who should receive the reports.

1. Open the file `config/config.yaml` in a text editor:
   - **On Mac:** `open -a TextEdit config/config.yaml`
   - **On Windows:** `notepad config\config.yaml`

2. Scroll down until you find this section (around line 93):
   ```
   email_recipients:
     # Add ~7 editorial staff emails here
     # - editor1@diningout.com
     # - editor2@diningout.com
   ```

3. Remove the `#` symbols and replace with your team's actual emails:
   ```
   email_recipients:
     - sarah@diningout.com
     - mike@diningout.com
     - jennifer@diningout.com
     - alex@diningout.com
     - chris@diningout.com
     - taylor@diningout.com
     - jordan@diningout.com
   ```

   **Important formatting rules:**
   - Each line must start with exactly **4 spaces**, then a **dash**, then a **space**, then the email
   - No tabs — only spaces
   - The `- ` (dash space) before each email is required

4. Also find this line (around line 85):
   ```
   email_from: "trends@diningout.com"
   ```
   Change it to match the Gmail you set up:
   ```
   email_from: "diningout.trends@gmail.com"
   ```

5. Save and close the file.

---

## Part 9: Test It

Now let's make sure everything works. Go back to your Terminal / Command Prompt.

**Make sure you're still in the project folder.** If you closed Terminal, reopen
it and navigate back:
- Mac: `cd ~/Downloads/Dining-out-editorial-scraper-tool-`
- Windows: `cd C:\Users\YourName\Downloads\Dining-out-editorial-scraper-tool-`

### Test 1: Check that all data sources are reachable

```
python3 main.py health
```
(On Windows, use `python` instead of `python3`)

You should see something like:
```
  news_rss: OK
  google_trends: OK
  reddit: OK
  tiktok: OK
  yelp: OK
  storage: {'total_items': 0, 'total_reports': 0, ...}
```

- **If reddit shows FAIL:** Go back to Part 5 and double-check the values in your `.env` file
- **If yelp shows FAIL:** Go back to Part 6 and double-check the API key
- **If tiktok shows FAIL:** That's OK! TikTok's data collection is "best effort" — the tool works fine without it

### Test 2: Collect data (no email sent yet)

```
python3 main.py collect
```

This goes out to all the sources and pulls in data. It takes about 1-2 minutes.
You should see a message like:
```
Collection complete: 247 items saved as run collect-20260224-143022-a1b2c3
```

The number of items will vary. Anything above 50 is good.

### Test 3: Preview the report

```
python3 main.py report -o test_report.html
```

This creates an HTML file you can open in your browser:
- **On Mac:** `open test_report.html`
- **On Windows:** `start test_report.html`

A web page will open showing the report. Check that:
- You see city sections (Denver, Houston, Dallas, Atlanta)
- There are story ideas at the top
- The "Competitor Watch" section has articles from Eater, Westword, etc.

### Test 4: Send yourself a test email

Before emailing the whole team, send one to yourself first.

1. Open `config/config.yaml` in a text editor
2. Temporarily change the recipients to just your email:
   ```
   email_recipients:
     - your.personal.email@gmail.com
   ```
3. Save the file
4. Run:
   ```
   python3 main.py run-weekly
   ```
5. Check your inbox (and your **spam/junk folder**) for the email
6. If it looks good, change the recipients back to your team's emails and save

---

## Part 10: Make It Run Automatically

Right now, the tool only runs when you manually type a command. Here's how to
make it run on its own every week.

### Easiest option: leave it running on your computer

```
python3 main.py schedule
```

This will:
- Send the weekly report every **Monday at 7:00 AM**
- Send a breaking news alert every **Wednesday at 12:00 PM** (only if there's actual breaking news)

**The catch:** Your computer needs to be on and not asleep for this to work.
It will keep running until you close the Terminal window or press **Ctrl+C**.

### Better option: ask your IT team

If DiningOut has an IT person or a server, ask them to set up a **cron job**
(that's the technical term for "run this on a schedule"). Show them this:

```
# Run these two commands on a schedule:
# Monday at 7am:    python3 /path/to/main.py run-weekly
# Wednesday at noon: python3 /path/to/main.py run-alert
```

They'll know what to do with that.

### Best option for non-technical users: GitHub Actions (free)

This runs the tool on GitHub's computers for free — no server needed, your
computer doesn't need to be on. Ask the developer who set this up (or a
technically-inclined team member) to create a GitHub Actions workflow.

---

## Customizing What the Tool Tracks

### Change which food topics are tracked

Open `config/config.yaml` and find the `keywords` section. Add or remove items:

```
keywords:
  - tacos
  - steak
  - fried chicken
  - seafood
  - cocktails
  - birria          # add new ones here
  - korean bbq      # like this
  - food truck
```

### Change when reports are sent

In the same file, find:
```
weekly_day: monday
weekly_time: "07:00"
midweek_day: wednesday
midweek_time: "12:00"
```

Change to whatever schedule you want. Times are in 24-hour format (so 2:00 PM = "14:00").

---

## If Something Goes Wrong

| What happened | What to do |
|---|---|
| "command not found" when typing `python3` | Python isn't installed. Go back to Part 1. |
| "No module named ..." | Run `pip3 install -r requirements.txt` again. |
| Reddit says FAIL | Check your `.env` file — make sure `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` match exactly what Reddit showed you. No extra spaces. |
| Yelp says FAIL | Same — check the `YELP_API_KEY` in `.env`. |
| No email received | Check your spam folder. If using Gmail, make sure you created an App Password (Part 7), not using your regular password. |
| Email says "authentication failed" | The app password in `.env` might be wrong. Go to https://myaccount.google.com/apppasswords and create a new one. |
| Report is empty | Run `python3 main.py collect` first to get data, then `python3 main.py report`. |
| TikTok shows FAIL | Normal — TikTok blocks automated access frequently. Everything else still works. |
| "Permission denied" | On Mac, try adding `sudo` before the command (it will ask for your computer password). |
| Something else broke | Take a screenshot of the error and send it to the person who set this up, or post it as a GitHub issue on the project. |
