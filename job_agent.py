#!/usr/bin/env python3
"""
James Tedesco - Job Search + Consulting Prospect Agent
Scrapes job boards and discovers consulting prospects.
Writes jobs.json, prospects.json, and meta.json for the dashboard.

Setup:
1. pip install requests beautifulsoup4 feedparser python-dateutil
2. Set environment variables (all optional):
   - EMAIL_TO / EMAIL_FROM / EMAIL_PASSWORD  ->  send digest email
   - GITHUB_WORKSPACE                        ->  where to write JSON (defaults to ".")
3. Cron: 0 13 * * * python3 /path/to/job_agent.py
"""

import requests
import feedparser
import smtplib
import os
import re
import json
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

# ─────────────────────────────────────────────
# CONFIG
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
    "gtm manager",
    "integrated marketing manager",
    "cultural marketing manager",
    "publisher relations manager",
    "content marketing manager",
    "campaign manager",
    "strategic partnerships",
    "business development manager",
    "director of partnerships",
    "brand strategist",
    "influencer partnerships",
    "creator partnerships",
    "co-marketing manager",
    "commercial partnerships",
    "collab manager",
    "brand and partnerships",
    "growth partnerships",
    "media partnerships",
    "creative operator",
    "brand operator",
]

TARGET_INDUSTRIES = [
    "gaming", "game", "indie game", "publisher", "esports",
    "consumer", "dtc", "direct to consumer", "lifestyle", "wellness", "cpg",
    "media", "entertainment", "editorial", "streaming", "creator economy",
    "fashion", "apparel", "food", "beverage", "spirits",
    "mental health", "health", "fitness", "beauty", "skincare",
    "travel", "hospitality", "culture", "music", "sports", "outdoor",
    "sustainability", "creator", "influencer",
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
    "tracksmith", "satisfy running", "kith",
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
]

MAX_AGE_DAYS = 8
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

OUTPUT_DIR = os.environ.get("GITHUB_WORKSPACE", ".")
EMAIL_TO = os.environ.get("EMAIL_TO", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")

# ─────────────────────────────────────────────
# JOB HELPERS
# ─────────────────────────────────────────────

def is_recent(date_str):
    if not date_str:
        return True
    try:
        posted = dateparser.parse(str(date_str))
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - posted).days <= MAX_AGE_DAYS
    except Exception:
        return True

def score_job(title, description="", company=""):
    score = 0
    text = f"{title} {description} {company}".lower()
    title_lower = title.lower()

    for t in TARGET_TITLES:
        if t in title_lower:
            score += 4
        elif t in text:
            score += 2

    for ind in TARGET_INDUSTRIES:
        if ind in text:
            score += 1

    for co in TARGET_COMPANIES:
        if co in company.lower():
            score += 5

    for kw in BAD_SIGNALS:
        if kw in text:
            score -= 5

    if "austin" in text or "remote" in text or "hybrid" in text:
        score += 1

    return score

def make_job_id(title, company, url=""):
    raw = f"{company}-{title}-{url}"
    return re.sub(r"[^a-z0-9]", "-", raw.lower())[:48].strip("-")

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
        "id": make_job_id(title, company, url),
        "title": title.strip(),
        "company": company.strip(),
        "url": url.strip(),
        "date": str(date_str)[:10] if date_str else "",
        "source": source,
        "score": score,
        "description": description[:280].strip() if description else "",
    })

# ─────────────────────────────────────────────
# JOB SCRAPERS
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
                        description=BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(),
                    )
        except Exception:
            pass

def scrape_glassdoor():
    print("  Scraping Glassdoor...")
    for q in SEARCH_QUERIES[:8]:
        try:
            encoded = q.replace(" ", "%20")
            url = f"https://www.glassdoor.com/Job/jobs.htm?sc.keyword={encoded}&locT=C&locId=1139761&sortBy=date_desc"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.select("[data-test='jobListing'], .react-job-listing")[:8]:
                title_el = card.select_one("[data-test='job-title'], .job-title")
                company_el = card.select_one("[data-test='employer-name'], .employer-name")
                link_el = card.select_one("a")
                if title_el:
                    href = link_el.get("href", "") if link_el else ""
                    full_url = ("https://www.glassdoor.com" + href) if href.startswith("/") else href or url
                    add_job(
                        title=title_el.text.strip(),
                        company=company_el.text.strip() if company_el else "",
                        url=full_url,
                        source="Glassdoor",
                    )
        except Exception:
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
                    source="Wellfound",
                )
        except Exception:
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
                description=BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(),
            )
    except Exception:
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
                description=BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(),
            )
    except Exception:
        pass

def scrape_builtin():
    print("  Scraping Built In Austin...")
    slugs = [
        "partnerships", "brand-manager", "marketing-manager",
        "business-development", "content-marketing", "campaign-manager",
        "brand-strategy", "go-to-market",
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
                        source=f"Built In ({city.title()})",
                    )
            except Exception:
                pass

def scrape_hiring_cafe():
    print("  Scraping Hiring Cafe...")
    queries = [
        "brand-partnerships", "partnerships-manager", "brand-manager",
        "collaborations", "creative-partnerships", "go-to-market",
        "influencer-partnerships", "content-marketing-manager",
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
                        source="Hiring Cafe",
                    )
        except Exception:
            pass

def scrape_wttj():
    print("  Scraping Welcome to the Jungle...")
    queries = [
        "brand-partnerships", "partnerships-manager", "brand-manager",
        "collaborations", "marketing-manager", "go-to-market",
        "influencer-partnerships", "content-marketing", "campaign-manager",
        "cultural-marketing",
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
                        source="Welcome to the Jungle",
                    )
        except Exception:
            pass

def scrape_workable():
    print("  Scraping Workable...")
    for q in ["brand partnerships", "partnerships manager", "brand manager", "collaborations", "go-to-market"]:
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
                    source="Workable",
                )
        except Exception:
            pass

def scrape_lever():
    print("  Scraping Lever career pages...")
    companies = [
        "calm", "headspace", "wondermind", "graza", "cuts", "madhappy",
        "vacation", "olipop", "liquid-death", "athletic-greens", "seed-health",
        "two-chairs", "cerebral", "spring-health", "fishwife", "ghia",
        "brightland", "fly-by-jing", "kin-euphorics", "hypebeast",
        "high-snobiety", "the-ringer", "axios", "substack", "a24", "spotify",
        "riot-games", "epic-games", "devolver-digital", "raw-fury",
        "annapurna-interactive", "humble-games", "patagonia", "cotopaxi",
        "allbirds", "vuori", "tracksmith", "momentous", "beam-organics",
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
                        source="Lever (Direct)",
                    )
        except Exception:
            pass

def scrape_greenhouse():
    print("  Scraping Greenhouse career pages...")
    companies = [
        "aspyr", "riotgames", "epicgames", "fandom", "crunchyroll",
        "calm", "headspace", "spotify", "howlerbros", "cuts", "allbirds",
        "vuori", "madhappy", "momentous", "two-chairs", "spring-health",
        "cerebral", "wondermind", "axios", "theringer", "hypebeast",
        "rawfury", "humblebundle",
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
                    description=BeautifulSoup(job.get("content", ""), "html.parser").get_text()[:300],
                )
        except Exception:
            pass

def scrape_ashby():
    print("  Scraping Ashby career pages...")
    companies = [
        "fishwife", "ghia", "graza", "brightland", "everyday-dose",
        "heart-and-soil", "momentous", "beam", "two-chairs", "fly-by-jing",
        "olipop", "kin-euphorics", "thesis", "seed", "ritual", "supergoop",
        "summer-fridays", "vacation-inc", "liquid-death", "madhappy", "cuts",
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
                        source="Ashby (Direct)",
                    )
        except Exception:
            pass

def scrape_direct_pages():
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
        "Kin Euphorics": "https://www.kineuphoric.com/pages/careers",
        "popagenda": "https://popagenda.co",
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
                        description=f"Matching role found on {company} careers page",
                    )
                    break
        except Exception:
            pass

def scrape_substacks():
    print("  Scraping Substack newsletters...")
    feeds = [
        ("Words of Mouth", "https://wordsofmouth.substack.com/feed"),
        ("Lenny's Newsletter", "https://www.lennysnewsletter.com/feed"),
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
                            description=entry.get("title", ""),
                        )
                        break
        except Exception:
            pass

# ─────────────────────────────────────────────
# CONSULTING PROSPECT SCRAPERS
# ─────────────────────────────────────────────

prospects = []
seen_brands = set()

PROSPECT_INDUSTRIES = [
    "gaming", "dtc", "consumer", "lifestyle", "wellness", "cpg",
    "food", "beverage", "fashion", "apparel", "mental health",
    "editorial", "media", "creator economy", "music", "culture",
]

FOUNDER_SIGNALS = [
    "founder", "founder-led", "bootstrapped", "self-funded",
    "indie", "independent", "seed stage", "pre-series a", "early stage",
    "small team", "solo founder",
]

def make_prospect_id(brand, contact=""):
    raw = f"{brand}-{contact}".lower()
    return re.sub(r"[^a-z0-9]", "-", raw)[:40].strip("-")

def score_prospect(brand, description, industry, notes=""):
    score = 0
    text = f"{brand} {description} {industry} {notes}".lower()

    for ind in PROSPECT_INDUSTRIES:
        if ind in text:
            score += 2

    for sig in FOUNDER_SIGNALS:
        if sig in text:
            score += 2

    if "austin" in text or "texas" in text:
        score += 1

    return max(score, 3)

def add_prospect(brand, founder="", contact="", contact_title="", gap="",
                 linkedin="", instagram="", website="", industry="",
                 revenue_est="", score=5, notes=""):
    if not brand or brand in seen_brands:
        return
    seen_brands.add(brand)
    prospects.append({
        "id": make_prospect_id(brand, contact),
        "brand": brand,
        "founder": founder,
        "contact": contact,
        "contact_title": contact_title,
        "gap": gap,
        "linkedin": linkedin,
        "instagram": instagram,
        "website": website,
        "industry": industry,
        "revenue_est": revenue_est,
        "score": score,
        "notes": notes,
        "added_date": datetime.now().strftime("%Y-%m-%d"),
    })

def seed_known_prospects():
    """Hardcoded high-priority prospects — active clients and named targets."""
    print("  Seeding known prospects...")

    add_prospect(
        brand="Opulist",
        gap="Active retainer client. Built the entire partnership function from scratch — closed $50K+ in brand and institutional partnerships in the first two quarters with no existing program, pricing framework, or deal history.",
        instagram="https://instagram.com/opulist",
        website="https://opulist.co",
        industry="Editorial / Media",
        score=10,
        notes="Active retainer",
    )
    add_prospect(
        brand="indie.io",
        gap="Active contracting engagement. Built outbound developer acquisition pipeline from the ground up — 150% increase in outbound activity, 40% increase in qualified conversations.",
        website="https://indie.io",
        industry="Gaming",
        score=10,
        notes="Active contract",
    )
    add_prospect(
        brand="Fishwife",
        founder="Becca Millstein",
        contact="Anna Parmelee",
        contact_title="Head of Growth",
        gap="Fishwife has one of the strongest brand identities in DTC food. The product is differentiated, the community is committed, and the brand equity is real. There is no dedicated partnerships operator. Commercial strategy is still founder-dependent. The collab and brand integration potential here is significant and untapped.",
        linkedin="https://linkedin.com/in/anna-parmelee",
        instagram="https://instagram.com/eatfishwife",
        website="https://eatfishwife.com",
        industry="Food & Beverage / DTC",
        revenue_est="$5M-10M",
        score=9,
        notes="No posted role - direct outreach",
    )
    add_prospect(
        brand="popagenda",
        founder="Gen Miller",
        contact="Gen Miller",
        contact_title="CEO",
        gap="popagenda has a clear creative identity and a strong point of view in music and culture. The commercial infrastructure - partnerships, brand collaborations, GTM - is founder-dependent and not yet systematized. Strong brand, weak commercial scaffolding.",
        linkedin="https://linkedin.com/in/gen-miller",
        instagram="https://instagram.com/popagenda",
        website="https://popagenda.co",
        industry="Music / Culture",
        revenue_est="$1M-5M",
        score=8,
        notes="No posted role - direct outreach",
    )
    add_prospect(
        brand="Midwest Games",
        founder="Adam Orth",
        contact="Adam Orth",
        contact_title="Founder / CEO",
        gap="Midwest Games has built a compelling indie publishing identity but the partnership and commercial development layer is thin. Adam is founder-operating the business. Developer acquisition and brand partnership infrastructure is the clear gap.",
        linkedin="https://linkedin.com/in/adam-orth",
        instagram="https://instagram.com/midwestgames",
        website="https://midwestgames.com",
        industry="Gaming",
        revenue_est="$2M-8M",
        score=8,
        notes="Contractor opportunity",
    )
    add_prospect(
        brand="Ghia",
        founder="Melanie Masarin",
        contact="Melanie Masarin",
        contact_title="Founder / CEO",
        gap="Ghia is building genuine cultural cachet in non-alc but the partnership infrastructure is light relative to the brand equity. Real room for a dedicated operator to formalize collaborations and brand integrations.",
        instagram="https://instagram.com/drinkghia",
        website="https://drinkghia.com",
        industry="Food & Beverage / DTC",
        revenue_est="$5M-15M",
        score=7,
        notes="",
    )
    add_prospect(
        brand="Graza",
        founder="Andrew Benin",
        contact="Andrew Benin",
        contact_title="Co-Founder / CEO",
        gap="Graza turned olive oil into a brand decision. The partnerships and collaboration layer is still founder-driven. The brand has the equity for real category-defying collabs and there is no dedicated operator to pursue them.",
        instagram="https://instagram.com/graza.co",
        website="https://graza.co",
        industry="Food & Beverage / DTC",
        revenue_est="$10M-30M",
        score=7,
        notes="",
    )
    add_prospect(
        brand="Wondermind",
        founder="Mandy Teefey",
        contact="Mandy Teefey",
        contact_title="Co-Founder / CEO",
        gap="Wondermind has strong founder equity and is building in mental health content with real cultural momentum. The brand partnership and GTM infrastructure is not yet systematized at the level the brand warrants.",
        instagram="https://instagram.com/wondermindco",
        website="https://wondermind.com",
        industry="Mental Health / Media",
        revenue_est="$2M-8M",
        score=7,
        notes="",
    )

def scrape_product_hunt_prospects():
    """Scrape Product Hunt for recent DTC/lifestyle/gaming launches."""
    print("  Scraping Product Hunt for prospects...")
    categories = ["consumer-goods", "lifestyle", "gaming", "health-fitness", "food-beverage"]
    for cat in categories:
        try:
            url = f"https://www.producthunt.com/topics/{cat}"
            resp = requests.get(url, headers=HEADERS, timeout=12)
            soup = BeautifulSoup(resp.text, "html.parser")
            for item in soup.select("[data-test='post-item'], [class*='postItem']")[:12]:
                name_el = item.select_one("h3, [class*='title'], [class*='name']")
                desc_el = item.select_one("p, [class*='tagline'], [class*='desc']")
                link_el = item.select_one("a")
                if not name_el:
                    continue
                brand = name_el.text.strip()
                desc = desc_el.text.strip() if desc_el else ""
                href = link_el.get("href", "") if link_el else ""
                site = f"https://www.producthunt.com{href}" if href.startswith("/") else href

                sc = score_prospect(brand, desc, cat)
                if sc < 4:
                    continue

                add_prospect(
                    brand=brand,
                    gap=f"{desc} Discovered on Product Hunt in the {cat.replace('-', ' ')} category. Likely founder-operated with minimal commercial infrastructure.",
                    website=site,
                    industry=cat.replace("-", " ").title(),
                    score=sc,
                    notes="Product Hunt discovery",
                )
        except Exception:
            pass

def scrape_words_of_mouth():
    """Parse Words of Mouth newsletter for emerging DTC brand mentions."""
    print("  Scanning Words of Mouth newsletter...")
    try:
        feed = feedparser.parse("https://wordsofmouth.substack.com/feed")
        for entry in feed.entries[:10]:
            if not is_recent(entry.get("published", "")):
                continue
            content_raw = entry.get("content", [{}])
            content_html = content_raw[0].get("value", entry.get("summary", "")) if content_raw else entry.get("summary", "")
            content = BeautifulSoup(content_html, "html.parser").get_text()
            # Find capitalized brand-like names not already in seen_brands
            brand_candidates = re.findall(r"\b([A-Z][a-zA-Z]{2,18}(?:\s[A-Z][a-zA-Z]{2,14})?)\b", content)
            checked = set()
            for brand in brand_candidates:
                if brand in checked or brand in seen_brands or len(brand) < 4:
                    continue
                if brand.lower() in {"the", "and", "for", "with", "this", "that", "they", "from",
                                      "have", "been", "their", "what", "when", "where", "which"}:
                    continue
                checked.add(brand)
                idx = content.find(brand)
                ctx = content[max(0, idx - 100):idx + 200].lower()
                sc = score_prospect(brand, ctx, "DTC")
                if sc >= 5:
                    add_prospect(
                        brand=brand,
                        gap=f"Mentioned in Words of Mouth newsletter. Context: {ctx[:200].strip()}",
                        industry="DTC / Consumer",
                        score=sc,
                        notes="Words of Mouth discovery",
                    )
    except Exception:
        pass

# ─────────────────────────────────────────────
# RUN ALL SCRAPERS
# ─────────────────────────────────────────────

print("James Tedesco Pipeline Agent")
print(f"Last {MAX_AGE_DAYS} days filter active\n")

print("--- JOB SCRAPERS ---")
scrape_indeed()
scrape_glassdoor()
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
scrape_direct_pages()
scrape_substacks()

jobs.sort(key=lambda x: x["score"], reverse=True)
top_jobs = jobs[:40]

print("\n--- PROSPECT SCRAPERS ---")
seed_known_prospects()
scrape_product_hunt_prospects()
scrape_words_of_mouth()

prospects.sort(key=lambda x: x["score"], reverse=True)

print(f"\nDone.")
print(f"  Jobs found:      {len(jobs)}, keeping top {len(top_jobs)}")
print(f"  Prospects found: {len(prospects)}\n")

# ─────────────────────────────────────────────
# WRITE JSON FILES FOR DASHBOARD
# ─────────────────────────────────────────────

jobs_path = os.path.join(OUTPUT_DIR, "jobs.json")
with open(jobs_path, "w") as f:
    json.dump(top_jobs, f, indent=2)
print(f"Wrote {len(top_jobs)} jobs  ->  {jobs_path}")

prospects_path = os.path.join(OUTPUT_DIR, "prospects.json")
with open(prospects_path, "w") as f:
    json.dump(prospects, f, indent=2)
print(f"Wrote {len(prospects)} prospects  ->  {prospects_path}")

meta_path = os.path.join(OUTPUT_DIR, "meta.json")
with open(meta_path, "w") as f:
    json.dump({
        "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "jobs": len(top_jobs),
        "prospects": len(prospects),
    }, f, indent=2)
print(f"Wrote meta  ->  {meta_path}")

# ─────────────────────────────────────────────
# OPTIONAL EMAIL DIGEST
# ─────────────────────────────────────────────

if not EMAIL_PASSWORD:
    print("\nNo EMAIL_PASSWORD set — skipping email digest.")
    print("Top roles:")
    for job in top_jobs[:10]:
        print(f"  [{job['score']}] {job['title']} @ {job['company']} ({job['source']})")
else:
    today = datetime.now().strftime("%A, %B %d")
    html_rows = ""
    for job in top_jobs:
        fit = "Strong Fit" if job["score"] >= 8 else "Good Fit" if job["score"] >= 5 else "Worth a Look"
        fit_color = "#2a7a2a" if job["score"] >= 8 else "#7a5a1a" if job["score"] >= 5 else "#555"
        html_rows += f"""
    <tr style="border-bottom:1px solid #f0f0f0">
      <td style="padding:14px 10px">
        <a href="{job['url']}" style="color:#1a1a1a;font-weight:600;font-size:15px;text-decoration:none">{job['title']}</a><br>
        <span style="color:#555;font-size:13px">{job['company']}</span>
        {"<br><span style='color:#999;font-size:12px;font-style:italic'>" + job['description'][:120] + "</span>" if job['description'] else ""}
      </td>
      <td style="padding:14px 10px;font-size:12px;color:{fit_color};font-weight:600;white-space:nowrap">{fit}</td>
      <td style="padding:14px 10px;font-size:12px;color:#888;white-space:nowrap">{job['source']}</td>
      <td style="padding:14px 10px;font-size:12px;color:#aaa;white-space:nowrap">{job['date']}</td>
    </tr>"""

    html_body = f"""<html><body style="font-family:Arial,sans-serif;max-width:900px;margin:0 auto;padding:28px;color:#1a1a1a;background:#fff">
<h2 style="border-bottom:3px solid #1a1a1a;padding-bottom:12px;margin-bottom:4px;font-size:22px">Job Digest</h2>
<p style="color:#888;font-size:13px;margin:4px 0 20px">{today} &nbsp;&middot;&nbsp; {len(jobs)} roles found &nbsp;&middot;&nbsp; Top {len(top_jobs)} shown &nbsp;&middot;&nbsp; Last {MAX_AGE_DAYS} days</p>
<table style="width:100%;border-collapse:collapse;font-size:14px">
<thead><tr style="background:#f8f8f8;font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:#888">
<th style="padding:10px;text-align:left">Role</th>
<th style="padding:10px;text-align:left">Fit</th>
<th style="padding:10px;text-align:left">Source</th>
<th style="padding:10px;text-align:left">Posted</th>
</tr></thead>
<tbody>{html_rows or "<tr><td colspan='4' style='padding:30px;color:#aaa;text-align:center;font-style:italic'>No new matching roles today.</td></tr>"}</tbody>
</table>
<hr style="margin:32px 0;border:none;border-top:1px solid #eee">
<p style="color:#ccc;font-size:11px;line-height:1.8">
Sources: Indeed, Glassdoor, Wellfound, Hitmarker, GamesIndustry.biz, Built In Austin, Hiring Cafe, Welcome to the Jungle, Workable, Lever, Greenhouse, Ashby, 27 Direct Career Pages, 7 Substack Feeds
</p></body></html>"""

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
