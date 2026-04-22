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

# ── SKILL BUCKET 1: Partnerships & Biz Dev ───────────────────────────────────
TITLES_PARTNERSHIPS = [
    "brand partnerships manager", "creative partnerships manager",
    "partnerships manager", "head of partnerships", "director of partnerships",
    "collaborations manager", "head of collaborations", "collab manager",
    "co-marketing manager", "commercial partnerships", "brand and partnerships",
    "growth partnerships", "media partnerships", "strategic partnerships",
    "influencer partnerships", "creator partnerships", "talent partnerships",
    "artist partnerships", "publisher relations", "licensing partnerships",
    "business development manager", "biz dev manager",
]

# ── SKILL BUCKET 2: Brand & Marketing ────────────────────────────────────────
TITLES_BRAND_MARKETING = [
    "brand manager", "brand marketing manager", "brand strategist",
    "head of brand", "director of brand", "vp of brand",
    "marketing manager", "integrated marketing manager", "cultural marketing manager",
    "campaign manager", "content marketing manager", "go-to-market manager",
    "gtm manager", "brand operator", "creative operator",
    "experiential marketing manager", "brand experience manager",
    "social media manager", "community manager",
]

# ── SKILL BUCKET 3: Creative & Content ───────────────────────────────────────
TITLES_CREATIVE = [
    "creative director", "associate creative director",
    "creative strategist", "brand creative", "creative lead",
    "content strategist", "editorial director", "head of content",
    "content director", "creative producer", "brand producer",
    "copy director", "copywriter", "brand copywriter",
]

# ── SKILL BUCKET 4: Ecom & Growth ────────────────────────────────────────────
TITLES_ECOM = [
    "ecommerce manager", "ecom manager", "shopify manager",
    "growth manager", "head of growth", "growth marketing manager",
    "conversion manager", "digital marketing manager",
    "retention marketing manager", "email marketing manager",
    "lifecycle manager",
]

# ── SKILL BUCKET 5: Gaming / Publishing ──────────────────────────────────────
TITLES_GAMING = [
    "publisher relations", "developer relations", "devrel",
    "game scout", "publishing manager", "publishing coordinator",
    "studio relations", "indie games manager", "gaming partnerships",
    "gaming brand manager", "esports partnerships", "gaming marketing manager",
]

# Combined — all titles used for scoring
TARGET_TITLES = (
    TITLES_PARTNERSHIPS
    + TITLES_BRAND_MARKETING
    + TITLES_CREATIVE
    + TITLES_ECOM
    + TITLES_GAMING
)

TARGET_INDUSTRIES = [
    "gaming", "game", "indie game", "publisher", "esports",
    "consumer", "dtc", "direct to consumer", "lifestyle", "wellness", "cpg",
    "media", "entertainment", "editorial", "streaming", "creator economy",
    "fashion", "apparel", "food", "beverage", "spirits",
    "mental health", "beauty", "skincare",
    "culture", "music", "outdoor recreation",
    "sustainability", "creator", "influencer",
    "sports media", "sports entertainment",  # media companies, NOT sports teams/franchises
]

# These keywords in the JOB TITLE alone are instant disqualifiers
# (prevents company bonus from saving clearly wrong roles)
TITLE_HARDSTOP = [
    "tax", "accountant", "payroll", "controller", "bookkeeper",
    "store administrator", "yield manager", "revenue optimization",
    "customer service", "customer success", "client success",
    "supply chain", "warehouse", "logistics",
    "software engineer", "data engineer", "devops", "machine learning",
    "data scientist", "security engineer", "infrastructure",
    "product analyst", "data analyst", "business analyst",
    "nurse", "physician", "pharmacist", "clinical",
    "real estate", "insurance", "mortgage",
    "asset protection", "loss prevention",
    "sql", "java", "kubernetes",
    "retail marketing manager",  # too retail-ops focused
    "email and web",  # too tactical/channel-specific
    "merchant partnerships",  # amazon sellers etc.
    "3d printing",
    "ai/cloud",
    "starlink",
    "west region",
    "location partnerships",  # geospatial ad partnerships
]

BAD_SIGNALS = [
    # wrong function — tech / engineering
    "software engineer", "data engineer", "devops", "machine learning",
    "data scientist", "backend", "frontend engineer", "ios developer",
    "android developer", "java", "kubernetes", "aws engineer",
    "systems engineer", "it systems", "product analyst", "data analyst",
    "security engineer", "infrastructure", "sre", "site reliability",
    # wrong function — medical / clinical
    "clinical", "nurse", "physician", "pharmacist", "radiologist",
    "therapy associate", "therapist", "counselor", "clinical social worker",
    # wrong function — finance / legal / hr
    "accountant", "cpa", "tax manager", "bookkeeper", "payroll",
    "accounts payable", "accounts receivable", "controller",
    "paralegal", "attorney", "recruiter", "talent acquisition",
    # wrong function — logistics / ops
    "supply chain", "warehouse", "logistics", "truck driver",
    "real estate agent", "insurance agent", "loan officer",
    # wrong function — crm / martech engineering
    "braze admin", "salesforce developer", "sql developer",
    "lifecycle marketing manager", "crm manager", "marketing automation",
    # wrong function — platform ad sales
    "global business solutions", "tiktok for business",
    "global sales", "ads manager", "performance marketing manager",
    "programmatic", "paid media manager", "sem manager",
    # wrong function — sales
    "sales executive", "account executive", "sales development",
    "inside sales", "outbound sales", "mid-market sales",
    "enterprise sales", "smb sales",
    # wrong function — retail / ops
    "store manager", "retail associate", "customer service",
    "merchandiser", "merchandising", "field rep", "territory manager",
    "client success", "customer success", "asset protection",
    # wrong industries entirely — not James's world
    "cruise", "cruise line", "cruise ship",
    "petroleum", "oil and gas", "mining", "drilling",
    "automotive", "auto parts", "dealership",
    "pharmaceutical", "pharma", "biotech",
    "staffing agency", "temp agency", "recruiting firm",
    "insurance", "reinsurance",
    "banking", "mortgage", "lending", "wealth management",
    "freight", "trucking", "shipping",
    "pest control", "cleaning services", "janitorial",
    "food service", "quick service", "fast food", "quick-service",
    "hospitality chain", "hotel chain", "resort chain",
    "sports team", "franchise", "sports franchise",
    # geo filters — block international-only roles
    "korea", "japan", "apac", "indonesia", "malaysia", "singapore",
    "australia", "india", "emea", "latam", "brazil", "mexico",
    "toronto", "london", "berlin", "amsterdam", "paris",
    "dublin", "sydney", "tokyo", "seoul", "shanghai", "beijing",
]

# Companies that get +5 score boost — attainable, right-sized, strong brand fit
TARGET_COMPANIES = [
    # gaming — indie publishers, mid-size studios (James has context here)
    "aspyr", "midwest games", "devolver digital", "annapurna interactive",
    "raw fury", "fellow traveller", "humble games", "tinybuild",
    "good shepherd", "skybound games", "thunderful", "joystick ventures",
    "coffee stain", "klei entertainment", "supergiant games",
    "neon doctrine", "whitethorn games", "freedom games", "modus games",
    "curve games", "maximum games", "nighthawk interactive",
    "hitmarker", "dexerto", "fandom", "gamesindustry",
    # dtc food & bev — small to mid, editorial identity, founder-led
    "fishwife", "graza", "ghia", "brightland", "fly by jing",
    "diaspora co", "omsom", "vacation inc", "recess", "taika",
    "clevr blends", "mud/wtr", "deux", "halfday", "dieux skin",
    "kin euphorics", "everyday dose", "heart and soil",
    "poppi", "culture pop", "de soi", "hiyo",
    "chomps", "paleovalley", "good culture", "somos",
    "snif", "touchland", "necessaire",
    "starface", "tower 28", "jones road", "ilia beauty",
    # apparel / lifestyle — indie to mid, cultural identity
    "howler brothers", "cotopaxi", "tracksmith", "corridor",
    "rowing blazers", "buck mason", "taylor stitch", "public rec",
    "outdoor voices", "criquet", "satisfy running",
    # austin-based — bonus for local proximity
    "tecovas", "waterloo sparkling", "austin eastciders", "rambler",
    # mental health / wellness — mission-driven, mid-size
    "wondermind", "two chairs", "real", "ahead", "momentous",
    # media / editorial — indie + boutique
    "a24", "substack", "axios", "the ringer", "puck",
    "hypebeast", "highsnobiety", "recurrent ventures",
    "meadowlark media", "togethxr", "uninterrupted",
    "neon", "mubi", "bleecker street", "magnolia",
    # creator economy — tools for creators, small to mid
    "beehiiv", "pietra", "fourthwall", "dash hudson", "later",
    # music / culture — independent
    "dice fm", "unitedmasters", "venice music", "awal",
    "create music group", "popagenda",
    # active application / named targets
    "farrow and ball", "farrow & ball",
    "turtle beach", "kyra", "joined media", "afk",
]

# Large corps / wrong-industry companies — hard penalty (-4)
# These get through on title match alone without this
BIG_CORP_PENALTY = [
    # big tech
    "google", "meta", "apple", "amazon", "microsoft", "netflix",
    "salesforce", "adobe", "oracle", "ibm", "intel",
    "waymo", "uber", "lyft", "doordash", "airbnb", "coinbase",
    "linkedin", "twitter", "x corp", "snapchat", "pinterest",
    "twitch", "youtube", "tiktok",
    # big gaming
    "unity", "roblox", "riot games", "epic games",
    "activision", "blizzard", "electronic arts", "ea games", "ubisoft",
    "take-two", "2k games", "bethesda", "zenimax", "sega",
    "bandai namco", "square enix", "capcom",
    # big media / publishing
    "spotify", "disney", "warner", "universal", "sony",
    "conde nast", "hearst", "vox media", "buzzfeed", "bustle",
    "barstool sports", "complex networks", "iheartmedia",
    # big consumer / retail
    "ralph lauren", "gap inc", "h&m", "zara", "lvmh", "kering",
    "l'oreal", "unilever", "procter", "colgate", "kraft", "nestle",
    "conagra", "pepsico", "coca-cola", "mondelez", "dole", "tyson",
    "starbucks", "mcdonald", "yum brands",
    "puma", "adidas", "nike", "under armour", "columbia sportswear",
    "lululemon", "allbirds", "vuori", "patagonia",
    # big pharma / health / insurance
    "united health", "cvs", "walgreens", "humana", "cigna",
    "pfizer", "johnson & johnson", "abbvie",
    # big finance
    "jpmorgan", "goldman", "morgan stanley", "bank of america",
    "wells fargo", "capital one", "american express",
    # big telco / auto / industrial
    "verizon", "att", "comcast", "charter",
    "ford", "gm", "toyota", "honda", "valvoline",
    # big wellness (already at scale, highly competitive)
    "whoop", "oura", "noom", "betterhelp", "hims", "ro health",
    "olipop", "liquid death", "athletic greens", "ag1",
    "calm", "headspace", "talkspace",
    # big hospitality / travel / cruise
    "marriott", "hilton", "hyatt", "intercontinental",
    "norwegian cruise", "royal caribbean", "carnival",
    "sage hospitality",
    # big creator / platform
    "cameo", "patreon", "kajabi", "teachable",
    # recruiting/staffing firms showing up as the "company"
    "robert half", "aquent", "kforce", "randstad",
    "heidrick", "russell reynolds",
    # misc large / wrong-fit that keep slipping through
    "kendra scott", "bumble", "roc nation", "coty",
    "generous brands", "buzzivo",
    "nintendo", "general mills", "ingram content",
    "roku", "spacex", "doordash",
    "houston dynamo", "orlando city", "sporting kc",  # sports franchises
    "freshpaint", "octave", "provectus",  # healthcare / AI / wrong vertical
    "iberostar", "marriott", "hilton", "wyndham",  # hotel chains
    "livelabs", "livelab",
    "talently", "reacher",  # recruiting / wrong vertical
]

SEARCH_QUERIES = [
    # ── Partnerships & Biz Dev ────────────────────────────────
    "brand partnerships manager DTC",
    "brand partnerships manager gaming",
    "creative partnerships manager",
    "collaborations manager lifestyle",
    "head of partnerships startup",
    "influencer partnerships manager gaming",
    "creator partnerships manager",
    "business development manager media",
    "publisher relations manager",
    "licensing partnerships manager",
    "media partnerships manager",
    # ── Brand & Marketing ─────────────────────────────────────
    "brand manager DTC startup",
    "brand manager indie games",
    "brand marketing manager consumer",
    "go-to-market manager startup",
    "marketing manager lifestyle brand",
    "marketing manager indie games",
    "integrated marketing manager entertainment",
    "cultural marketing manager",
    "experiential marketing manager",
    "campaign manager entertainment",
    "community manager gaming",
    "head of brand startup",
    # ── Creative & Content ────────────────────────────────────
    "creative director DTC",
    "creative director gaming",
    "brand creative director",
    "creative strategist lifestyle",
    "content strategist DTC",
    "editorial director media",
    "head of content startup",
    "brand copywriter",
    # ── Ecom & Growth ─────────────────────────────────────────
    "ecommerce manager DTC",
    "head of growth DTC startup",
    "growth marketing manager consumer",
    "digital marketing manager lifestyle",
    "email marketing manager DTC",
    # ── Gaming / Publishing ───────────────────────────────────
    "developer relations gaming",
    "publishing manager indie games",
    "gaming marketing manager",
    "studio relations manager",
    "game scout",
    "esports partnerships manager",
    # ── Broader operator / builder ────────────────────────────
    "head of marketing startup",
    "director of brand",
    "brand operator",
    "vp partnerships",
    "fractional brand",
    "gtm manager startup",
]

MAX_AGE_DAYS = 8
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

OUTPUT_DIR = os.environ.get("GITHUB_WORKSPACE", ".")
EMAIL_TO = os.environ.get("EMAIL_TO", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "ueTL3dBbPL1d6QkBzk9nnw")
HUNTER_API_KEY = os.environ.get("HUNTER_API_KEY", "2a556ff74abf73e7425a5a5557f1304dc9c34745")

# ─────────────────────────────────────────────
# APOLLO CONTACT LOOKUP
# ─────────────────────────────────────────────

CONTACT_TITLE_KEYWORDS = [
    "partnerships", "brand", "marketing", "collaborations",
    "creative", "growth", "gtm", "go-to-market", "talent",
    "business development", "commercial", "founder", "ceo",
    "cmo", "vp", "director", "head of", "recruiter", "hiring",
]

_hunter_cache = {}
_apollo_cache = {}

def apollo_get_contacts(company_name, domain=None):
    """
    Apollo.io contact lookup stub.
    The $49/mo Apollo plan blocks /v1/mixed_people/search and /v1/people/search.
    Upgrade to Professional (~$99/mo) to unlock full API database search.
    """
    return []

def hunter_get_contacts(company_name, domain=None):
    """Return up to 5 relevant contacts using Hunter.io domain search."""
    if not HUNTER_API_KEY:
        return []
    cache_key = (domain or company_name).lower().strip()
    if cache_key in _hunter_cache:
        return _hunter_cache[cache_key]

    # derive domain from company name if not provided
    if not domain:
        slug = re.sub(r"[^a-z0-9]", "", company_name.lower())
        domain = f"{slug}.com"

    try:
        resp = requests.get(
            f"https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": HUNTER_API_KEY, "limit": 20},
            timeout=12,
        )
        if resp.status_code != 200:
            _hunter_cache[cache_key] = []
            return []

        data = resp.json()
        emails = data.get("data", {}).get("emails", [])

        # score and filter by title relevance
        scored = []
        for e in emails:
            title = (e.get("position") or "").lower()
            score = sum(1 for kw in CONTACT_TITLE_KEYWORDS if kw in title)
            if score > 0 and e.get("value"):
                scored.append((score, e))

        scored.sort(key=lambda x: x[0], reverse=True)
        contacts = []
        for _, e in scored[:5]:
            contacts.append({
                "name": f"{e.get('first_name', '')} {e.get('last_name', '')}".strip(),
                "title": e.get("position", ""),
                "email": e.get("value", ""),
                "linkedin": e.get("linkedin", ""),
            })

        _hunter_cache[cache_key] = contacts
        return contacts
    except Exception:
        _hunter_cache[cache_key] = []
        return []

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

    # Title scoring — award points only for the BEST single match
    # (prevents "brand marketing manager" and "marketing manager" from double-stacking)
    title_bonus = 0
    desc_bonus = 0
    for t in TARGET_TITLES:
        if t in title_lower:
            title_bonus = max(title_bonus, 4)
        elif t in text:
            desc_bonus = max(desc_bonus, 2)
    score += title_bonus + desc_bonus

    for ind in TARGET_INDUSTRIES:
        if ind in text:
            score += 1

    for co in TARGET_COMPANIES:
        if co in company.lower():
            score += 5

    co_lower = company.lower().strip()
    for co in BIG_CORP_PENALTY:
        co_clean = co.strip()
        # word-boundary match so "unity" doesn't hit "community", etc.
        if re.search(r'(?<![a-z])' + re.escape(co_clean) + r'(?![a-z])', co_lower):
            score -= 6  # strong enough to overcome TARGET_COMPANIES bonus

    for kw in BAD_SIGNALS:
        if kw in text:
            score -= 5

    if "austin" in text or "austin, tx" in text:
        score += 4
    if "remote" in text or "hybrid" in text or "work from anywhere" in text or "distributed" in text:
        score += 3
    if "new york" in text or "brooklyn" in text or "manhattan" in text:
        score -= 4
    if "los angeles" in text or "santa monica" in text or "culver city" in text:
        score -= 4
    if "san francisco" in text or "bay area" in text or "seattle" in text:
        score -= 3
    if "chicago" in text or "boston" in text or "denver" in text:
        score -= 2

    return score

def make_job_id(title, company, url=""):
    raw = f"{company}-{title}-{url}"
    return re.sub(r"[^a-z0-9]", "-", raw.lower())[:48].strip("-")

jobs = []
seen_urls = set()
seen_title_company = set()

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
    # Hard-stop: if the title itself signals a wrong function, skip immediately
    title_lower = title.lower()
    if any(hs in title_lower for hs in TITLE_HARDSTOP):
        return
    if url in seen_urls:
        return
    tc_key = title.lower().strip() + "|" + company.lower().strip()
    if tc_key in seen_title_company:
        return
    seen_title_company.add(tc_key)
    if not is_recent(date_str):
        return
    desc_clean = clean_text(description)
    score = score_job(title, desc_clean, company)
    if score < 4:
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
                for entry in feed.entries[:15]:
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
        # gaming — indie / mid-size (attainable)
        "devolver-digital", "raw-fury", "annapurna-interactive",
        "humble-games", "tinybuild", "good-shepherd", "skybound",
        "coffee-stain", "team17", "thunderful", "whitethorn-games",
        "freedom-games", "modus-games", "curve-games",
        "fellow-traveller", "joystick-ventures",
        # dtc / food & bev — small to mid
        "graza", "fishwife", "ghia", "brightland", "fly-by-jing",
        "everyday-dose", "heart-and-soil", "taika", "clevr",
        "deux", "halfday", "kin-euphorics", "momentous", "beam-organics",
        "poppi", "culture-pop", "de-soi", "hiyo", "recess",
        "chomps", "paleovalley", "good-culture", "siete-foods",
        "touchland", "necessaire", "jones-road-beauty", "ilia", "tower-28",
        "omsom", "diaspora-co", "snif",
        # apparel / lifestyle
        "howler-brothers", "cotopaxi", "tracksmith", "corridor",
        "rowing-blazers", "buck-mason", "taylor-stitch", "public-rec",
        "outdoor-voices", "criquet", "satisfy-running",
        # wellness / mental health — mid-size only
        "wondermind", "two-chairs", "real", "ahead", "seed-health",
        "thorne", "ritual",
        # media / editorial
        "a24", "substack", "axios", "the-ringer", "puck",
        "hypebeast", "highsnobiety", "uninterrupted",
        "meadowlark-media", "togethxr", "overtime",
        "recurrent-ventures", "mubi", "neon",
        # creator economy
        "beehiiv", "later", "dash-hudson", "linktree", "pietra",
        # music / culture
        "unitedmasters", "awal", "venice-music", "create-music-group",
        "dice-fm",
        # austin
        "tecovas", "waterloo-sparkling", "criquet",
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
        # gaming — indie / mid (aspyr is Austin, great target)
        "aspyr", "rawfury", "humblebundle", "devolverdigital", "tinybuild",
        "goodshepherdentertainment", "skyboundgames",
        "doublefine", "coffeestain", "klei", "505games",
        "maximumgames", "curvesgames", "nighthawkinteractive",
        "fandom", "dexerto",
        # dtc / food / bev / beauty — small to mid
        "everyday-dose", "fishwife", "touchland", "necessaire",
        "graza", "ghia", "jones-road", "iliabeauty", "starface", "tower28beauty",
        "chomps", "siete", "good-culture", "poppi",
        "vacation", "omsom", "diasporaco", "flybyjing",
        "dieux", "softservices", "snif", "jolie",
        "clevr", "mudwtr", "taika", "deux", "halfday",
        "recess", "desoi", "hiyo", "momentous",
        "brightland",
        # apparel / lifestyle — indie to mid
        "howlerbros", "cotopaxi", "tracksmith",
        "outdoorvoices", "rowingblazers", "corridor", "criquet",
        "buckmason", "taylorstitch", "publicrec",
        # austin brands
        "tecovas", "kendrascott", "waterloosparkling",
        "austineastciders", "rambler",
        # media / editorial — attainable
        "axios", "theringer", "hypebeast", "highsnobiety",
        "substack", "a24", "neon", "mubi",
        "uninterrupted", "meadowlarkmedia", "togethxr", "puck",
        "recurrentventures",
        # creator economy
        "beehiiv", "later", "dashhudson", "linktree", "pietra", "fourthwall",
        # music / culture
        "unitedmasters", "awal", "venice-music", "createmusicgroup",
        # wellness — mid-size only
        "twochairs", "wondermind", "springhealth", "thorne", "ritual",
        # experiential / events
        "smilebooth",
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
        # James's named targets + active applications
        "Aspyr": "https://www.aspyr.com/open_positions",
        "Midwest Games": "https://www.midwestgames.com/contact",
        "Heart and Soil": "https://heartandsoil.co/careers/",
        "Everyday Dose": "https://apply.workable.com/everyday-dose-inc/",
        "Howler Brothers": "https://www.howlerbros.com/pages/careers",
        "Fishwife": "https://www.eatfishwife.com/pages/careers",
        "popagenda": "https://popagenda.co",
        "Farrow and Ball": "https://www.farrow-ball.com/careers",
        "A24": "https://a24films.com/jobs",
        "Dash Hudson": "https://www.dashhudson.com/careers",
        "Turtle Beach": "https://careers.turtlebeach.com/",
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
        # entertainment / film
        "A24": "https://a24films.com/jobs",
        "Neon": "https://www.neonrated.com/jobs",
        "MUBI": "https://mubi.com/en/careers",
        "Criterion": "https://www.criterion.com/about/jobs",
        # sports / culture
        "Uninterrupted": "https://www.uninterrupted.com/careers",
        "Overtime": "https://overtime.tv/careers",
        "Meadowlark Media": "https://meadowlarkmedia.com/careers",
        "Complex Networks": "https://complex.com/careers",
        "Togethxr": "https://www.togethxr.com/careers",
        # creator economy
        "Patreon": "https://www.patreon.com/careers",
        "Beehiiv": "https://www.beehiiv.com/careers",
        "Pietra": "https://www.pietrastudio.com/careers",
        "Linktree": "https://linktr.ee/careers",
        "Dash Hudson": "https://www.dashhudson.com/careers",
        # attainable — smaller, earlier stage, more likely to hire fractional
        "Studs": "https://www.studs.com/pages/careers",
        "Jolie": "https://jolieskinco.com/pages/careers",
        "Soft Services": "https://www.softservices.com/pages/careers",
        "Snif": "https://www.snif.co/pages/careers",
        "French Girl Organics": "https://frenchgirlorganics.com/pages/careers",
        "Oat Haus": "https://www.oathaus.com/pages/careers",
        "Taika": "https://taika.co/pages/careers",
        "Clevr Blends": "https://clevrblends.com/pages/careers",
        "Wooden Spoon Herbs": "https://woodenspoonherbs.com/pages/careers",
        "Diaspora Co": "https://www.diasporaco.com/pages/careers",
        "Dae Hair": "https://daehair.com/pages/careers",
        "Dieux Skin": "https://dieuxskin.com/pages/careers",
        "Experiment Beauty": "https://experimentbeauty.com/pages/careers",
        "Halfday": "https://drinkhalfday.com/pages/careers",
        "Cann": "https://drinkcann.com/pages/careers",
        "Wynk": "https://drinkwynk.com/pages/careers",
        "Deux": "https://eatdeux.com/pages/careers",
        "Mud Wtr": "https://mudwtr.com/pages/careers",
        "Swoon": "https://swoondrinks.com/pages/careers",
        "Gorgie": "https://drinkgorgie.com/pages/careers",
        # austin-local attainable
        "Austin Eastciders": "https://austineastciders.com/careers/",
        "Waterloo Sparkling Water": "https://waterloosparkling.com/pages/careers",
        "Rambler": "https://drinkrambler.com/pages/careers",
        "Saveur Selects": "https://saveurselects.com/pages/careers",
        "Keep Austin Weird": "https://keepaustinweird.com/careers",
        "Austin Beerworks": "https://austinbeerworks.com/careers",
        "Kendra Scott": "https://kendrascott.com/pages/careers",
        "Tecovas": "https://www.tecovas.com/pages/careers",
        "Criquet Shirts": "https://www.criquet.com/pages/careers",
        "Nack": "https://nack.com/careers",
        # gaming — smaller / attainable
        "Whitethorn Games": "https://whitethorngames.com/jobs",
        "Armor Games Studios": "https://armorgamesstudios.com/careers",
        "Freedom Games": "https://freedomgames.com/careers",
        "Graffiti Games": "https://www.graffiti.games/careers",
        "Stride PR": "https://stridepr.com/careers",
        "Vicarious PR": "https://www.vicariouspr.com/careers",
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

def scrape_linkedin():
    print("  Scraping LinkedIn...")
    for q in SEARCH_QUERIES[:20]:
        try:
            encoded = q.replace(" ", "%20")
            for loc in ["103644278", "90000070"]:  # Austin, Remote
                url = f"https://www.linkedin.com/jobs/search/?keywords={encoded}&location={loc}&f_TPR=r604800&sortBy=DD"
                resp = requests.get(url, headers=HEADERS, timeout=12)
                soup = BeautifulSoup(resp.text, "html.parser")
                for card in soup.select(".job-search-card, .base-card")[:10]:
                    title_el = card.select_one(".base-search-card__title, h3")
                    company_el = card.select_one(".base-search-card__subtitle, h4")
                    link_el = card.select_one("a.base-card__full-link, a")
                    date_el = card.select_one("time")
                    if title_el:
                        href = link_el.get("href", "") if link_el else ""
                        add_job(
                            title=title_el.text.strip(),
                            company=company_el.text.strip() if company_el else "",
                            url=href,
                            date_str=date_el.get("datetime", "") if date_el else "",
                            source="LinkedIn",
                        )
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

    # European companies that explicitly hire US remote/freelance — don't penalize
    if any(kw in text for kw in ["us remote", "us expansion", "us market", "contractor opportunity", "us-based"]):
        score += 2

    return max(score, 3)

def add_prospect(brand, founder="", contact="", contact_title="", gap="",
                 linkedin="", instagram="", website="", industry="",
                 revenue_est="", score=5, notes="", region="US"):
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
        "region": region,
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

    # Attainable — smaller, earlier stage, more likely to respond to fractional pitch
    add_prospect(
        brand="Taika",
        founder="Kal Freese",
        contact="Kal Freese",
        contact_title="Co-Founder / CEO",
        gap="Taika is a functional coffee brand with a strong aesthetic identity and a clear point of view. Early stage, founder-operated, no dedicated partnerships or GTM operator. Exactly the profile for a fractional engagement.",
        instagram="https://instagram.com/drinktaika",
        website="https://taika.co",
        industry="Food & Beverage / DTC",
        revenue_est="$1M-5M",
        score=8,
        notes="Early stage — high responsiveness likelihood",
    )
    add_prospect(
        brand="Clevr Blends",
        founder="Hannah Mendoza",
        contact="Hannah Mendoza",
        contact_title="Co-Founder / CEO",
        gap="Clevr Blends has built a distinctive brand in functional lattes with strong celebrity endorsement and community. The commercial infrastructure is thin. No dedicated partnerships operator.",
        instagram="https://instagram.com/clevrblends",
        website="https://clevrblends.com",
        industry="Food & Beverage / Wellness",
        revenue_est="$2M-8M",
        score=8,
        notes="Early stage — high responsiveness likelihood",
    )
    add_prospect(
        brand="Mud/Wtr",
        founder="Shane Heath",
        contact="Shane Heath",
        contact_title="Founder / CEO",
        gap="Mud/Wtr has built a cult brand around coffee alternatives and a strong community. The partnership and collab layer is underdeveloped for the brand's cultural footprint. Founder-operated commercial function.",
        instagram="https://instagram.com/mudwtr",
        website="https://mudwtr.com",
        industry="Food & Beverage / Wellness",
        revenue_est="$10M-30M",
        score=7,
        notes="",
    )
    add_prospect(
        brand="Deux",
        founder="Sabeena Ladha",
        contact="Sabeena Ladha",
        contact_title="Founder / CEO",
        gap="Deux makes functional cookie dough with a strong DTC brand and a genuinely funny, distinct voice. Small team, founder-operated, no commercial partnerships infrastructure. High responsiveness likelihood.",
        instagram="https://instagram.com/eatdeux",
        website="https://eatdeux.com",
        industry="Food & Beverage / DTC",
        revenue_est="$1M-5M",
        score=8,
        notes="Small team — high responsiveness likelihood",
    )
    add_prospect(
        brand="Halfday",
        founder="Lara Wyss",
        contact="Lara Wyss",
        contact_title="Co-Founder / CEO",
        gap="Halfday is building in the relaxation drink space with a strong aesthetic and a clear consumer insight. Very early stage, founder-operated, no dedicated GTM or partnerships function.",
        instagram="https://instagram.com/drinkhalfday",
        website="https://drinkhalfday.com",
        industry="Food & Beverage / Wellness",
        revenue_est="$500K-$3M",
        score=8,
        notes="Early stage — high responsiveness likelihood",
    )
    add_prospect(
        brand="Dieux Skin",
        founder="Charlotte Palermino",
        contact="Charlotte Palermino",
        contact_title="Co-Founder / CEO",
        gap="Dieux has built exceptional brand equity in skincare with a transparency-first positioning and a devoted community. Small team, founder-operated commercial function, no dedicated partnerships operator.",
        instagram="https://instagram.com/dieuxskin",
        website="https://dieuxskin.com",
        industry="Beauty / DTC",
        revenue_est="$3M-10M",
        score=8,
        notes="Small team — high responsiveness likelihood",
    )
    add_prospect(
        brand="Criquet Shirts",
        founder="Billy Nachman",
        contact="Billy Nachman",
        contact_title="Co-Founder / CEO",
        gap="Criquet is a lifestyle apparel brand built around sport, culture, and a strong Austin identity. The commercial partnership and collaboration layer is minimal. Austin-based, founder-operated.",
        instagram="https://instagram.com/criquetshirts",
        website="https://criquet.com",
        industry="Apparel / Lifestyle",
        revenue_est="$3M-10M",
        score=7,
        notes="Austin-based",
    )
    add_prospect(
        brand="Tecovas",
        founder="Paul Hedrick",
        contact="Paul Hedrick",
        contact_title="Founder / CEO",
        gap="Tecovas is the dominant DTC Western boot brand with strong Austin roots and a growing retail presence. The brand partnership and collab layer is underdeveloped for the brand's scale and cultural moment.",
        instagram="https://instagram.com/tecovas",
        website="https://tecovas.com",
        industry="Apparel / Lifestyle",
        revenue_est="$50M+",
        score=6,
        notes="Austin-based — larger org but strong fit",
    )
    add_prospect(
        brand="Waterloo Sparkling Water",
        founder="John Setz",
        contact="John Setz",
        contact_title="CEO",
        gap="Waterloo is the leading Austin-born sparkling water brand with national distribution. The brand partnership and collaboration layer is not systematized at the level the brand warrants.",
        instagram="https://instagram.com/waterloosparkling",
        website="https://waterloosparkling.com",
        industry="Food & Beverage / DTC",
        revenue_est="$20M+",
        score=6,
        notes="Austin-based",
    )
    add_prospect(
        brand="Whitethorn Games",
        founder="Matthew White",
        contact="Matthew White",
        contact_title="Founder / CEO",
        gap="Whitethorn Games publishes cozy and accessible indie games with a strong community identity. Small team, founder-operated, no dedicated partnerships or brand operator. High responsiveness likelihood for fractional engagement.",
        instagram="https://instagram.com/whitethorndigital",
        website="https://whitethorngames.com",
        industry="Gaming",
        revenue_est="$1M-5M",
        score=8,
        notes="Small team — high responsiveness likelihood",
    )
    add_prospect(
        brand="Freedom Games",
        founder="",
        contact="",
        contact_title="",
        gap="Freedom Games is an indie publisher with a growing catalog and minimal commercial infrastructure. No dedicated partnerships operator. Strong fit for fractional developer relations and brand support.",
        instagram="https://instagram.com/freedomgamesofficial",
        website="https://freedomgames.com",
        industry="Gaming",
        revenue_est="$1M-5M",
        score=7,
        notes="Small team — high responsiveness likelihood",
    )
    add_prospect(
        brand="Diaspora Co",
        founder="Sana Javeri Kadri",
        contact="Sana Javeri Kadri",
        contact_title="Founder / CEO",
        gap="Diaspora Co has built one of the most values-driven and editorially strong brands in the spice space. The commercial partnership layer is thin. Founder-operated, strong community, high responsiveness likelihood.",
        instagram="https://instagram.com/diasporaco",
        website="https://diasporaco.com",
        industry="Food & Beverage / DTC",
        revenue_est="$2M-8M",
        score=8,
        notes="Small team — high responsiveness likelihood",
    )

    # ── EUROPEAN COMPANIES — hire US-based freelancers / consultants ──────────
    add_prospect(
        brand="Highsnobiety",
        founder="David Fischer",
        contact="David Fischer",
        contact_title="Founder / CEO",
        gap="Highsnobiety is Berlin's defining culture-and-commerce media brand — editorial, events, and brand partnerships at the intersection of streetwear, music, and luxury. They routinely hire US-based freelancers for brand and partnerships work and their commercial infrastructure is sophisticated enough to absorb a high-caliber operator.",
        instagram="https://instagram.com/highsnobiety",
        website="https://highsnobiety.com",
        industry="Media / Fashion / Culture",
        revenue_est="$20M+",
        score=9,
        notes="Berlin-based, US remote-friendly — strong fit",
        region="EU",
    )
    add_prospect(
        brand="Pangaia",
        founder="Amanda Parkes",
        contact="Amanda Parkes",
        contact_title="Chief Innovation Officer",
        gap="Pangaia has built one of the most credible sustainability-first fashion brands globally. The brand partnership and commercial infrastructure layer is underdeveloped relative to the cultural equity. London-based but hires US-based consultants for commercial and partnership work.",
        instagram="https://instagram.com/pangaia",
        website="https://pangaia.com",
        industry="Fashion / Sustainability",
        revenue_est="$30M+",
        score=8,
        notes="London-based — US contractor opportunity",
        region="EU",
    )
    add_prospect(
        brand="Tony's Chocolonely",
        founder="Teun van de Keuken",
        contact="",
        contact_title="",
        gap="Tony's has built one of the most purpose-driven food brands in the world and is aggressively expanding in the US market. The brand partnership and GTM infrastructure for US market entry is an active need. US-facing partnerships role is a clear opportunity.",
        instagram="https://instagram.com/tonyschocolonely",
        website="https://tonyschocolonely.com",
        industry="Food & Beverage / DTC",
        revenue_est="$100M+",
        score=8,
        notes="Amsterdam HQ — active US expansion, strong contractor opportunity",
        region="EU",
    )
    add_prospect(
        brand="Oatly",
        founder="",
        contact="",
        contact_title="",
        gap="Oatly built the oat milk category and has unmatched brand equity in the space. The partnership and co-marketing layer in the US is thin relative to the brand's scale. US-based contractor work on brand programs is realistic.",
        instagram="https://instagram.com/oatly",
        website="https://oatly.com",
        industry="Food & Beverage / DTC",
        revenue_est="$700M+",
        score=7,
        notes="Swedish HQ — US office in NYC, remote brand partnership work feasible",
        region="EU",
    )
    add_prospect(
        brand="Ganni",
        founder="Ditte Reffstrup",
        contact="Ditte Reffstrup",
        contact_title="Creative Director",
        gap="Ganni has become the definitive Scandinavian fashion brand with genuine cultural cachet. The US market brand partnership and GTM infrastructure is not yet at the level the brand warrants. Copenhagen HQ with remote-friendly commercial infrastructure.",
        instagram="https://instagram.com/ganni",
        website="https://ganni.com",
        industry="Fashion / DTC",
        revenue_est="$100M+",
        score=7,
        notes="Copenhagen HQ — US remote consulting feasible",
        region="EU",
    )
    add_prospect(
        brand="Represent",
        founder="George Heaton",
        contact="George Heaton",
        contact_title="Founder / CEO",
        gap="Represent has built serious brand equity in premium streetwear and is aggressively expanding in the US market. The brand partnership and commercial infrastructure for US market growth is the active gap. Manchester-based but US-facing commercial work is a clear need.",
        instagram="https://instagram.com/representclo",
        website="https://representclo.com",
        industry="Fashion / Apparel",
        revenue_est="$30M+",
        score=8,
        notes="Manchester-based — US expansion mode, contractor fit",
        region="EU",
    )
    add_prospect(
        brand="Monocle",
        founder="Tyler Brule",
        contact="Tyler Brule",
        contact_title="Founder / Editor-in-Chief",
        gap="Monocle has built a global media brand with genuine cultural cachet and a distinctive commercial model built on brand partnerships and licensing. US-based freelance editorial and brand partnership work is a realistic engagement model for them.",
        instagram="https://instagram.com/monoclemag",
        website="https://monocle.com",
        industry="Editorial / Media",
        revenue_est="$20M+",
        score=7,
        notes="London HQ — US editorial and brand work feasible",
        region="EU",
    )
    add_prospect(
        brand="Veja",
        founder="Francois-Ghislain Morillion",
        contact="",
        contact_title="",
        gap="Veja has built the most credible sustainability narrative in sneakers with genuine traction in the US market. The brand partnership and commercial infrastructure for US growth is minimal. Paris HQ with US market as an active growth priority.",
        instagram="https://instagram.com/veja",
        website="https://veja-store.com",
        industry="Fashion / Sustainability",
        revenue_est="$100M+",
        score=7,
        notes="Paris HQ — US market growth, contractor opportunity",
        region="EU",
    )
    add_prospect(
        brand="Dazed Media",
        founder="Jefferson Hack",
        contact="Jefferson Hack",
        contact_title="Co-Founder / CEO",
        gap="Dazed is one of the most influential culture and fashion media brands globally. The brand partnership and commercial infrastructure in the US is thin for the brand's cultural reach. London-based with clear US market appetite.",
        instagram="https://instagram.com/dazed",
        website="https://dazeddigital.com",
        industry="Media / Fashion / Culture",
        revenue_est="$10M-30M",
        score=7,
        notes="London HQ — US brand and partnership work feasible",
        region="EU",
    )
    add_prospect(
        brand="Patagonia Provisions",
        founder="Yvon Chouinard",
        contact="",
        contact_title="",
        gap="Patagonia Provisions is building a premium food brand inside the world's most values-aligned outdoor company. The brand partnership and GTM infrastructure is minimal for the brand equity they carry. Fractional GTM and partnership support is the gap.",
        instagram="https://instagram.com/patagoniafoods",
        website="https://patagoniaprovisions.com",
        industry="Food & Beverage / Sustainability",
        revenue_est="$10M+",
        score=7,
        notes="Ventura CA HQ but operates globally — strong values fit",
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
scrape_linkedin()
scrape_substacks()

jobs.sort(key=lambda x: x["score"], reverse=True)
top_jobs = jobs  # no cap — show everything that passes the score filter

# Contact enrichment for top jobs (Hunter.io)
print("\n--- CONTACT ENRICHMENT (JOBS) ---")
for job in top_jobs[:30]:
    if job.get("contacts"):
        continue
    contacts = hunter_get_contacts(job["company"]) if HUNTER_API_KEY else []
    if contacts:
        job["contacts"] = contacts
        print(f"  {job['company']}: {len(contacts)} contacts")

print("\n--- PROSPECT SCRAPERS ---")
seed_known_prospects()
scrape_product_hunt_prospects()
scrape_words_of_mouth()

prospects.sort(key=lambda x: x["score"], reverse=True)

# Contact enrichment for prospects (Hunter.io)
print("\n--- CONTACT ENRICHMENT (PROSPECTS) ---")
for p in prospects[:30]:
    if p.get("contacts"):
        continue
    domain = None
    if p.get("website"):
        domain = p["website"].replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
    contacts = hunter_get_contacts(p["brand"], domain=domain) if HUNTER_API_KEY else []
    if contacts:
        p["contacts"] = contacts
        print(f"  {p['brand']}: {len(contacts)} contacts")

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
