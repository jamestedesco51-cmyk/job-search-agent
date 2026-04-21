#!/usr/bin/env python3
"""
James Tedesco - Daily Job Search Agent
Wide net version - finds roles across all public job boards dynamically.

Setup:
1. pip install requests beautifulsoup4 feedparser python-dateutil
2. Set environment variables:
   - EMAIL_TO: your personal email
   - EMAIL_FROM: gmail address to send from  
   - EMAIL_PASSWORD: gmail app password
     Get one at: https://myaccount.google.com/apppasswords
3. Cron: 0 8 * * * EMAIL_TO=x EMAIL_FROM=x EMAIL_PASSWORD=x python3 /path/to/job_agent.py
"""

import requests
import feedparser
import smtplib
import os
import re
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

# ─────────────────────────────────────────────
# PROFILE — your encodings and target roles
# ─────────────────────────────────────────────

TARGET_TITLES = [
    "brand partnerships manager",
    "creative partnerships manager",
    "partnerships manager",
    "brand manager",
    "head of partnerships",
    "collaborations manager",
    "head of collaborations",
    "marketing manager",
    "brand marketing manager",
    "go-to-market manager",
    "integrated marketing manager",
    "cultural marketing manager",
    "publisher relations manager",
    "content marketing manager",
    "campaign manager",
    "strategic partnerships",
    "business development manager",
    "gtm manager",
    "director of partnerships",
    "brand strategist",
    "influencer partnerships",
    "creator partnerships",
    "co-marketing manager",
    "commercial partnerships",
    "affiliate and partnerships",
    "community and partnerships",
    "collab manager",
    "brand and partnerships",
    "growth partnerships",
    "media partnerships",
]

TARGET_INDUSTRIES = [
    "gaming", "game", "indie game", "publisher", "esports",
    "consumer", "dtc", "direct to consumer", "lifestyle", "wellness", "cpg",
    "media", "entertainment", "editorial", "streaming", "creator economy",
    "fashion", "apparel", "food", "beverage", "spirits", "alcohol",
    "mental health", "health", "fitness", "beauty", "skincare",
    "travel", "hospitality", "culture", "music", "sports", "outdoor",
    "sustainability", "cannabis", "web3", "creator", "influencer",
]

GOOD_SIGNALS = TARGET_TITLES + TARGET_INDUSTRIES + [
    "austin", "remote", "hybrid", "brand building", "partnership program",
    "go-to-market", "gtm", "collab", "collaboration", "campaign execution",
    "product launch", "brand strategy", "consumer brand", "startup",
    "early stage", "series a", "series b", "growth stage",
]

BAD_SIGNALS = [
    "software engineer", "data engineer", "devops", "machine learning",
    "data scientist", "backend", "frontend engineer", "ios developer",
    "android developer", "java", "kubernetes", "aws engineer",
    "clinical", "nurse", "physician", "pharmacist", "radiologist",
    "accountant", "cpa", "tax manager", "bookkeeper",
    "supply chain", "warehouse", "logistics", "truck driver",
    "real estate agent", "insurance agent", "loan officer",
    "braze admin", "salesforce developer", "sql developer",
    "lifecycle marketing manager", "crm manager",
]

TARGET_COMPANIES = [
    # gaming
    "aspyr", "midwest games", "popagenda", "riot games", "epic games",
    "devolver digital", "annapurna interactive", "raw fury", "fellow traveller",
    "humble games", "dexerto", "fandom", "crunchyroll", "ign",
    # dtc / consumer
    "fishwife", "graza", "ghia", "brightland", "fly by jing",
    "diaspora co", "omsom", "vacation inc", "cuts clothing", "madhappy",
    "olipop", "liquid death", "momentous", "beam", "kin euphorics",
    "everyday dose", "heart and soil", "athletic greens", "seed health",
    "thesis", "supergoop", "summer fridays",
    # lifestyle / outdoor
    "howler brothers", "patagonia", "cotopaxi", "allbirds", "vuori",
    "tracksmith", "satisfy running", "kith", "aimé leon dore",
    # mental health / wellness  
    "wondermind", "calm", "headspace", "two chairs", "cerebral",
    "spring health", "brightside",
    # media / entertainment
    "a24", "spotify", "substack", "axios", "the ringer",
    "complex networks", "hypebeast", "high snobiety",
]

SEARCH_QUERIES = [
    "brand partnerships manager",
    "creative partnerships manager",
    "partnerships manager DTC",
    "partnerships manager gaming",
    "brand manager gaming",
    "brand manager lifestyle",
    "brand manager consumer",
    "collaborations manager",
    "head of collaborations",
    "head of partnerships",
    "influencer partnerships manager",
    "creator partnerships manager",
    "go-to-market manager",
    "integrated marketing manager",
    "cultural marketing manager",
    "campaign manager entertainment",
    "brand strategy manager",
    "content marketing manager lifestyle",
    "marketing manager indie games",
    "business development manager media",
    "strategic partnerships media",
    "publisher relations manager",
    "brand marketing manager consumer",
    "partnerships manager wellness",
    "brand manager DTC startup",
    "collab manager fashion",
    "media partnerships manager",
    "growth partnerships manager",
    "brand and partnerships",
]

MAX_AGE_DAYS = 8
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

EMAIL_TO = os.environ.get("EMAIL_TO", "your@email.com")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "sender@gmail.com")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def is_recent(date_str):
    if not date_str:
        return True
    try:
        posted = dateparser.parse(str(date_str))
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - posted
        return age.days <= MAX_AGE_DAYS
    except:
        return True

def score_job(title, description="", company=""):
    score = 0
    text = f"{title} {description} {company}".lower()
    title_lower = title.lower()

    # Strong title match
    for t in TARGET_TITLES:
        if t in title_lower:
            score += 4
        elif t in text:
            score += 2

    # Industry match
    for ind in TARGET_INDUSTRIES:
        if ind in text:
            score += 1

    # Target company match
    for co in TARGET_COMPANIES:
        if co in company.lower():
            score += 5

    # Bad signal penalty
    for kw in BAD_SIGNALS:
        if kw in text:
            score -= 5

    # Location boost
    if "austin" in text or "remote" in text or "hybrid" in text:
        score += 1

    return score

jobs = []
seen_urls = set()

def add_job(title, company, url, date_str="", source="", description=""):
    if not title or not url:
        return
    if url in seen_urls:
        return
    if not is_recent(date_str):
        return
    score = score_job(title, description, company)
    if score < 2:
        return
    seen_urls.add(url)
    jobs.append({
        "title": title.strip(),
        "company": company.strip(),
        "url": url.strip(),
        "date": str(date_str)[:10] if date_str else "",
        "source": source,
        "score": score,
        "description": description[:250].strip() if description else ""
    })

# ─────────────────────────────────────────────
# SCRAPERS — cast the widest possible net
# ─────────────────────────────────────────────

def scrape_indeed():
    print("  Scraping Indeed...")
    for q in SEARCH_QUERIES:
        try:
            encoded = q.replace(" ", "+")
            for loc in ["Austin%2C+TX", "remote"]:
                url = f"https://www.indeed.com/rss?q={encoded}&l={loc}&sort=date&fromage=7"
                feed = feedparser.parse(url)
                for entry in feed.entries[:10]:
                    add_job(
                        title=entry.get("title", ""),
                        company=entry.get("source", {}).get("title", ""),
                        url=entry.get("link", ""),
                        date_str=entry.get("published", ""),
                        source="Indeed",
                        description=BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()
                    )
        except Exception as e:
            pass

def scrape_wellfound():
    print("  Scraping Wellfound...")
    role_slugs = [
        "brand-partnerships", "partnerships-manager", "brand-manager",
        "creative-partnerships", "collaborations", "marketing-manager",
        "business-development", "go-to-market", "influencer-marketing",
        "creator-partnerships", "content-marketing", "campaign-manager",
        "brand-strategy", "growth-marketing", "media-partnerships",
        "publisher-relations", "integrated-marketing",
    ]
    for slug in role_slugs:
        try:
            url = f"https://wellfound.com/jobs?role={slug}&remote=true"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.select("[data-test='JobListing']")[:10]:
                title = card.select_one("[data-test='JobListing-title']")
                company = card.select_one("[data-test='JobListing-company']")
                link = card.select_one("a")
                date = card.select_one("time")
                add_job(
                    title=title.text.strip() if title else "",
                    company=company.text.strip() if company else "",
                    url="https://wellfound.com" + link["href"] if link else url,
                    date_str=date.get("datetime", "") if date else "",
                    source="Wellfound"
                )
        except Exception as e:
            pass

def scrape_hitmarker():
    print("  Scraping Hitmarker...")
    try:
        feed = feedparser.parse("https://hitmarker.net/jobs/rss")
        for entry in feed.entries[:40]:
            add_job(
                title=entry.get("title", ""),
                company=entry.get("author", ""),
                url=entry.get("link", ""),
                date_str=entry.get("published", ""),
                source="Hitmarker",
                description=BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()
            )
    except Exception as e:
        pass

def scrape_gamesindustry():
    print("  Scraping GamesIndustry.biz...")
    try:
        feed = feedparser.parse("https://www.gamesindustry.biz/jobs/rss")
        for entry in feed.entries[:40]:
            add_job(
                title=entry.get("title", ""),
                company=entry.get("author", ""),
                url=entry.get("link", ""),
                date_str=entry.get("published", ""),
                source="GamesIndustry.biz",
                description=BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()
            )
    except Exception as e:
        pass

def scrape_builtin():
    print("  Scraping Built In...")
    slugs = [
        "partnerships", "brand-manager", "marketing-manager",
        "business-development", "content-marketing", "campaign-manager",
        "brand-strategy", "go-to-market", "creative-director",
    ]
    for slug in slugs:
        for city in ["austin", "remote"]:
            try:
                url = f"https://builtin.com/jobs/{city}/{slug}?sortBy=newest"
                resp = requests.get(url, headers=HEADERS, timeout=10)
                soup = BeautifulSoup(resp.text, "html.parser")
                for card in soup.select("[data-id]")[:10]:
                    title = card.select_one("h2")
                    company = card.select_one("[data-testid='company-name']")
                    link = card.select_one("a")
                    add_job(
                        title=title.text.strip() if title else "",
                        company=company.text.strip() if company else "",
                        url="https://builtin.com" + link["href"] if link else url,
                        source=f"Built In ({city.title()})"
                    )
            except Exception as e:
                pass

def scrape_hiring_cafe():
    print("  Scraping Hiring Cafe...")
    queries = [
        "brand-partnerships", "partnerships-manager", "brand-manager",
        "collaborations", "creative-partnerships", "go-to-market",
        "marketing-manager-lifestyle", "influencer-partnerships",
        "content-marketing-manager", "brand-strategy",
    ]
    for q in queries:
        try:
            url = f"https://hiring.cafe/search?q={q}&remote=true&sort=newest"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.select(".job-card, [class*='job'], [class*='listing']")[:10]:
                title_el = card.select_one("h2, h3, [class*='title']")
                company_el = card.select_one("[class*='company'], [class*='employer']")
                link_el = card.select_one("a")
                date_el = card.select_one("time, [class*='date']")
                if title_el:
                    href = link_el.get("href", "") if link_el else ""
                    full_url = f"https://hiring.cafe{href}" if href.startswith("/") else href or url
                    add_job(
                        title=title_el.text.strip(),
                        company=company_el.text.strip() if company_el else "",
                        url=full_url,
                        date_str=date_el.get("datetime", "") if date_el else "",
                        source="Hiring Cafe"
                    )
        except Exception as e:
            pass

def scrape_wttj():
    print("  Scraping Welcome to the Jungle...")
    queries = [
        "brand-partnerships", "partnerships-manager", "brand-manager",
        "collaborations", "creative-partnerships", "marketing-manager",
        "go-to-market", "influencer-partnerships", "content-marketing",
        "campaign-manager", "brand-strategy", "cultural-marketing",
    ]
    for q in queries:
        try:
            url = f"https://www.welcometothejungle.com/en/jobs?query={q}&aroundQuery=remote&sortBy=mostRecent"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.select("[data-testid='job-list-item'], [class*='JobCard']")[:10]:
                title_el = card.select_one("h3, h4, [class*='title'], [data-testid='job-title']")
                company_el = card.select_one("[class*='company'], [data-testid='company-name']")
                link_el = card.select_one("a")
                date_el = card.select_one("time")
                if title_el:
                    href = link_el.get("href", "") if link_el else ""
                    full_url = f"https://www.welcometothejungle.com{href}" if href.startswith("/") else href or url
                    add_job(
                        title=title_el.text.strip(),
                        company=company_el.text.strip() if company_el else "",
                        url=full_url,
                        date_str=date_el.get("datetime", "") if date_el else "",
                        source="Welcome to the Jungle"
                    )
        except Exception as e:
            pass

def scrape_workable():
    print("  Scraping Workable...")
    for q in ["brand partnerships", "partnerships manager", "brand manager", "collaborations", "go-to-market", "influencer partnerships"]:
        try:
            url = f"https://apply.workable.com/api/v1/widget/jobs?query={q.replace(' ', '%20')}"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            data = resp.json()
            for job in data.get("jobs", [])[:15]:
                add_job(
                    title=job.get("title", ""),
                    company=job.get("company", {}).get("name", ""),
                    url=job.get("url", ""),
                    date_str=job.get("published_on", ""),
                    source="Workable"
                )
        except Exception as e:
            pass

def scrape_lever():
    print("  Scraping Lever career pages...")
    # Expanded list of companies likely on Lever
    companies = [
        "calm", "headspace", "wondermind", "graza", "cuts",
        "madhappy", "vacation", "olipop", "liquid-death",
        "athletic-greens", "seed-health", "two-chairs",
        "cerebral", "spring-health", "fishwife", "ghia",
        "brightland", "fly-by-jing", "kin-euphorics",
        "hypebeast", "high-snobiety", "the-ringer",
        "axios", "substack", "a24", "spotify",
        "riot-games", "epic-games", "devolver-digital",
        "raw-fury", "annapurna-interactive", "humble-games",
        "patagonia", "cotopaxi", "allbirds", "vuori",
        "tracksmith", "momentous", "beam-organics",
        "everyday-dose", "heart-and-soil",
    ]
    for company in companies:
        try:
            url = f"https://jobs.lever.co/{company}"
            resp = requests.get(url, headers=HEADERS, timeout=8)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for posting in soup.select(".posting")[:8]:
                title_el = posting.select_one(".posting-name")
                link_el = posting.select_one("a.posting-title")
                if title_el:
                    add_job(
                        title=title_el.text.strip(),
                        company=company.replace("-", " ").title(),
                        url=link_el["href"] if link_el else url,
                        source="Lever (Direct)"
                    )
        except Exception as e:
            pass

def scrape_greenhouse():
    print("  Scraping Greenhouse career pages...")
    companies = [
        "aspyr", "riotgames", "epicgames", "fandom",
        "crunchyroll", "calm", "headspace", "spotify",
        "howlerbros", "cuts", "allbirds", "vuori",
        "madhappy", "momentous", "two-chairs",
        "spring-health", "cerebral", "wondermind",
        "axios", "theringer", "hypebeast",
        "devolverdidital", "rawfury", "humbleBundle",
    ]
    for company in companies:
        try:
            url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true"
            resp = requests.get(url, headers=HEADERS, timeout=8)
            if resp.status_code != 200:
                continue
            data = resp.json()
            for job in data.get("jobs", [])[:8]:
                add_job(
                    title=job.get("title", ""),
                    company=company.replace("-", " ").title(),
                    url=job.get("absolute_url", ""),
                    date_str=job.get("updated_at", ""),
                    source="Greenhouse (Direct)",
                    description=BeautifulSoup(job.get("content", ""), "html.parser").get_text()[:300]
                )
        except Exception as e:
            pass

def scrape_ashby():
    print("  Scraping Ashby career pages...")
    companies = [
        "fishwife", "ghia", "graza", "brightland",
        "everyday-dose", "heart-and-soil", "momentous",
        "beam", "two-chairs", "fly-by-jing", "olipop",
        "kin-euphorics", "thesis", "seed", "ritual",
        "supergoop", "summer-fridays", "vacation-inc",
        "liquid-death", "madhappy", "cuts",
    ]
    for company in companies:
        try:
            url = f"https://jobs.ashbyhq.com/{company}"
            resp = requests.get(url, headers=HEADERS, timeout=8)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.select("[class*='job'], [class*='posting'], [class*='listing']")[:8]:
                title_el = card.select_one("h3, h4, [class*='title']")
                link_el = card.select_one("a")
                if title_el:
                    href = link_el.get("href", "") if link_el else ""
                    full_url = f"https://jobs.ashbyhq.com{href}" if href.startswith("/") else href or url
                    add_job(
                        title=title_el.text.strip(),
                        company=company.replace("-", " ").title(),
                        url=full_url,
                        source="Ashby (Direct)"
                    )
        except Exception as e:
            pass

def scrape_direct_career_pages():
    print("  Scraping direct career pages...")
    pages = {
        "Aspyr": "https://www.aspyr.com/open_positions",
        "Midwest Games": "https://www.midwestgames.com/contact",
        "Heart and Soil": "https://heartandsoil.co/careers/",
        "Everyday Dose": "https://apply.workable.com/everyday-dose-inc/",
        "Howler Brothers": "https://www.howlerbros.com/pages/careers",
        "Fishwife": "https://www.eatfishwife.com/pages/careers",
        "Graza": "https://www.graza.co/pages/jobs",
        "Ghia": "https://drinkghia.com/pages/jobs",
        "Wondermind": "https://www.wondermind.com/careers",
        "Calm": "https://www.calm.com/careers",
        "Headspace": "https://www.headspace.com/careers",
        "Cuts Clothing": "https://www.cuts.com/pages/careers",
        "Madhappy": "https://madhappy.com/pages/careers",
        "Vacation Inc": "https://vacation.inc/pages/jobs",
        "Olipop": "https://drinkolipop.com/pages/careers",
        "Liquid Death": "https://liquiddeath.com/pages/jobs",
        "Momentous": "https://livemomentous.com/pages/careers",
        "Patagonia": "https://www.patagonia.com/jobs/",
        "Cotopaxi": "https://www.cotopaxi.com/pages/careers",
        "Tracksmith": "https://www.tracksmith.com/pages/careers",
        "Vuori": "https://vuoriclothing.com/pages/careers",
        "Brightland": "https://www.brightland.co/pages/careers",
        "Supergoop": "https://www.supergoop.com/pages/careers",
        "Summer Fridays": "https://www.summerfridays.com/pages/careers",
        "Kin Euphorics": "https://www.kineuphoric.com/pages/careers",
        "Popagenda": "https://popagenda.co",
        "Two Chairs": "https://www.twochairs.com/careers",
        "Spring Health": "https://springhealth.com/careers/",
    }
    for company, url in pages.items():
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text().lower()
            for title_kw in TARGET_TITLES:
                if title_kw in text:
                    add_job(
                        title=title_kw.title(),
                        company=company,
                        url=url,
                        source="Direct Career Page",
                        description=f"Matching role found on {company} careers page"
                    )
                    break
        except Exception as e:
            pass

def scrape_substacks():
    print("  Scraping Substack newsletters...")
    feeds = [
        ("Words of Mouth", "https://wordsofmouth.substack.com/feed"),
        ("Lenny's Newsletter", "https://www.lennysnewsletter.com/feed"),
        ("The Hustle", "https://thehustle.co/feed/"),
        ("Marketing Brew", "https://www.marketingbrew.com/rss"),
        ("Games Industry Daily", "https://gamesindustry.substack.com/feed"),
        ("CPG Insiders", "https://cpginsiders.substack.com/feed"),
        ("DTC Newsletter", "https://dtcnewsletter.com/feed/"),
        ("Demand Curve", "https://www.demandcurve.com/blog/feed"),
    ]
    for name, url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
                content = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text().lower()
                title_text = entry.get("title", "").lower()
                for title_kw in TARGET_TITLES:
                    if title_kw in content or title_kw in title_text:
                        add_job(
                            title=f"Job mention: {title_kw.title()}",
                            company=name,
                            url=entry.get("link", ""),
                            date_str=entry.get("published", ""),
                            source=f"Substack: {name}",
                            description=entry.get("title", "")
                        )
                        break
        except Exception as e:
            pass

# ─────────────────────────────────────────────
# RUN ALL SCRAPERS
# ─────────────────────────────────────────────

print("James Tedesco Job Agent - Starting...")
print(f"Looking for roles posted in the last {MAX_AGE_DAYS} days\n")

scrape_indeed()
scrape_wellfound()
scrape_hitmarker()
scrape_gamesindustry()
scrape_builtin()
scrape_hiring_cafe()
scrape_wttj()
scrape_workable()
scrape_lever()
scrape_greenhouse()
scrape_ashby()
scrape_direct_career_pages()
scrape_substacks()

jobs.sort(key=lambda x: x["score"], reverse=True)
top_jobs = jobs[:30]

print(f"\nDone. Found {len(jobs)} relevant roles. Sending top {len(top_jobs)}.\n")

# ─────────────────────────────────────────────
# BUILD + SEND EMAIL
# ─────────────────────────────────────────────

today = datetime.now().strftime("%A, %B %d")

html_rows = ""
for job in top_jobs:
    fit = "Strong Fit" if job["score"] >= 8 else "Good Fit" if job["score"] >= 5 else "Worth a Look"
    fit_color = "#1a7a1a" if job["score"] >= 8 else "#7a5a1a" if job["score"] >= 5 else "#555"
    html_rows += f"""
    <tr style="border-bottom: 1px solid #f0f0f0;">
        <td style="padding: 14px 10px;">
            <a href="{job['url']}" style="color: #1a1a1a; font-weight: 600; font-size: 15px; text-decoration: none;">{job['title']}</a><br>
            <span style="color: #555; font-size: 13px;">{job['company']}</span>
            {"<br><span style='color: #999; font-size: 12px; font-style: italic;'>" + job['description'][:120] + "...</span>" if job['description'] else ""}
        </td>
        <td style="padding: 14px 10px; font-size: 12px; color: {fit_color}; font-weight: 600; white-space: nowrap;">{fit}</td>
        <td style="padding: 14px 10px; font-size: 12px; color: #888; white-space: nowrap;">{job['source']}</td>
        <td style="padding: 14px 10px; font-size: 12px; color: #aaa; white-space: nowrap;">{job['date']}</td>
    </tr>"""

no_jobs_msg = '<tr><td colspan="4" style="padding: 30px; color: #aaa; text-align: center; font-style: italic;">No new matching roles today. Check back tomorrow.</td></tr>'

html_body = f"""<html><body style="font-family: Arial, sans-serif; max-width: 860px; margin: 0 auto; padding: 28px; color: #1a1a1a; background: #fff;">
<h2 style="border-bottom: 3px solid #1a1a1a; padding-bottom: 12px; margin-bottom: 4px; font-size: 22px;">Job Digest</h2>
<p style="color: #888; font-size: 13px; margin: 4px 0 20px;">{today} &nbsp;·&nbsp; {len(jobs)} roles found &nbsp;·&nbsp; Top {len(top_jobs)} shown &nbsp;·&nbsp; Last {MAX_AGE_DAYS} days only</p>
<table style="width: 100%; border-collapse: collapse; font-size: 14px;">
<thead><tr style="background: #f8f8f8; font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; color: #888;">
<th style="padding: 10px; text-align: left;">Role</th>
<th style="padding: 10px; text-align: left;">Fit</th>
<th style="padding: 10px; text-align: left;">Source</th>
<th style="padding: 10px; text-align: left;">Posted</th>
</tr></thead>
<tbody>{html_rows if html_rows else no_jobs_msg}</tbody>
</table>
<hr style="margin: 32px 0; border: none; border-top: 1px solid #eee;">
<p style="color: #ccc; font-size: 11px; line-height: 1.8;">
Sources: Indeed · Wellfound · Hitmarker · GamesIndustry.biz · Built In · Hiring Cafe · Welcome to the Jungle · Workable · Lever · Greenhouse · Ashby · 28 Direct Career Pages · 8 Substack Feeds<br>
Roles: Brand Partnerships · Creative Partnerships · Brand Manager · Collaborations · Campaign Manager · GTM · Business Development · Content Marketing · Cultural Marketing<br>
Industries: Gaming · DTC · Lifestyle · Wellness · CPG · Media · Entertainment · Fashion · Mental Health · Travel · Creator Economy
</p></body></html>"""

if not EMAIL_PASSWORD:
    print("No EMAIL_PASSWORD set. Printing results:\n")
    for job in top_jobs:
        print(f"[score:{job['score']}] {job['title']} @ {job['company']}")
        print(f"  Source: {job['source']}")
        print(f"  URL: {job['url']}\n")
else:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Job Digest - {today} ({len(top_jobs)} roles)"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html_body, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print(f"Digest sent to {EMAIL_TO}")
    except Exception as e:
        print(f"Email error: {e}")
        for job in top_jobs:
            print(f"[{job['score']}] {job['title']} @ {job['company']} -- {job['url']}")
