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
    "systems engineer", "it systems", "product analyst", "data analyst",
    "clinical", "nurse", "physician", "pharmacist", "radiologist",
    "therapy associate", "therapist", "counselor", "clinical social worker",
    "accountant", "cpa", "tax manager", "bookkeeper",
    "supply chain", "warehouse", "logistics", "truck driver",
    "real estate agent", "insurance agent", "loan officer",
    "braze admin", "salesforce developer", "sql developer",
    "lifecycle marketing manager", "crm manager",
    "sales executive", "account executive", "sales development",
    "yield manager", "revenue optimization", "store administrator",
    "store manager", "retail associate", "customer service",
]

TARGET_COMPANIES = [
    # gaming — publishers, studios, platforms
    "aspyr", "midwest games", "popagenda", "riot games", "epic games",
    "devolver digital", "annapurna interactive", "raw fury", "fellow traveller",
    "humble games", "humble bundle", "dexerto", "fandom", "crunchyroll", "ign",
    "2k games", "take two", "505 games", "sega", "bandai namco",
    "focus entertainment", "plaion", "modus games", "maximum games",
    "curve games", "team17", "private division", "tinyBuild", "neon doctrine",
    "good shepherd", "skybound games", "nighthawk interactive",
    "apply games", "games workshop", "gamescom", "gearbox",
    "embracer group", "playtika", "naughty dog", "insomniac",
    "double fine", "obsidian", "inXile", "machine games", "arkane",
    "id software", "bethesda", "zenimax", "activision blizzard",
    "505 games", "warhorse studios", "coffee stain", "paradox interactive",
    "klei entertainment", "supergiant games", "motion twin",
    "hitbox team", "thunderful", "joystick ventures",
    # gaming media / community
    "ign entertainment", "gamespot", "gamesradar", "kotaku", "polygon",
    "pcgamer", "eurogamer", "rock paper shotgun", "giant bomb",
    "hitmarker", "gamesindustry biz",
    # dtc / consumer / food & bev
    "fishwife", "graza", "ghia", "brightland", "fly by jing",
    "diaspora co", "omsom", "vacation inc", "cuts clothing", "madhappy",
    "olipop", "liquid death", "momentous", "beam", "kin euphorics",
    "everyday dose", "heart and soil", "athletic greens", "seed health",
    "thesis", "supergoop", "summer fridays", "touchland", "necessaire",
    "by humankind", "blueland", "grove collaborative",
    "jones road beauty", "ilia beauty", "tower 28",
    "jolie", "soft services", "starface", "paulas choice",
    "recess", "trip", "de soi", "dram", "with/co",
    "two roots", "hiyo", "aplós", "monday gin", "lyre's",
    "omakase berry", "snif", "french girl organics",
    "oat haus", "party ice", "fly by jing",
    "chomps", "epic bar", "paleovalley", "equip foods",
    "good culture", "kite hill", "forager project",
    "fly by jing", "somos", "siete family foods",
    "poppi", "popfizz", "culture pop", "united sodas",
    "ghia", "trip", "lyre",
    # apparel / fashion / lifestyle
    "howler brothers", "patagonia", "cotopaxi", "allbirds", "vuori",
    "tracksmith", "satisfy running", "kith", "aimé leon dore",
    "beams", "noah", "corridor", "rowing blazers",
    "free label", "entireworld", "buck mason", "taylor stitch",
    "mack weldon", "unbound merino", "james perse",
    "rhone", "public rec", "lululemon", "outdoor voices",
    "alo yoga", "beyond yoga", "girlfriend collective",
    "girlfriend collective", "girlfriend collective",
    "khaite", "toteme", "ganni", "staud", "sleeper",
    "skims", "parade", "aerie", "cuup",
    # mental health / wellness
    "wondermind", "calm", "headspace", "two chairs", "cerebral",
    "spring health", "brightside", "real", "talkspace",
    "betterhelp", "monument", "workit health", "sober grid",
    "done adhd", "alto pharmacy", "ahead", "noom",
    "whoop", "oura", "levels", "eight sleep",
    "thorne", "ritual", "care of", "seed health",
    "hims hers", "ro health", "thirty madison",
    # media / entertainment / editorial
    "a24", "spotify", "substack", "axios", "the ringer",
    "complex networks", "hypebeast", "high snobiety",
    "vox media", "bustle digital", "puck news", "the atlantic",
    "conde nast", "hearst", "future plc", "recurrent ventures",
    "gallery media", "group nine", "barstool sports",
    "meadowlark media", "uninterrupted", "togethxr",
    "wave sports entertainment", "overtime", "loaded",
    "nerdist", "collider", "screenrant", "cbr",
    "dicebreaker", "tabletop gaming",
    # creator economy / talent
    "cameo", "patreon", "beehiiv", "ghost", "kajabi",
    "teachable", "gumroad", "stan", "koji",
    "pietra", "fourthwall", "creative juice",
    "linktree", "later", "buffer", "dash hudson",
    # music / culture
    "sound on sound", "festival pass", "dice fm",
    "seated", "songkick", "bandsintown",
    "awal", "stem", "distrokid", "unitedmasters",
    "venice music", "empire distribution", "create music group",
    "canary music", "amuse", "tunecore",
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

def clean_text(raw):
    """Strip HTML tags and normalize whitespace."""
    if not raw:
        return ""
    text = BeautifulSoup(str(raw), "html.parser").get_text(separator=" ")
    return " ".join(text.split())

def is_ascii_title(title):
    """Reject titles that are mostly non-ASCII (e.g. Japanese)."""
    try:
        title.encode("ascii")
        return True
    except UnicodeEncodeError:
        # allow if majority of chars are ASCII
        ascii_chars = sum(1 for c in title if ord(c) < 128)
        return ascii_chars / max(len(title), 1) > 0.6

def add_job(title, company, url, date_str="", source="", description=""):
    if not title or not url:
        return
    if not is_ascii_title(title):
        return
    if url in seen_urls:
        return
    if not is_recent(date_str):
        return
    desc_clean = clean_text(description)
    score = score_job(title, desc_clean, company)
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
        "description": desc_clean[:280],
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
        # wellness / mental health
        "calm", "headspace", "wondermind", "two-chairs", "cerebral",
        "spring-health", "brightside", "real", "noom", "whoop", "levels",
        "thorne", "ritual", "hims", "ro",
        # dtc / food / bev
        "graza", "cuts", "madhappy", "vacation", "olipop", "liquid-death",
        "athletic-greens", "seed-health", "fishwife", "ghia", "brightland",
        "fly-by-jing", "kin-euphorics", "momentous", "beam-organics",
        "everyday-dose", "heart-and-soil", "poppi", "culture-pop",
        "chomps", "paleovalley", "good-culture", "siete-foods",
        "touchland", "necessaire", "blueland", "grove-collaborative",
        "jones-road-beauty", "ilia", "tower-28", "starface",
        # lifestyle / apparel
        "patagonia", "cotopaxi", "allbirds", "vuori", "tracksmith",
        "outdoor-voices", "alo", "rhone", "public-rec", "buck-mason",
        "taylor-stitch", "mack-weldon", "kith",
        # gaming
        "riot-games", "epic-games", "devolver-digital", "raw-fury",
        "annapurna-interactive", "humble-games", "tinyBuild",
        "good-shepherd", "skybound", "gearbox", "double-fine",
        "coffee-stain", "paradox-interactive", "team17",
        # media / editorial
        "a24", "spotify", "substack", "axios", "the-ringer",
        "hypebeast", "high-snobiety", "vox-media", "puck",
        "barstool-sports", "uninterrupted", "overtime",
        # creator economy
        "patreon", "cameo", "beehiiv", "later", "dash-hudson",
        "linktree", "pietra",
        # music
        "unitedmasters", "awal", "distrokid", "create-music-group",
        "venice-music",
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
        # gaming
        "aspyr", "riotgames", "epicgames", "fandom", "crunchyroll",
        "rawfury", "humblebundle", "devolverdigital", "tinybuild",
        "goodshepherdentertainment", "skyboundgames", "gearbox",
        "doublefine", "obsidian", "coffeestain", "paradoxinteractive",
        "team17", "klei",
        # wellness / mental health
        "calm", "headspace", "cerebral", "springhealth", "two-chairs",
        "wondermind", "noom", "whoop", "levels", "thorne", "ritual",
        "hims", "thirty-madison",
        # dtc / consumer
        "cuts", "allbirds", "vuori", "madhappy", "momentous",
        "liquid-death", "olipop", "everyday-dose",
        "touchland", "necessaire", "blueland",
        "jones-road", "ilia-beauty", "starface",
        "chomps", "siete", "good-culture",
        # lifestyle
        "howlerbros", "patagonia", "cotopaxi", "tracksmith",
        "outdoor-voices", "alo", "rhone", "public-rec",
        # media
        "spotify", "axios", "theringer", "hypebeast",
        "voxmedia", "substack", "a24",
        # creator
        "patreon", "beehiiv", "later",
        # music
        "unitedmasters", "awal", "venice-music",
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
                    description=BeautifulSoup(job.get("content", "") or "", "html.parser").get_text(separator=" ").strip()[:300],
                )
        except Exception:
            pass

def scrape_ashby():
    print("  Scraping Ashby career pages...")
    companies = [
        # dtc food / bev / wellness
        "fishwife", "ghia", "graza", "brightland", "everyday-dose",
        "heart-and-soil", "momentous", "beam", "fly-by-jing",
        "olipop", "kin-euphorics", "thesis", "seed", "ritual",
        "supergoop", "summer-fridays", "vacation-inc", "liquid-death",
        "madhappy", "cuts", "poppi", "culture-pop", "chomps",
        "paleovalley", "good-culture", "siete",
        "touchland", "necessaire", "blueland", "grove",
        "jones-road", "ilia", "tower28", "starface",
        "recess", "de-soi", "hiyo", "aplós",
        # gaming
        "devolver", "annapurna", "raw-fury", "tinybuild",
        "good-shepherd", "skybound", "coffee-stain",
        # lifestyle / apparel
        "outdoor-voices", "alo-yoga", "rhone", "public-rec",
        "buck-mason", "taylor-stitch", "mack-weldon",
        "rowing-blazers", "corridor", "noah",
        # media / creator
        "substack", "beehiiv", "patreon", "pietra",
        "linktree", "later", "dash-hudson",
        # music
        "unitedmasters", "venice-music", "awal", "create-music-group",
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
        # James's named targets
        "Aspyr": "https://www.aspyr.com/open_positions",
        "Midwest Games": "https://www.midwestgames.com/contact",
        "Heart and Soil": "https://heartandsoil.co/careers/",
        "Everyday Dose": "https://apply.workable.com/everyday-dose-inc/",
        "Howler Brothers": "https://www.howlerbros.com/pages/careers",
        "Fishwife": "https://www.eatfishwife.com/pages/careers",
        "popagenda": "https://popagenda.co",
        # gaming
        "Raw Fury": "https://rawfury.com/careers/",
        "Fellow Traveller": "https://fellowtraveller.games/jobs/",
        "tinyBuild": "https://www.tinybuild.com/careers",
        "Good Shepherd": "https://goodshepherd.com/careers",
        "Skybound Games": "https://www.skybound.com/careers",
        "Devolver Digital": "https://www.devolverdigital.com/jobs",
        "Annapurna Interactive": "https://annapurnainteractive.com/en/jobs",
        "Joystick Ventures": "https://joystickventures.com",
        # food / bev / dtc
        "Graza": "https://www.graza.co/pages/jobs",
        "Ghia": "https://drinkghia.com/pages/jobs",
        "Vacation Inc": "https://vacation.inc/pages/jobs",
        "Olipop": "https://drinkolipop.com/pages/careers",
        "Liquid Death": "https://liquiddeath.com/pages/jobs",
        "Poppi": "https://drinkpoppi.com/pages/careers",
        "Recess": "https://drinkre.cc/pages/careers",
        "Kin Euphorics": "https://www.kineuphoric.com/pages/careers",
        "De Soi": "https://drinkdesoi.com/pages/careers",
        "Fly By Jing": "https://www.flybyjing.com/pages/careers",
        "Brightland": "https://www.brightland.co/pages/careers",
        "Omsom": "https://www.omsom.com/pages/careers",
        "Siete Foods": "https://sietefoods.com/pages/careers",
        "Chomps": "https://www.chomps.com/pages/careers",
        "Momentous": "https://livemomentous.com/pages/careers",
        # beauty / personal care
        "Supergoop": "https://www.supergoop.com/pages/careers",
        "Summer Fridays": "https://www.summerfridays.com/pages/careers",
        "Touchland": "https://touchland.com/pages/careers",
        "Necessaire": "https://www.necessaire.com/pages/careers",
        "Jones Road Beauty": "https://www.jonesroadbeauty.com/pages/careers",
        "Starface": "https://starface.world/pages/careers",
        "Tower 28": "https://tower28beauty.com/pages/careers",
        # apparel / lifestyle
        "Cuts Clothing": "https://www.cuts.com/pages/careers",
        "Madhappy": "https://madhappy.com/pages/careers",
        "Patagonia": "https://www.patagonia.com/jobs/",
        "Cotopaxi": "https://www.cotopaxi.com/pages/careers",
        "Tracksmith": "https://www.tracksmith.com/pages/careers",
        "Vuori": "https://vuoriclothing.com/pages/careers",
        "Outdoor Voices": "https://www.outdoorvoices.com/pages/careers",
        "Buck Mason": "https://www.buckmason.com/pages/careers",
        "Taylor Stitch": "https://www.taylorstitch.com/pages/careers",
        "Rowing Blazers": "https://rowingblazers.com/pages/careers",
        "Corridor": "https://www.corridornyc.com/pages/careers",
        "Rhone": "https://www.rhone.com/pages/careers",
        "Public Rec": "https://publicrec.com/pages/careers",
        # wellness / mental health
        "Calm": "https://www.calm.com/careers",
        "Headspace": "https://www.headspace.com/careers",
        "Wondermind": "https://www.wondermind.com/careers",
        "Two Chairs": "https://www.twochairs.com/careers",
        "Spring Health": "https://springhealth.com/careers/",
        "Levels": "https://www.levelshealth.com/careers",
        "Eight Sleep": "https://www.eightsleep.com/careers/",
        "Whoop": "https://www.whoop.com/careers/",
        "Thorne": "https://www.thorne.com/pages/careers",
        "Ritual": "https://ritual.com/pages/careers",
        # media / editorial
        "The Ringer": "https://www.theringer.com/careers",
        "Substack": "https://substack.com/jobs",
        "Puck": "https://puck.news/careers",
        "Axios": "https://www.axios.com/about/careers",
        "Hypebeast": "https://hypebeast.com/jobs",
        # music / culture
        "UnitedMasters": "https://unitedmasters.com/careers",
        "AWAL": "https://www.awal.com/careers",
        "Venice Music": "https://www.venicemusic.co/careers",
        "Create Music Group": "https://createmusicgroup.com/careers/",
        "DICE": "https://dice.fm/careers",
        # creator economy
        "Patreon": "https://www.patreon.com/careers",
        "Beehiiv": "https://www.beehiiv.com/careers",
        "Pietra": "https://www.pietrastudio.com/careers",
        "Linktree": "https://linktr.ee/careers",
        "Dash Hudson": "https://www.dashhudson.com/careers",
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

    # Additional consulting targets — strong brands, weak commercial infrastructure
    add_prospect(
        brand="Recess",
        founder="Ben Witte",
        contact="Ben Witte",
        contact_title="Founder / CEO",
        gap="Recess has built one of the most visually distinctive brands in the non-alc space. The aesthetic is genuinely good. The partnerships and brand collab layer is not systematized and the brand equity supports much more than what's been done commercially.",
        instagram="https://instagram.com/drinkrecess",
        website="https://drinkre.cc",
        industry="Food & Beverage / DTC",
        revenue_est="$5M-15M",
        score=7,
        notes="",
    )
    add_prospect(
        brand="Brightland",
        founder="Aishwarya Iyer",
        contact="Aishwarya Iyer",
        contact_title="Founder / CEO",
        gap="Brightland has built exceptional brand equity in olive oil and vinegar with zero retail dependency. Strong editorial POV, strong community. No dedicated partnerships or commercial infrastructure operator.",
        instagram="https://instagram.com/brightlandco",
        website="https://brightland.co",
        industry="Food & Beverage / DTC",
        revenue_est="$3M-10M",
        score=7,
        notes="",
    )
    add_prospect(
        brand="Fly By Jing",
        founder="Jing Gao",
        contact="Jing Gao",
        contact_title="Founder / CEO",
        gap="Fly By Jing has built a cult brand around Sichuan flavors and a strong founder identity. The commercial partnership and collab layer is underdeveloped relative to the cultural cachet. Real room for a fractional operator.",
        instagram="https://instagram.com/flybyjing",
        website="https://flybyjing.com",
        industry="Food & Beverage / DTC",
        revenue_est="$5M-15M",
        score=7,
        notes="",
    )
    add_prospect(
        brand="Vacation Inc",
        founder="Dakota Green",
        contact="Dakota Green",
        contact_title="Co-Founder / CEO",
        gap="Vacation has built an unusually strong brand identity in sunscreen — irreverent, nostalgic, highly meme-able. The brand partnership and collab calendar is active but founder-driven. No dedicated commercial operator.",
        instagram="https://instagram.com/vacation",
        website="https://vacation.inc",
        industry="Beauty / DTC",
        revenue_est="$5M-20M",
        score=7,
        notes="",
    )
    add_prospect(
        brand="Joystick Ventures",
        founder="",
        contact="",
        contact_title="",
        gap="Joystick Ventures is building community around gaming culture and brand. Early stage, founder-operated, no dedicated partnerships or GTM operator. Strong signal for fractional engagement.",
        instagram="https://instagram.com/joystickventures",
        website="https://joystickventures.com",
        industry="Gaming",
        revenue_est="$1M-5M",
        score=7,
        notes="",
    )
    add_prospect(
        brand="Fellow Traveller",
        founder="Chris Wright",
        contact="Chris Wright",
        contact_title="CEO",
        gap="Fellow Traveller publishes narrative and story-driven games with a strong curatorial identity. The brand partnership and developer relations infrastructure is minimal for the cultural footprint they have.",
        instagram="https://instagram.com/ftgames",
        website="https://fellowtraveller.games",
        industry="Gaming",
        revenue_est="$2M-8M",
        score=7,
        notes="",
    )
    add_prospect(
        brand="UnitedMasters",
        founder="Steve Stoute",
        contact="Steve Stoute",
        contact_title="Founder / CEO",
        gap="UnitedMasters sits at the intersection of music distribution, brand partnerships, and creator economy. The commercial partnership layer is sophisticated but there is real room for fractional GTM support on specific brand programs.",
        instagram="https://instagram.com/unitedmasters",
        website="https://unitedmasters.com",
        industry="Music / Creator Economy",
        revenue_est="$20M+",
        score=6,
        notes="Larger org — fractional brand program angle",
    )
    add_prospect(
        brand="Beehiiv",
        founder="Tyler Denk",
        contact="Tyler Denk",
        contact_title="Co-Founder / CEO",
        gap="Beehiiv is the fastest-growing newsletter platform and has real brand equity in the creator economy. The brand partnership and commercial infrastructure is still founder-operated. Strong fit for fractional operator.",
        instagram="https://instagram.com/beehiiv",
        website="https://beehiiv.com",
        industry="Creator Economy / Media",
        revenue_est="$5M-20M",
        score=7,
        notes="",
    )
    add_prospect(
        brand="DICE",
        founder="Phil Hutcheon",
        contact="Phil Hutcheon",
        contact_title="Founder / CEO",
        gap="DICE is building the ticketing platform for independent music and culture with a genuine community identity. The brand partnership and GTM layer is thin relative to the brand equity in the music space.",
        instagram="https://instagram.com/dice_fm",
        website="https://dice.fm",
        industry="Music / Culture",
        revenue_est="$10M-30M",
        score=6,
        notes="",
    )
    add_prospect(
        brand="Rowing Blazers",
        founder="Jack Carlson",
        contact="Jack Carlson",
        contact_title="Founder / Creative Director",
        gap="Rowing Blazers has built one of the most culturally resonant menswear brands in the market. The collaboration catalog is impressive but the commercial infrastructure behind partnerships is still founder-driven.",
        instagram="https://instagram.com/rowingblazers",
        website="https://rowingblazers.com",
        industry="Fashion / Apparel",
        revenue_est="$5M-15M",
        score=7,
        notes="",
    )
    add_prospect(
        brand="Puck",
        founder="Jon Kelly",
        contact="Jon Kelly",
        contact_title="Co-Founder / CEO",
        gap="Puck has built genuine media brand equity and a subscriber model with no ad dependency. The commercial partnership and brand integration layer is minimal — there is real room for someone to build that function.",
        instagram="https://instagram.com/pucknews",
        website="https://puck.news",
        industry="Editorial / Media",
        revenue_est="$5M-15M",
        score=6,
        notes="",
    )
    add_prospect(
        brand="Outdoor Voices",
        founder="",
        contact="",
        contact_title="",
        gap="Outdoor Voices has a strong brand identity and an active community in activewear. Post-founder transition, the commercial infrastructure and partnership function needs rebuilding.",
        instagram="https://instagram.com/outdoorvoices",
        website="https://www.outdoorvoices.com",
        industry="Apparel / Lifestyle",
        revenue_est="$20M+",
        score=6,
        notes="Post-founder transition — rebuilding phase",
    )
    add_prospect(
        brand="Omsom",
        founder="Vanessa Pham",
        contact="Vanessa Pham",
        contact_title="Co-Founder / CEO",
        gap="Omsom has built a loud, proud brand identity in Asian-American food culture with a devoted community. The collaboration and brand partnership layer is founder-driven and not yet systematized.",
        instagram="https://instagram.com/omsom",
        website="https://omsom.com",
        industry="Food & Beverage / DTC",
        revenue_est="$3M-10M",
        score=7,
        notes="",
    )
    add_prospect(
        brand="Pietra",
        founder="Ronak Trivedi",
        contact="Ronak Trivedi",
        contact_title="Co-Founder / CEO",
        gap="Pietra is building commerce infrastructure for creators and brands with a strong network in the creator economy. GTM and brand partnership infrastructure is thin for the market position they occupy.",
        instagram="https://instagram.com/pietrastudio",
        website="https://pietrastudio.com",
        industry="Creator Economy / DTC",
        revenue_est="$5M-20M",
        score=6,
        notes="",
    )
    add_prospect(
        brand="Madhappy",
        founder="Peiman Raf",
        contact="Peiman Raf",
        contact_title="Co-Founder / CEO",
        gap="Madhappy has made mental health feel like a lifestyle position rather than a category. The brand equity is real. The partnership and commercial infrastructure is still founder-operated below the brand's potential.",
        instagram="https://instagram.com/madhappy",
        website="https://madhappy.com",
        industry="Fashion / Mental Health",
        revenue_est="$10M-30M",
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
top_jobs = jobs  # no cap — show everything that passes the score filter

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
