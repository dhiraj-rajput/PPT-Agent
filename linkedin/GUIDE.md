# LinkedIn Authenticated Scraping — Setup Guide

This guide explains how to enable Layer 3 (authenticated scraping) which
gives access to significantly more LinkedIn company data.

---

## ⚠️ Important Warning

> **Never use your primary LinkedIn account for scraping.**  
> LinkedIn monitors for automated behavior and can permanently ban accounts.
> Use a dedicated burner account that you're comfortable losing.

---

## Part 1: Creating a Burner LinkedIn Account

### Step 1: Set Up a New Email Address
Create a new email address that is **not linked to your real identity**.
Free options:
- Gmail (gmail.com)
- ProtonMail (proton.me) — more privacy-focused
- Temp email services are **not recommended** (LinkedIn blocks them)

### Step 2: Create the LinkedIn Account
1. Go to [linkedin.com/signup](https://www.linkedin.com/signup)
2. Register with your new email address
3. Use a **fictional name** (e.g., "Alex Johnson")
4. Use a **stock photo** or generated face as a profile picture
   - Free AI-generated faces: [thispersondoesnotexist.com](https://thispersondoesnotexist.com)
5. Set a **realistic job title** (e.g., "Business Analyst at Consulting Firm")
6. Add 1-2 connections if possible (makes the account look legitimate)

### Step 3: Warm Up the Account
Before using the account for scraping:
- Log in manually and browse normally for **2-3 days**
- View a few profiles and company pages
- This reduces the chance of being flagged immediately

---

## Part 2: Extracting the `li_at` Session Cookie

The `li_at` cookie is LinkedIn's primary session authentication token.
Once we have it, our scraper can make requests that appear to come from
a logged-in user.

### Steps (Google Chrome):
1. Log into LinkedIn with your **burner account** in Chrome
2. Press `F12` to open DevTools (or right-click → "Inspect")
3. Click the **"Application"** tab
4. In the left sidebar, expand **"Cookies"** → click **"https://www.linkedin.com"**
5. Find the cookie named **`li_at`** in the list
6. Right-click its **Value** field → **"Copy value"**

### Steps (Firefox):
1. Log in to LinkedIn in Firefox
2. Press `F12` → click **"Storage"** tab
3. Expand **"Cookies"** → click **"https://www.linkedin.com"**
4. Find `li_at` → copy the value from the "Value" column

### Add to Your `.env` File:
```env
LINKEDIN_LI_AT=AQEDAQoAAAGX...your_very_long_cookie_value_here...
```

> **Note:** The `li_at` cookie expires periodically (usually every few weeks).
> If scraping stops working, repeat this process to get a fresh cookie.

---

## Part 3: Using a Proxy (Optional but Recommended)

Using a proxy routes your scraping traffic through a different IP address,
reducing the risk of your home/office IP being blocked by LinkedIn.

### Free Options (Limited)
Free proxies are generally **not recommended** for LinkedIn because:
- They are slow and unreliable
- LinkedIn detects them quickly
- They may expose your traffic to the proxy operator

### Recommended: Residential Proxy Services
These rotate IP addresses automatically and are much harder for LinkedIn to detect:

| Service | Price | Notes |
|---------|-------|-------|
| [BrightData](https://brightdata.com) | Paid (~$10-15/GB) | Industry standard, very reliable |
| [Oxylabs](https://oxylabs.io) | Paid | Good for LinkedIn specifically |
| [SmartProxy](https://smartproxy.com) | Paid | Cheaper option |

### Using a Proxy with the Scraper
Once you have a proxy, add it to your `.env` file:

```env
# HTTP proxy format: http://user:password@proxy-host:port
# SOCKS5 proxy format: socks5://user:password@proxy-host:port
SCRAPING_PROXY_URL=http://username:password@proxy.example.com:8888
```

Then update `authenticated_scraper.py` to pass the proxy to Playwright:

```python
browser = await playwright_instance.chromium.launch(
    headless=settings.BROWSER_HEADLESS,
    proxy={"server": settings.SCRAPING_PROXY_URL},
    args=["--disable-blink-features=AutomationControlled"],
)
```

---

## Part 4: Using `curl` / `curl-impersonate`

As an alternative to Playwright, you can use `curl-impersonate` which
mimics real browser TLS fingerprints (making requests look like Chrome/Firefox).

### Installation (Windows via WSL or Linux):
```bash
pip install curl-cffi
```

### Basic Usage in Python:
```python
from curl_cffi import requests as curl_requests

response = curl_requests.get(
    "https://www.linkedin.com/company/infosys",
    impersonate="chrome120",   # Mimics Chrome 120
    cookies={"li_at": "your_li_at_value_here"},
    headers={"Accept-Language": "en-US,en;q=0.9"},
)

html_content = response.text
```

This is **faster** than Playwright and uses **less memory**, but only works for
pages that don't require JavaScript execution to load their content.
For fully JS-rendered pages, Playwright (Layer 3) is still needed.

---

## Part 5: Cookie Rotation Strategy

If you're scraping many companies, rotate between multiple `li_at` cookies
to distribute the load across accounts:

```python
# In your .env file
LINKEDIN_LI_AT_1=your_first_cookie_here
LINKEDIN_LI_AT_2=your_second_cookie_here
LINKEDIN_LI_AT_3=your_third_cookie_here
```

Then rotate them in the authenticated scraper based on the company being scraped.

---

## Troubleshooting

| Problem | Likely Cause | Solution |
|---------|-------------|----------|
| "Please sign in" page appears | `li_at` cookie expired | Get a fresh cookie |
| Account requires CAPTCHA | Account flagged as suspicious | Use a proxy, reduce scraping frequency |
| Account permanently banned | Too much scraping | Create a new burner account |
| Empty page content | JavaScript not loaded | Increase `PAGE_LOAD_WAIT_MS` in `authenticated_scraper.py` |
| Rate limited (429) | Too many requests | Increase delay settings in `.env` |

---

## Recommended Scraping Frequency

To minimize the risk of account bans, stay within these limits:

- **Max 50 company pages per day** per account
- **Delay between requests**: 3-8 seconds (configured in `.env`)
- **Delay between companies**: at least 30 seconds
- **Maximum daily scrape time**: 2-3 hours

These limits are conservative but significantly reduce the risk of bans.
