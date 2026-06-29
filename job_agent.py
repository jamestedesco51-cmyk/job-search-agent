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
    "partnerships manager", "senior partnerships manager", "sr. partnerships manager",
    "head of partnerships",
    "collaborations manager", "head of collaborations", "collab manager",
    "co-marketing manager", "commercial partnerships", "brand and partnerships",
    "growth partnerships", "media partnerships", "strategic partnerships",
    "influencer partnerships", "creator partnerships", "talent partnerships",
    "artist partnerships", "publisher relations", "licensing partnerships",
    "business development manager", "biz dev manager",
    # fractional / contract
    "fractional cmo", "fractional head of marketing", "fractional head of partnerships",
    "fractional brand", "fractional marketing", "fractional partnerships",
    "fractional gtm", "fractional creative director", "fractional strategist",
    "fractional operator", "fractional consultant",
]

# ── SKILL BUCKET 2: Brand & Marketing ────────────────────────────────────────
TITLES_BRAND_MARKETING = [
    "brand manager", "brand marketing manager", "brand strategist",
    "head of brand", "senior brand manager",
    "marketing manager", "senior marketing manager", "integrated marketing manager",
    "cultural marketing manager", "campaign manager", "content marketing manager",
    "go-to-market manager", "gtm manager", "brand operator", "creative operator",
    "experiential marketing manager", "brand experience manager",
]

# ── SKILL BUCKET 3: Creative & Content ───────────────────────────────────────
TITLES_CREATIVE = [
    "associate creative director",
    "creative strategist", "senior creative strategist",
    "brand creative", "creative lead",
    "content strategist", "senior content strategist",
    "head of content", "content director",
    "creative producer", "brand producer", "senior creative producer",
    "creative project manager", "project manager marketing",
    "integrated marketing manager",
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
    "menswear", "lifestyle goods", "heritage", "surf", "outdoor",
    "healthcare", "health", "medtech", "digital health", "medical device",
    "biotech", "health tech", "clinical", "hospital", "health system",
    "university", "higher education", "academic", "research", "education",
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
    "amazon brand",  # amazon marketplace seller focus
    "social media manager",  # too narrow / junior
    "influencer manager",  # pure influencer ops
    "talent manager",  # talent representation, not brand strategy
    # pure technical/engineering design roles
    "ui designer", "ux designer",
    "motion designer",
    "programmatic manager",
    # too junior
    "junior partnerships",
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
    "goodwin recruiting", "motion recruitment", "cybercoders",
    "nemt", "non-emergency medical", "non emergency medical",
    "government contractor", "federal contractor", "dod contractor",
    "restaurant chain", "drive-in restaurant", "quick service",
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
    # menswear / lifestyle goods
    "corridor nyc", "corridor", "adsum", "metalwood", "pilgrim surf",
    "blackstock", "dehen", "carter young", "knickerbocker",
    # medical / health startups (brand-forward, not big pharma)
    "hims & hers", "ro health", "cerebral", "brightline", "headway",
    "noom", "life house", "devoted health", "devoted studios",
    "tend dental", "dental intelligence", "smiledirectclub",
    "keep company", "wellthy", "carrot fertility", "progyny",
    "midi health", "oshi health", "harbor health",
    # academia / university (Austin-centric)
    "ut austin", "university of texas", "texas medical center",
    "st. david's", "baylor scott", "ascension seton",
    "dell medical", "md anderson", "texas children's",
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
    "starbucks", "mcdonald", "yum brands", "kfc", "taco bell",
    "checkers", "rally's", "sonic drive", "jack in the box",
    "puma", "adidas", "nike", "under armour", "columbia sportswear",
    "lululemon", "allbirds", "vuori", "patagonia",
    # big consumer brands that keep slipping through
    "heineken", "ab inbev", "anheuser", "molson", "diageo", "constellation brands",
    "puig", "estee lauder", "revlon", "coty",
    "bodyarmor", "gatorade", "powerade",
    "fanatics", "nfl", "nba", "mlb", "nhl",
    # big B2B / fintech / wrong sector
    "affirm", "klarna", "stripe", "square", "paypal", "brex",
    "people.ai", "salesloft", "outreach.io", "gong",
    "servicenow", "workday", "hubspot", "zendesk",
    # government / defense / wrong world
    "govcio", "leidos", "booz allen", "saic", "caci",
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
    "olipop", "athletic greens", "ag1",
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
    # recruiting firms posting their own "openings" (not real brand roles)
    "morgan mace", "crossing hurdles", "jobgether", "gno partners",
    "one haus", "zazu digital", "creative circle", "the hub",
    "the kitchen", "the collective", "brandwidth",
]

SEARCH_QUERIES = [
    # ── Partnerships & Biz Dev ────────────────────────────────
    "brand partnerships manager remote",
    "brand partnerships manager DTC",
    "brand partnerships manager gaming",
    "creative partnerships manager remote",
    "collaborations manager remote",
    "head of partnerships remote",
    "influencer partnerships manager",
    "creator partnerships manager remote",
    "business development manager media remote",
    "publisher relations manager",
    "media partnerships manager remote",
    "strategic partnerships manager remote",
    # ── Brand & Marketing ─────────────────────────────────────
    "brand manager DTC remote",
    "brand manager indie games",
    "brand marketing manager remote",
    "go-to-market manager startup remote",
    "marketing manager lifestyle brand remote",
    "marketing manager gaming remote",
    "integrated marketing manager remote",
    "cultural marketing manager",
    "campaign manager remote",
    "head of brand startup remote",
    # ── Creative & Content ────────────────────────────────────
    "creative director DTC remote",
    "creative strategist remote",
    "content strategist DTC remote",
    "editorial director media",
    "head of content remote",
    # ── Ecom & Growth ─────────────────────────────────────────
    "ecommerce manager DTC remote",
    "head of growth startup remote",
    "growth marketing manager remote",
    # ── Gaming / Publishing ───────────────────────────────────
    "developer relations gaming remote",
    "publishing manager indie games",
    "gaming partnerships manager",
    "game scout remote",
    "esports partnerships manager",
    # ── Broader operator / builder ────────────────────────────
    "head of marketing startup remote",
    "director of brand remote",
    "vp partnerships remote",
    "gtm manager startup remote",
    "partnerships lead remote",
    # ── Fractional / contract roles ───────────────────────────
    "fractional CMO remote",
    "fractional head of marketing",
    "fractional head of partnerships",
    "fractional brand strategist",
    "fractional marketing director",
    "fractional partnerships manager",
    "fractional GTM remote",
    "fractional creative director",
    "contract brand partnerships manager",
    "contract head of growth remote",
    # ── Fractional (expanded — @falsestartKate sources) ───────
    "fractional creative producer",
    "fractional brand manager",
    "fractional content strategist",
    "fractional brand operator",
    "fractional partnerships lead",
    "fractional growth marketer",
    "fractional head of content",
    "fractional creative lead",
    "fractional campaign manager",
    "fractional creative strategist",
    "fractional brand DTC",
    "fractional marketing CPG",
    "fractional marketing startup",
    "fractional brand marketing",
    "interim head of marketing",
    "interim brand manager",
    "interim partnerships manager",
    "interim creative director",
    "interim head of brand",
    "interim marketing manager",
    "interim GTM manager",
    "contract creative strategist",
    "contract brand manager",
    "contract creative producer",
    "contract content strategist",
    "contract marketing manager remote",
    "contract head of brand",
    "contract brand marketing manager",
    "contract partnerships manager",
    "part-time brand manager",
    "part-time partnerships manager",
    "part-time head of growth",
    "part-time creative director remote",
    "part-time marketing manager remote",
    "retainer brand strategist",
    "retainer partnerships manager",
    "consulting brand strategy startup",
    "consulting GTM DTC",
    "consulting partnerships CPG",
    # ── Fractional by sector (gaming / media / entertainment) ─
    "fractional brand manager gaming",
    "fractional partnerships manager gaming",
    "fractional developer relations gaming",
    "contract publishing manager indie games",
    "interim head of partnerships gaming",
    "fractional creator partnerships media",
    "fractional brand entertainment",
    "contract creative producer media",
    "fractional brand manager streaming",
    "fractional GTM entertainment startup",
    "contract partnerships manager gaming",
    # ── Fractional by sector (wellness / health / fitness) ────
    "fractional brand manager wellness",
    "fractional marketing wellness brand",
    "contract brand strategist health",
    "interim head of marketing health startup",
    "fractional partnerships wellness CPG",
    "contract growth marketer health app",
    "fractional brand digital health",
    # ── Fractional by sector (fashion / menswear / lifestyle) ─
    "fractional brand manager fashion",
    "contract brand strategist apparel",
    "fractional marketing director menswear",
    "interim brand manager lifestyle brand",
    "contract creative director fashion",
    "fractional GTM apparel startup",
    "part-time brand manager clothing",
    # ── Fractional by sector (food / bev / CPG) ───────────────
    "fractional brand manager food beverage",
    "fractional head of marketing CPG",
    "contract brand manager beverage",
    "interim brand manager food startup",
    "fractional partnerships food brand",
    # ── Fractional by sector (creator / media / newsletters) ──
    "fractional brand creator economy",
    "contract content strategist newsletter",
    "fractional marketing creator platform",
    "fractional partnerships creator",
    "contract brand manager media startup",
    # ── Fractional — broad operator / startup stage ────────────
    "fractional operator startup",
    "fractional brand operator DTC",
    "fractional head of growth startup",
    "contract GTM manager startup",
    "interim chief of staff marketing",
    "fractional marketing lead remote",
    "contract brand lead startup",
    "fractional partnerships lead startup",
    # ── Brand & Creative (expanded) ───────────────────────────
    "brand director remote",
    "creative director lifestyle remote",
    "creative director CPG remote",
    "brand strategist remote",
    "brand lead startup remote",
    "creative lead DTC remote",
    "brand creative director remote",
    "director of creative remote",
    "VP creative remote",
    "brand experience manager remote",
    "storytelling director remote",
    # ── Medical / Healthcare branding ─────────────────────────
    "brand manager healthcare remote",
    "marketing manager health startup remote",
    "brand partnerships manager health wellness",
    "creative director health brand remote",
    "head of marketing medtech remote",
    "brand strategist medical device remote",
    "marketing director digital health remote",
    "partnerships manager healthcare remote",
    # ── Academia / University / UT Austin ─────────────────────
    "brand partnerships university remote",
    "marketing manager university Austin",
    "director of partnerships UT Austin",
    "creative director university remote",
    "head of brand education remote",
    "marketing director higher education remote",
    "brand manager education Austin",
    "partnerships director research institution",
]

MAX_AGE_DAYS = 7
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
    Apollo.io People Search — returns up to 3 relevant contacts at a company.
    Uses /api/v1/mixed_people/search (requires Professional plan or higher).
    Names and titles are returned; emails require separate enrichment credits.
    """
    if not APOLLO_API_KEY:
        return []
    cache_key = (domain or company_name).lower().strip()
    if cache_key in _apollo_cache:
        return _apollo_cache[cache_key]

    try:
        payload = {
            "api_key": APOLLO_API_KEY,
            "q_keywords": company_name,
            "person_seniorities": ["manager", "director", "vp", "c_suite", "head"],
            "person_titles": [
                "partnerships", "brand manager", "marketing manager",
                "head of partnerships", "director of partnerships",
                "vp of marketing", "cmo", "founder", "ceo",
                "growth", "collaborations", "creative director",
            ],
            "per_page": 5,
        }
        if domain:
            payload["q_organization_domains_list"] = [domain]

        resp = requests.post(
            "https://api.apollo.io/api/v1/mixed_people/search",
            json=payload,
            headers={"Content-Type": "application/json", "Cache-Control": "no-cache"},
            timeout=12,
        )

        if resp.status_code != 200:
            _apollo_cache[cache_key] = []
            return []

        data = resp.json()
        people = data.get("people", [])
        contacts = []
        for p in people[:3]:
            last = p.get("last_name") or p.get("last_name_obfuscated", "")
            name = f"{p.get('first_name', '')} {last}".strip()
            # Build LinkedIn URL from name if available
            linkedin = p.get("linkedin_url", "")
            if not linkedin:
                slug = re.sub(r"[^a-z0-9]", "-", name.lower()).strip("-")
                linkedin = f"https://www.linkedin.com/in/{slug}" if slug else ""
            contacts.append({
                "name": name,
                "title": p.get("title", ""),
                "email": p.get("email", ""),
                "linkedin": linkedin,
                "source": "Apollo",
            })
        _apollo_cache[cache_key] = contacts
        return contacts

    except Exception:
        _apollo_cache[cache_key] = []
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

    # Fractional / contract / part-time — these are exactly what James is targeting
    # A "Fractional Brand Manager" should surface higher than a regular one
    if any(kw in title_lower for kw in ["fractional", "contract", "part-time", "part time", "interim"]):
        score += 3
    # "Freelance" or "consulting" in title also signals flexible engagement
    if any(kw in title_lower for kw in ["freelance", "consulting", "consultant", "as-needed", "retainer"]):
        score += 2

    # Team-based roles are a strong positive signal — James thrives in collaborative environments
    team_signals = ["team", "collaborate", "cross-functional", "work with", "partner with",
                    "alongside", "joint", "collective", "crew", "in-house"]
    if any(sig in text for sig in team_signals):
        score += 2

    # Standalone "creative director" (not associate) is a senior stretch — nudge down
    if "creative director" in title_lower and "associate" not in title_lower:
        score -= 3

    # 8 years exp — director-level at established orgs is a reach
    # "Head of X" at startups is fine (startup speak for manager), "Director of X" is not
    # Director and VP level — stretch at 8 years, nudge down so they surface but don't dominate
    stretch_titles = [
        "director of brand", "director of partnerships", "director of marketing",
        "director of creative", "director of content", "director of growth",
        "brand director", "marketing director", "partnerships director",
        "senior director",
        "vp of brand", "vp of partnerships", "vp of marketing",
        "vp partnerships", "vp brand", "vp marketing",
        "vice president",
    ]
    if any(dt in title_lower for dt in stretch_titles):
        score -= 4

    # C-suite and above — hard out
    # Exception: "fractional CMO" is a target role, don't penalize it
    is_fractional_cmo = "fractional" in title_lower and "cmo" in title_lower
    if not is_fractional_cmo and any(sr in title_lower for sr in ["svp", "evp", "chief ", "cmo", "cco", "ceo"]):
        score -= 10

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

REMOTE_KEYWORDS = {
    "remote", "hybrid", "work from anywhere", "distributed", "wfh",
    "anywhere", "fully remote", "100% remote", "us remote", "remote-first",
    "remote first", "flexible location", "remote friendly",
}
AUSTIN_KEYWORDS = {"austin"}
ONSITE_CITY_BLOCKLIST = {
    "new york", "nyc", "brooklyn", "manhattan", "new york city",
    "los angeles", "santa monica", "culver city", "west hollywood", "burbank",
    "san francisco", "bay area", "palo alto", "mountain view", "menlo park",
    "seattle", "bellevue", "redmond",
    "chicago", "boston", "denver", "atlanta", "miami",
    "dallas", "houston", "philadelphia", "portland", "nashville",
    "san diego", "phoenix", "minneapolis", "washington, d.c", "washington dc",
    "toronto", "london", "berlin", "amsterdam", "paris",
}

def is_location_ok(location="", description=""):
    """Return True if the job is remote, hybrid, Austin-based, or location unknown."""
    loc = (location or "").lower().strip()
    desc = (description or "").lower()
    combined = f"{loc} {desc}"
    if any(kw in combined for kw in REMOTE_KEYWORDS):
        return True
    if any(kw in combined for kw in AUSTIN_KEYWORDS):
        return True
    if not loc:
        return True  # no location info → benefit of the doubt
    if any(city in loc for city in ONSITE_CITY_BLOCKLIST):
        return False
    return True  # some location not on blocklist → allow

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

def add_job(title, company, url, date_str="", source="", description="", location=""):
    if not title or not url:
        return
    if not is_ascii_title(title):
        return
    # Hard-stop: if the title itself signals a wrong function, skip immediately
    title_lower = title.lower()
    if any(hs in title_lower for hs in TITLE_HARDSTOP):
        return
    # Location filter — remote, hybrid, Austin, or unknown only
    if not is_location_ok(location, description):
        return
    if url in seen_urls:
        return
    tc_key = title.lower().strip() + "|" + company.lower().strip()
    if tc_key in seen_title_company:
        return
    seen_title_company.add(tc_key)
    if not is_recent(date_str):
        return
    loc_clean = (location or "").strip()
    desc_clean = clean_text(description)
    # Fold location into scoring so remote/Austin still get their bonus
    score = score_job(title, f"{desc_clean} {loc_clean}", company)
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
        "location": loc_clean,
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
    # Glassdoor now requires JS rendering — skip to avoid wasted timeouts
    pass

def scrape_wellfound():
    # Wellfound uses client-side JS rendering — HTML scraping returns empty shells.
    # Replaced by Remotive, We Work Remotely, and Remote OK scrapers below.
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
                loc_el = posting.select_one(".sort-by-location, .posting-category.location, [class*='location']")
                if title_el:
                    add_job(
                        title=title_el.text.strip(),
                        company=company.replace("-", " ").title(),
                        url=link_el["href"] if link_el else url,
                        source="Lever (Direct)",
                        location=loc_el.get_text(strip=True) if loc_el else "",
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
                loc = job.get("location", {})
                location = loc.get("name", "") if isinstance(loc, dict) else str(loc or "")
                add_job(
                    title=job.get("title", ""),
                    company=company.replace("-", " ").title(),
                    url=job.get("absolute_url", ""),
                    date_str=job.get("updated_at", ""),
                    source="Greenhouse (Direct)",
                    description=BeautifulSoup(job.get("content", "") or "", "html.parser").get_text(separator=" ").strip()[:300],
                    location=location,
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
    for q in SEARCH_QUERIES:
        try:
            encoded = q.replace(" ", "%20")
            # Three passes: Austin, US Remote location, + f_WT=2 (remote work type globally)
            url_configs = [
                f"https://www.linkedin.com/jobs/search/?keywords={encoded}&location=103644278&f_TPR=r1209600&sortBy=DD",
                f"https://www.linkedin.com/jobs/search/?keywords={encoded}&f_WT=2&f_TPR=r1209600&sortBy=DD",
                f"https://www.linkedin.com/jobs/search/?keywords={encoded}&location=90000070&f_TPR=r1209600&sortBy=DD",
            ]
            for url in url_configs:
                resp = requests.get(url, headers=HEADERS, timeout=12)
                soup = BeautifulSoup(resp.text, "html.parser")
                for card in soup.select(".job-search-card, .base-card")[:10]:
                    title_el = card.select_one(".base-search-card__title, h3")
                    company_el = card.select_one(".base-search-card__subtitle, h4")
                    link_el = card.select_one("a.base-card__full-link, a")
                    date_el = card.select_one("time")
                    loc_el = card.select_one(".job-search-card__location, .base-search-card__metadata span")
                    if title_el:
                        href = link_el.get("href", "") if link_el else ""
                        add_job(
                            title=title_el.text.strip(),
                            company=company_el.text.strip() if company_el else "",
                            url=href,
                            date_str=date_el.get("datetime", "") if date_el else "",
                            source="LinkedIn",
                            location=loc_el.get_text(strip=True) if loc_el else "",
                        )
        except Exception:
            pass

def scrape_remotive():
    """Remotive.io — free remote jobs API, no auth required."""
    print("  Scraping Remotive...")
    queries = [
        "partnerships", "brand manager", "brand marketing", "marketing manager",
        "creative strategist", "content strategist", "growth manager",
        "developer relations", "gaming", "go-to-market", "collaborations",
    ]
    seen = set()
    for q in queries:
        try:
            url = f"https://remotive.com/api/remote-jobs?search={q.replace(' ', '%20')}&limit=25"
            resp = requests.get(url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                continue
            for job in resp.json().get("jobs", []):
                if job.get("url") in seen:
                    continue
                seen.add(job.get("url", ""))
                add_job(
                    title=job.get("title", ""),
                    company=job.get("company_name", ""),
                    url=job.get("url", ""),
                    date_str=job.get("publication_date", ""),
                    source="Remotive",
                    description=BeautifulSoup(job.get("description", ""), "html.parser").get_text(separator=" ")[:400],
                    location=job.get("candidate_required_location", "remote"),
                )
        except Exception:
            pass

def scrape_weworkremotely():
    """We Work Remotely — RSS feeds by category, reliable and parseable."""
    print("  Scraping We Work Remotely...")
    feeds = [
        ("https://weworkremotely.com/categories/remote-marketing-jobs.rss", "WWR Marketing"),
        ("https://weworkremotely.com/categories/remote-business-management-jobs.rss", "WWR Business"),
        ("https://weworkremotely.com/categories/remote-copywriting-jobs.rss", "WWR Copywriting"),
        ("https://weworkremotely.com/categories/remote-design-jobs.rss", "WWR Design"),
    ]
    for feed_url, label in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:25]:
                title = entry.get("title", "")
                # WWR titles come as "Company: Role Title" — split them
                if ": " in title:
                    company_part, title_part = title.split(": ", 1)
                else:
                    company_part, title_part = "", title
                add_job(
                    title=title_part.strip(),
                    company=company_part.strip(),
                    url=entry.get("link", ""),
                    date_str=entry.get("published", ""),
                    source="We Work Remotely",
                    description=BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(separator=" ")[:400],
                )
        except Exception:
            pass

def scrape_remoteok():
    """Remote OK — JSON API, no auth required, remote-only listings."""
    print("  Scraping Remote OK...")
    tags = ["marketing", "partnerships", "brand", "growth", "gaming", "creative", "content"]
    seen = set()
    for tag in tags:
        try:
            resp = requests.get(
                f"https://remoteok.com/api?tags={tag}",
                headers={**HEADERS, "Accept": "application/json"},
                timeout=12,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            for job in data[1:]:  # first item is legal notice metadata
                if not isinstance(job, dict):
                    continue
                jurl = job.get("url", "")
                if jurl in seen:
                    continue
                seen.add(jurl)
                add_job(
                    title=job.get("position", ""),
                    company=job.get("company", ""),
                    url=jurl if jurl.startswith("http") else f"https://remoteok.com{jurl}",
                    date_str=job.get("date", ""),
                    source="Remote OK",
                    description=BeautifulSoup(job.get("description", ""), "html.parser").get_text(separator=" ")[:400],
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

def scrape_linkedin_contract():
    """
    LinkedIn guest API with Contract / Part-time / Temporary job type filters.
    This is the most reliable source for actual fractional/contract brand roles.
    Uses f_JT=C,T,P (Contract, Temporary, Part-time) + f_WT=2 (Remote).
    """
    print("  Scraping LinkedIn (contract/fractional roles)...")
    fractional_queries = [
        # Explicitly fractional
        "fractional CMO",
        "fractional head of marketing",
        "fractional brand",
        "fractional partnerships",
        "fractional creative director",
        "fractional GTM",
        "fractional marketing director",
        "fractional content strategist",
        "fractional growth",
        "fractional operator",
        "fractional brand strategist",
        # Contract/interim equivalents
        "contract brand manager",
        "contract creative director",
        "contract head of marketing",
        "contract partnerships manager",
        "contract creative producer",
        "contract content strategist",
        "contract marketing manager",
        "contract brand partnerships",
        "interim head of marketing",
        "interim brand manager",
        "interim CMO",
        "interim partnerships manager",
        "interim creative director",
        "part-time brand manager",
        "part-time creative director",
        "part-time head of growth",
        "part-time partnerships",
        # Broader operator roles that attract fractional talent
        "consulting brand strategy",
        "consulting marketing startup",
        "consulting partnerships",
        "brand advisor",
        "marketing advisor",
        "growth advisor",
        # Role-specific fractional variants
        "fractional brand manager",
        "fractional creative strategist",
        "fractional influencer marketing",
        "fractional creative producer",
        "fractional head of content",
        "fractional head of brand",
        "fractional ecommerce",
        "fractional partnerships director",
        "contract brand strategist",
        "contract influencer marketing",
        "contract creative strategist",
        "contract head of growth",
        "part-time marketing manager",
        "part-time content strategist",
        "part-time creative director",
        "interim head of brand",
        "interim marketing director",
        "freelance brand strategist",
        "freelance creative director",
        "freelance partnerships manager",
        "freelance marketing manager",
        "freelance content strategist",
    ]
    seen = set()
    for q in fractional_queries:
        for job_types in ["C,T,P", "C"]:  # Contract+Temp+PT first, then just Contract
            try:
                encoded = requests.utils.quote(q)
                url = (
                    f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                    f"?keywords={encoded}&f_JT={job_types}&f_WT=2&f_TPR=r604800&start=0"
                )
                resp = requests.get(url, headers=HEADERS, timeout=12)
                if resp.status_code != 200:
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")
                for card in soup.find_all("li"):
                    title_el = card.find("h3", class_="base-search-card__title")
                    company_el = card.find("h4", class_="base-search-card__subtitle")
                    link_el = card.find("a", class_="base-card__full-link")
                    date_el = card.find("time")
                    loc_el = card.find("span", class_="job-search-card__location")
                    if not title_el:
                        continue
                    href = link_el.get("href", "") if link_el else ""
                    if href in seen:
                        continue
                    seen.add(href)
                    add_job(
                        title=title_el.get_text(strip=True),
                        company=company_el.get_text(strip=True) if company_el else "",
                        url=href,
                        date_str=date_el.get("datetime", "") if date_el else "",
                        source="LinkedIn (Contract)",
                        location=loc_el.get_text(strip=True) if loc_el else "Remote",
                    )
            except Exception:
                pass


def scrape_fractionaljobs_io():
    """
    FractionalJobs.io — dedicated fractional job board.
    Page renders with all listings in static HTML as h3 triples:
    company_name / '-' / job_title (with company URL as external link).
    """
    print("  Scraping FractionalJobs.io...")
    try:
        r = requests.get("https://www.fractionaljobs.io/", headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return
        soup = BeautifulSoup(r.text, "html.parser")
        # Pattern: h3[company], h3['-'], h3[title] repeating
        h3_texts = [h.get_text(strip=True) for h in soup.find_all("h3")]
        # Also collect all external links (company URLs and apply links)
        ext_links = [a.get("href", "") for a in soup.find_all("a", href=True)
                     if a.get("href", "").startswith("http") and "fractionaljobs" not in a.get("href", "")]
        FRACTIONAL_RELEVANT = [
            "brand", "market", "partner", "creative", "content", "growth",
            "gtm", "go-to-market", "operator", "strategy", "strategist",
            "campaign", "collab", "influencer", "communications", "pr ",
            "experiential", "head of", "cmo", "director",
        ]
        ext_idx = 0
        for i in range(1, len(h3_texts) - 2, 3):
            company = h3_texts[i]
            sep = h3_texts[i + 1]
            title = h3_texts[i + 2]
            if sep != "-" or not company or not title:
                continue
            # Only pass through roles relevant to James's skill set
            if not any(k in title.lower() for k in FRACTIONAL_RELEVANT):
                ext_idx += 1
                continue
            # Grab the next available external link as the apply URL
            url = ext_links[ext_idx] if ext_idx < len(ext_links) else "https://www.fractionaljobs.io/"
            ext_idx += 1
            add_job(
                title=title,
                company=company,
                url=url,
                date_str="",
                source="FractionalJobs.io",
                location="Remote",
            )
    except Exception as e:
        print(f"    FractionalJobs.io error: {e}")


def scrape_wellfound_contract():
    """
    Wellfound (AngelList) — startup-focused job board.
    Scrapes contract/fractional roles at early-stage companies.
    """
    print("  Scraping Wellfound (startup fractional)...")
    queries = [
        "fractional CMO", "fractional brand", "fractional marketing",
        "fractional partnerships", "contract brand", "interim head of marketing",
        "brand advisor", "fractional creative",
    ]
    seen = set()
    for q in queries:
        try:
            encoded = requests.utils.quote(q)
            url = f"https://wellfound.com/jobs?q={encoded}&remote=true&job_type=contract"
            r = requests.get(url, headers=HEADERS, timeout=12)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for card in soup.find_all(["div", "li"], class_=re.compile(r"job|listing|card|role", re.I))[:12]:
                title_el = card.find(["h2", "h3", "a"])
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if len(title) < 5 or not any(k in title.lower() for k in
                    ["brand", "partner", "creative", "market", "content", "growth", "gtm", "fractional", "operator"]):
                    continue
                href = title_el.get("href", "") if title_el.name == "a" else ""
                if href and not href.startswith("http"):
                    href = "https://wellfound.com" + href
                if href in seen:
                    continue
                seen.add(href)
                company_el = card.find(["span", "p", "a"], class_=re.compile(r"company|startup|org", re.I))
                company = company_el.get_text(strip=True) if company_el else "Wellfound"
                add_job(
                    title=title,
                    company=company,
                    url=href or "https://wellfound.com/jobs",
                    date_str="",
                    source="Wellfound (Startup)",
                    location="Remote",
                )
        except Exception:
            pass


def scrape_contra():
    """
    Contra — freelance/fractional platform.
    Their main site is JS-rendered, but they expose opportunities via
    their search page with accessible markup when queried correctly.
    """
    print("  Scraping Contra (fractional platform)...")
    # Contra's search returns some server-side rendered cards with these patterns
    queries = ["brand", "marketing", "partnerships", "creative", "content", "growth"]
    seen = set()
    for q in queries:
        for remote_flag in ["true", ""]:
            try:
                url = f"https://contra.com/search?q={requests.utils.quote(q)}&type=opportunity"
                if remote_flag:
                    url += "&remote=true"
                r = requests.get(url, headers={**HEADERS, "Accept": "text/html,application/xhtml+xml"}, timeout=10)
                if r.status_code != 200:
                    continue
                soup = BeautifulSoup(r.text, "html.parser")
                # Look for any heading that reads like a job title
                for el in soup.find_all(["h1", "h2", "h3", "h4"]):
                    text = el.get_text(strip=True)
                    if len(text) < 5 or len(text) > 120:
                        continue
                    if not any(k in text.lower() for k in
                        ["brand", "partner", "creative", "market", "content", "growth", "gtm", "fractional", "operator"]):
                        continue
                    link_el = el.find_parent("a") or el.find("a")
                    href = link_el.get("href", "") if link_el else ""
                    if href and not href.startswith("http"):
                        href = "https://contra.com" + href
                    if href in seen:
                        continue
                    seen.add(href or text)
                    add_job(
                        title=text,
                        company="Contra",
                        url=href or "https://contra.com/search",
                        date_str="",
                        source="Contra (Fractional)",
                        location="Remote",
                    )
            except Exception:
                pass


def scrape_working_not_working():
    """
    Working Not Working — creative talent job board.
    Site renders JS but their RSS feed and /jobs listing page
    exposes some static listings we can parse.
    """
    print("  Scraping Working Not Working...")
    seen = set()
    # Try their RSS feed first
    for feed_url in [
        "https://workingnotworking.com/jobs.rss",
        "https://workingnotworking.com/feed",
        "https://workingnotworking.com/jobs/feed",
    ]:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:30]:
                title = entry.get("title", "")
                if not any(k in title.lower() for k in
                    ["brand", "creative", "content", "partner", "market", "strategy", "producer", "director"]):
                    continue
                link = entry.get("link", "https://workingnotworking.com/jobs")
                if link in seen:
                    continue
                seen.add(link)
                add_job(
                    title=title,
                    company="Working Not Working",
                    url=link,
                    date_str=entry.get("published", ""),
                    source="Working Not Working",
                    location="Remote",
                    description=BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:300],
                )
        except Exception:
            pass
    # Also try the main jobs page for any static HTML
    try:
        r = requests.get("https://workingnotworking.com/jobs", headers=HEADERS, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=re.compile(r"/jobs/\d+|/opportunities/\d+")):
                title = a.get_text(strip=True)
                href = a.get("href", "")
                if not title or len(title) < 5 or href in seen:
                    continue
                if not any(k in title.lower() for k in
                    ["brand", "creative", "content", "partner", "market", "strategy", "producer", "director"]):
                    continue
                seen.add(href)
                if not href.startswith("http"):
                    href = "https://workingnotworking.com" + href
                add_job(
                    title=title,
                    company="Working Not Working",
                    url=href,
                    date_str="",
                    source="Working Not Working",
                    location="Remote",
                )
    except Exception:
        pass


def scrape_himalayas():
    """
    Himalayas — remote jobs board with structured HTML listings.
    Their search page returns server-side rendered cards.
    """
    print("  Scraping Himalayas (remote jobs)...")
    queries = [
        "fractional brand manager",
        "fractional marketing",
        "fractional partnerships",
        "contract creative director",
        "brand manager",
        "partnerships manager",
        "creative strategist",
        "head of marketing",
        "content strategist",
        "growth marketing manager",
    ]
    seen = set()
    for q in queries:
        try:
            url = f"https://himalayas.app/jobs?q={requests.utils.quote(q)}&remote=true"
            r = requests.get(url, headers={
                **HEADERS,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }, timeout=12)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            # Himalayas uses data-* attributes and structured cards
            for card in soup.find_all(["article", "div", "li"],
                                      attrs={"data-job-id": True}):
                title_el = card.find(["h2", "h3", "h4"])
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                link_el = card.find("a", href=True)
                href = link_el.get("href", "") if link_el else ""
                if href and not href.startswith("http"):
                    href = "https://himalayas.app" + href
                if href in seen:
                    continue
                seen.add(href or title)
                company_el = card.find(["span", "p", "a"],
                                       class_=re.compile(r"company|employer|org", re.I))
                company = company_el.get_text(strip=True) if company_el else "Himalayas"
                add_job(
                    title=title,
                    company=company,
                    url=href or f"https://himalayas.app/jobs?q={requests.utils.quote(q)}",
                    date_str="",
                    source="Himalayas (Remote)",
                    location="Remote",
                )
            # Fallback: grab any job-title links from the page
            if not seen:
                for a in soup.find_all("a", href=re.compile(r"/jobs/[a-z0-9-]+")):
                    title = a.get_text(strip=True)
                    if not title or len(title) < 5:
                        continue
                    href = a.get("href", "")
                    if not href.startswith("http"):
                        href = "https://himalayas.app" + href
                    if href in seen:
                        continue
                    seen.add(href)
                    add_job(
                        title=title,
                        company="Himalayas",
                        url=href,
                        date_str="",
                        source="Himalayas (Remote)",
                        location="Remote",
                    )
        except Exception as e:
            print(f"    Himalayas error ({q}): {e}")


# ─────────────────────────────────────────────
# CONSULTING PROSPECT SCRAPERS
# ─────────────────────────────────────────────

prospects = []
seen_brands = set()

PROSPECT_INDUSTRIES = [
    "gaming", "dtc", "consumer", "lifestyle", "wellness", "cpg",
    "food", "beverage", "fashion", "apparel", "mental health",
    "editorial", "media", "creator economy", "music", "culture",
    "menswear", "men's", "outdoor", "surf", "heritage", "lifestyle goods",
    "functional", "running", "sportswear", "workwear",
    "healthcare", "health", "medtech", "digital health", "medical device",
    "biotech", "health tech", "clinical",
    "university", "higher education", "academic", "research", "education",
]

FOUNDER_SIGNALS = [
    "founder", "founder-led", "bootstrapped", "self-funded",
    "indie", "independent", "seed stage", "pre-series a", "early stage",
    "small team", "solo founder",
]

# Signals that the function/role doesn't exist yet — James fills the gap
HEADCOUNT_GAP_SIGNALS = [
    "no dedicated", "no partnerships", "no head of", "no brand",
    "founder-operated", "founder-driven", "founder doing it",
    "doing it themselves", "wearing all the hats", "first hire",
    "building the function", "zero infrastructure", "thin commercial",
    "underdeveloped", "not systematized", "minimal infrastructure",
    "commercial layer is the gap", "function is the gap",
    "execution gap", "no operator", "no commercial",
]

# Signals that there's real budget/traction but a missing operator
EXECUTION_GAP_SIGNALS = [
    "growing fast", "fast-growing", "rapid growth", "scaling",
    "strong brand", "strong community", "cult brand", "brand equity",
    "devoted community", "real traction", "clear gap", "room for",
    "untapped", "warrants more", "level the brand warrants",
    "fractional engagement", "fractional operator", "retainer",
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

    # Headcount/execution gap signals — the core of what James solves
    for sig in HEADCOUNT_GAP_SIGNALS:
        if sig in text:
            score += 3
            break  # one gap signal is enough — don't stack

    for sig in EXECUTION_GAP_SIGNALS:
        if sig in text:
            score += 2
            break  # one execution signal is enough

    # Explicit small headcount in gap description — strongest signal
    if any(hc in text for hc in ["1-10", "1-15", "3-10", "5-15", "5-20", "10-25", "10-30", "15-30"]):
        score += 2

    if "austin" in text or "texas" in text:
        score += 1

    # European companies that explicitly hire US remote/freelance — don't penalize
    if any(kw in text for kw in ["us remote", "us expansion", "us market", "contractor opportunity", "us-based"]):
        score += 2

    return max(score, 3)

def add_prospect(brand, founder="", contact="", contact_title="", gap="",
                 linkedin="", instagram="", website="", industry="",
                 revenue_est="", score=5, notes="", region="US",
                 fractional_role="", headcount="", engagement_type="fractional"):
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
        "fractional_role": fractional_role,
        "headcount": headcount,
        "engagement_type": engagement_type,  # fractional | consulting | retainer
        "added_date": datetime.now().strftime("%Y-%m-%d"),
    })

def seed_known_prospects():
    """Hardcoded high-priority prospects — active clients and named targets."""
    print("  Seeding known prospects...")

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
    # Ghia, Graza, Wondermind removed — too established per master context do-not-target list

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
    # Vacation Inc removed — too established per master context do-not-target list
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
        fractional_role="Fractional Brand & GTM Strategist",
        headcount="10-30",
    )

    # ── FRACTIONAL SWEET SPOT — 1-30 people, growing, need the function ──────
    add_prospect(
        brand="Everyday Dose",
        founder="Jack Savage",
        contact="Jack Savage",
        contact_title="Founder / CEO",
        gap="Everyday Dose is building in the functional coffee alternative space with a strong product and growing DTC presence. Small team, founder-operated, no dedicated partnerships or commercial infrastructure operator.",
        instagram="https://instagram.com/everydaydose",
        website="https://everydaydose.com",
        industry="Food & Beverage / Wellness",
        revenue_est="$2M-8M",
        score=9,
        notes="Named target — resume ready",
        fractional_role="Fractional Head of Partnerships",
        headcount="5-15",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Heart & Soil",
        founder="Paul Saladino",
        contact="Paul Saladino",
        contact_title="Founder / CEO",
        gap="Heart and Soil is a fast-growing organ supplement brand with a devoted community built around the carnivore and ancestral health movement. The brand partnership and commercial infrastructure is entirely founder-operated. No dedicated partnerships layer.",
        instagram="https://instagram.com/heartandsoilsupplements",
        website="https://heartandsoil.co",
        industry="Wellness / DTC",
        revenue_est="$5M-15M",
        score=9,
        notes="Named target — resume ready",
        fractional_role="Fractional Head of Partnerships",
        headcount="10-25",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Howler Brothers",
        founder="Adam Olson",
        contact="Adam Olson",
        contact_title="Co-Founder",
        gap="Howler Brothers is one of the most culturally credible outdoor and surf lifestyle brands in the market. Austin-based, founder-operated, with a strong community and editorial identity. The commercial partnership and collab layer is underdeveloped for the brand equity they carry.",
        instagram="https://instagram.com/howlerbros",
        website="https://howlerbros.com",
        industry="Apparel / Lifestyle",
        revenue_est="$5M-15M",
        score=9,
        notes="Named target — warm contact inside",
        fractional_role="Fractional Head of Partnerships",
        headcount="10-25",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Lomi",
        founder="Matt Bertulli",
        contact="Matt Bertulli",
        contact_title="Co-Founder / CEO",
        gap="Lomi built a genuine consumer category in home composting. The DTC brand is strong, the community is real, and the commercial partnership layer is not systematized. Small team with no dedicated partnerships operator.",
        instagram="https://instagram.com/lomi.world",
        website="https://lomi.com",
        industry="Sustainability / DTC",
        revenue_est="$10M-30M",
        score=8,
        notes="Small team — high responsiveness likelihood",
        fractional_role="Fractional Head of Partnerships",
        headcount="15-30",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Nguyen Coffee Supply",
        founder="Sahra Nguyen",
        contact="Sahra Nguyen",
        contact_title="Founder / CEO",
        gap="Nguyen Coffee Supply has built a strong brand identity around Vietnamese coffee culture with a devoted community. Small team, founder-operated, no dedicated brand partnership or commercial infrastructure operator.",
        instagram="https://instagram.com/nguyencoffeesupply",
        website="https://nguyencoffeesupply.com",
        industry="Food & Beverage / DTC",
        revenue_est="$2M-8M",
        score=8,
        notes="Small team — high responsiveness likelihood",
        fractional_role="Fractional Head of Partnerships",
        headcount="5-15",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Chamberlain Coffee",
        founder="Emma Chamberlain",
        contact="",
        contact_title="",
        gap="Chamberlain Coffee has strong brand recognition from the founder's platform but the commercial partnership infrastructure is not operating at the level the audience warrants. Small team behind a large name.",
        instagram="https://instagram.com/chamberlaincoffee",
        website="https://chamberlaincoffee.com",
        industry="Food & Beverage / DTC",
        revenue_est="$5M-20M",
        score=7,
        notes="Founder-celebrity brand — commercial layer is the gap",
        fractional_role="Fractional Head of Partnerships",
        headcount="10-25",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Canopy",
        founder="Ken Berkun",
        contact="Ken Berkun",
        contact_title="Founder / CEO",
        gap="Canopy is building in the home wellness and air quality space with a strong DTC brand and a growing community. Very small team, founder-operated, no dedicated partnerships or GTM operator.",
        instagram="https://instagram.com/canopyhumidifier",
        website="https://canopyhumidifier.com",
        industry="Wellness / DTC",
        revenue_est="$3M-10M",
        score=8,
        notes="Small team — high responsiveness likelihood",
        fractional_role="Fractional GTM Strategist",
        headcount="5-15",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Mela Watermelon Water",
        founder="Dominic Purpura",
        contact="Dominic Purpura",
        contact_title="Co-Founder / CEO",
        gap="Mela has built a genuinely differentiated product in the functional water space and is growing fast. Very small team, founder-operated, no dedicated partnerships or commercial infrastructure operator. Exactly the profile for fractional engagement.",
        instagram="https://instagram.com/drinkwatermelon",
        website="https://drinkwatermelon.com",
        industry="Food & Beverage / DTC",
        revenue_est="$1M-5M",
        score=8,
        notes="Early stage — high responsiveness likelihood",
        fractional_role="Fractional Head of Partnerships",
        headcount="3-10",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Public Goods",
        founder="Morgan Hirsh",
        contact="Morgan Hirsh",
        contact_title="Founder / CEO",
        gap="Public Goods is a membership-based sustainable essentials brand with a strong editorial identity and devoted community. The brand partnership and collab layer is underdeveloped. Small team, no dedicated operator.",
        instagram="https://instagram.com/publicgoods",
        website="https://publicgoods.com",
        industry="Sustainability / DTC",
        revenue_est="$5M-15M",
        score=7,
        notes="Small team — high responsiveness likelihood",
        fractional_role="Fractional Head of Brand",
        headcount="10-25",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Surreal Cereal",
        founder="Kit Gammell",
        contact="Kit Gammell",
        contact_title="Co-Founder / CEO",
        gap="Surreal has built a brand with a genuinely funny, irreverent voice in the functional food space. UK-based but active in the US market. Small team, founder-operated, strong brand, thin commercial infrastructure.",
        instagram="https://instagram.com/eatmoresurreal",
        website="https://eatmoresurreal.com",
        industry="Food & Beverage / DTC",
        revenue_est="$2M-8M",
        score=8,
        notes="UK-based, active US expansion — strong cultural fit",
        fractional_role="Fractional Head of Partnerships",
        headcount="5-15",
        engagement_type="fractional",
        region="EU",
    )

    # ── NET-NEW TARGETS — researched May 2026 ────────────────────────────────
    add_prospect(
        brand="Surely",
        founder="Brandon Joldersma",
        contact="Brandon Joldersma",
        contact_title="CEO",
        gap="Austin-based non-alcoholic wine brand. New CEO named Feb 2024 — classic inflection point where founders realize they need commercial infrastructure fast. Four employees, no dedicated partnerships or retail velocity function. Expanding SKUs but no one building the wholesale, on-premise, or collab pipeline.",
        instagram="https://instagram.com/drinksurely",
        website="https://drinksurely.com",
        industry="Non-Alcoholic / Functional Beverage",
        revenue_est="$2M-6M",
        score=9,
        notes="Austin-based — leadership inflection point, new CEO, post-raise",
        fractional_role="Fractional Head of Partnerships",
        headcount="4-8",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Gorgie",
        founder="Michelle Cordeiro Grant",
        contact="Michelle Cordeiro Grant",
        contact_title="Founder & CEO",
        gap="Functional energy/beauty beverage brand that just closed a $24.5M Series A in April 2025. Growing 5x YoY. Michelle is the brand — founder-operated commercial function. One influencer collab (Alix Earle) but no structured partnerships or creator program. Post-Series A is exactly when brands need fractional infrastructure before hiring a VP.",
        instagram="https://instagram.com/getgorgie",
        website="https://getgorgie.com",
        industry="Functional Beverage / Beauty / DTC",
        revenue_est="$8M-20M",
        score=9,
        notes="$24.5M Series A closed April 2025 — capital and mandate, no infrastructure",
        fractional_role="Fractional Head of Influencer & Creator Partnerships",
        headcount="15-25",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Sunwink",
        founder="Eliza Ganesh",
        contact="Eliza Ganesh",
        contact_title="Founder & CEO",
        gap="Functional herbal beverage DTC brand. Co-founder Jordan Schenck — the commercial and brand-facing co-founder — departed in 2024 to become Chief Brand Officer at Flashfood. That's a direct commercial leadership vacuum. Eliza is a product/operations founder. $14M raised, 12 people, strong community, but the brand partnership and influencer program is not built out.",
        instagram="https://instagram.com/drinksunwink",
        website="https://sunwink.com",
        industry="Functional Beverage / Wellness",
        revenue_est="$3M-8M",
        score=9,
        notes="Commercial co-founder departed — direct vacuum to fill",
        fractional_role="Fractional CMO / Head of Brand Partnerships",
        headcount="12",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Aura Bora",
        founder="Paul Voge",
        contact="Paul Voge",
        contact_title="Co-Founder & CEO",
        gap="Botanical sparkling water brand at $12M retail sales, 11,000 stores, still a 15-person husband-and-wife-founded company. Collab program (Graza olive oil martini etc.) is founder-driven and ad hoc — no dedicated partnerships person. Acquired by Next In Natural in Feb 2025, creating new ownership pressure to professionalize commercial operations.",
        instagram="https://instagram.com/aurabora",
        website="https://aurabora.com",
        industry="Functional Beverage / DTC",
        revenue_est="$10M-15M",
        score=8,
        notes="Post-acquisition by Next In Natural — new owners professionalizing",
        fractional_role="Fractional Head of Brand Partnerships",
        headcount="15",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Odyssey Elixir",
        founder="Scott Frohman",
        contact="Scott Frohman",
        contact_title="Founder & CEO",
        gap="Functional mushroom sparkling beverage. Post-Series A ($6.3M, March 2023) with VP of Marketing and VP of Sales hired, but no partnerships, influencer, or co-brand function. Direct competitor to Mud/Wtr and Clevr Blends — both of which have built influencer programs. Odyssey is expanding into CVS, Sprouts, and Central Market with no one owning the cultural and creator relationship layer.",
        instagram="https://instagram.com/odysseyelixir",
        website="https://odysseyelixir.com",
        industry="Functional Beverage / Wellness",
        revenue_est="$3M-8M",
        score=8,
        notes="Post-Series A, retail expansion, no partnerships function",
        fractional_role="Fractional Head of Creator & Brand Partnerships",
        headcount="10-18",
        engagement_type="fractional",
    )
    add_prospect(
        brand="WYNK",
        founder="Casey Parzych",
        contact="Casey Parzych",
        contact_title="Co-Founder & CEO",
        gap="THC-infused functional seltzer brand that quietly landed enterprise partnerships with Delta, Marriott, Levy Restaurants, and Virgin Voyages — all founder-hustle, none systematized. Three founders with backgrounds in energy trading, mechanical engineering, and beverage distribution. Zero marketing or commercial partnerships expertise on the team. THC beverages are going mainstream in 2025-2026 and there's no one building the brand partnership or creator program.",
        instagram="https://instagram.com/drinkwynk",
        website="https://drinkwynk.com",
        industry="Functional Beverage / Cannabis / DTC",
        revenue_est="$3M-8M",
        score=8,
        notes="THC mainstream moment — enterprise deals exist, no infrastructure",
        fractional_role="Fractional Head of Brand Partnerships & GTM Strategy",
        headcount="10-20",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Brami Snacks",
        founder="Aaron Gatti",
        contact="Aaron Gatti",
        contact_title="Founder & CEO",
        gap="Plant-based lupini bean protein snack brand, 10-person team, doubling revenue YoY with Assembled Brands growth capital deployed. No partnerships function. Lupini bean is a breakout ingredient with influencer and collab potential — no one is building brand deals or systematically running influencer programs at Brami. Founder does it all.",
        instagram="https://instagram.com/enjoybrami",
        website="https://enjoybrami.com",
        industry="Food & Beverage / CPG",
        revenue_est="$3M-8M",
        score=8,
        notes="Doubling YoY with capital deployed, no partnerships operator",
        fractional_role="Fractional Head of Brand & Influencer Partnerships",
        headcount="10",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Alder Apparel",
        founder="Mikayla Wujec",
        contact="Mikayla Wujec",
        contact_title="Co-Founder",
        gap="Sustainable inclusive outdoor apparel brand backed by REI Path Ahead Ventures. Six-person team — two founders doing everything. REI backing gives them retail credibility and access but no one is building the brand partnership, ambassador, or community program that outdoor brands need to compete. Cannot afford a senior CMO at this size; fractional is the clear path.",
        instagram="https://instagram.com/alderapparel",
        website="https://alderapparel.com",
        industry="Outdoor / Lifestyle / Sustainable Apparel",
        revenue_est="$2M-5M",
        score=8,
        notes="REI-backed, 6-person team, no CMO",
        fractional_role="Fractional Head of Partnerships / Fractional CMO",
        headcount="6",
        engagement_type="fractional",
    )
    add_prospect(
        brand="AVEC Drinks",
        founder="Alex Doman",
        contact="Alex Doman",
        contact_title="Co-Founder & CEO",
        gap="Premium cocktail mixers DTC brand backed by Pharrell's Black Ambition fund and Gather Ventures. Founder Alex Doman personally hand-selling and delivering to his first 30 accounts out of a 1995 Chevy Van — still a one-man commercial band. 1,200 retail doors but no brand collab program, no influencer partnership system, no structured on-premise sales infrastructure.",
        instagram="https://instagram.com/withavec",
        website="https://drinkavec.com",
        industry="Food & Beverage / DTC",
        revenue_est="$600K-2M",
        score=8,
        notes="Pharrell / Black Ambition backed — cultural credibility, founder-only commercial op",
        fractional_role="Fractional Head of Partnerships & Brand Strategy",
        headcount="3-8",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Akupara Games",
        founder="David Logan",
        contact="David Logan",
        contact_title="Founder & CEO",
        gap="Indie game publisher with 20-44 remote employees — 2023 was their best year ever with hits like Rain World: Downpour and Astrea. Operates without any external investment and without any formal partnerships or business development function. David Logan is the entire BD function personally. No developer acquisition partnerships, no media collab deals, no influencer programs. Too big to stay this lean commercially, too small to afford a full BD hire.",
        instagram="",
        website="https://akuparagames.com",
        industry="Gaming / Indie Publishing",
        revenue_est="$1M-3M",
        score=8,
        notes="Breakout 2023 — no BD function, founder is the entire commercial op",
        fractional_role="Fractional Head of Business Development & Developer Partnerships",
        headcount="20-44",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Graffiti Games",
        founder="Mihalis Belantis",
        contact="Mihalis Belantis",
        contact_title="Co-Founder",
        gap="Indie publisher of 18 games including Turnip Boy Commits Tax Evasion — a cult breakout with real IP, merchandise, and influencer deal potential. Original CEO/founder Alex Josef departed Dec 2022, leaving no clear commercial successor. 1-10 person publisher with a valuable catalog and zero partnerships infrastructure to monetize it.",
        instagram="",
        website="https://graffitigames.com",
        industry="Gaming / Indie Publishing",
        revenue_est="Sub-$1M",
        score=7,
        notes="Leadership transition — cult IP (Turnip Boy) with no commercial owner",
        fractional_role="Fractional Head of BD & Publisher Relations",
        headcount="1-10",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Matter of Fact",
        founder="Paul Baek",
        contact="Paul Baek",
        contact_title="Founder & CEO",
        gap="DTC clean skincare brand launched with $10M seed (Horizon Ventures, First Round). Paul Baek is a former K-pop singer turned Harvard grad turned formulator — not a commercial operator. Acquired by Next8 Investments (K18 and Olaplex veterans) in November 2024. New owners are actively rebuilding the commercial function. First structured retail partnership (CosmoProf exclusive) happened early 2025 but no systematic brand partnerships or influencer program exists.",
        instagram="https://instagram.com/matteroffact",
        website="https://matteroffact.com",
        industry="Beauty / DTC Skincare",
        revenue_est="$3M-8M",
        score=8,
        notes="Post-acquisition Nov 2024 — new owners (K18/Olaplex vets) actively rebuilding",
        fractional_role="Fractional Head of Brand Partnerships / Fractional CMO",
        headcount="16",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Trashy",
        founder="Kaitlin Mogentale",
        contact="Kaitlin Mogentale",
        contact_title="Founder & CEO",
        gap="Upcycled snack brand (formerly Pulp Pantry) that rebranded in 2024. Kaitlin renamed the company, relaunched the brand, and opened a Wefunder campaign — all while being a solo commercial operator on a 3-person team. Strong media narrative (Shark Tank, Upcycled Certified, food waste mission) that hasn't been monetized into brand deals or structured distribution partnerships.",
        instagram="https://instagram.com/trashy",
        website="https://trashychips.com",
        industry="Food & Beverage / Sustainable CPG",
        revenue_est="$500K-2M",
        score=7,
        notes="Fresh rebrand + crowdfund = inflection point, solo commercial operator",
        fractional_role="Fractional Brand Strategist & GTM Operator",
        headcount="3-6",
        engagement_type="fractional",
    )

    # ── MENSWEAR & LIFESTYLE GOODS — added May 2026 ──────────────────────────
    add_prospect(
        brand="Corridor NYC",
        founder="Dan Snyder",
        contact="Dan Snyder",
        contact_title="Founder & Designer",
        gap="American sportswear brand at ~$10M revenue with 17 employees — classic inflection point. Dan Snyder is running creative, design, production, and commercial strategy simultaneously. No dedicated partnerships director. Collab history is thin for the brand's revenue level — mostly retail, not cultural brand moments. Stocked at Mr. Porter, SSENSE, END but no systematic co-brand or creator program.",
        instagram="https://instagram.com/corridornyc",
        website="https://corridornyc.com",
        industry="Menswear / DTC / Lifestyle",
        revenue_est="$8M-12M",
        score=8,
        notes="$10M inflection — founder wearing all hats, collab history underdeveloped",
        fractional_role="Fractional Head of Partnerships & Brand Strategy",
        headcount="17",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Adsum",
        founder="Pete Macnee",
        contact="Pete Macnee",
        contact_title="Founder & Creative Director",
        gap="Menswear brand stocked at Dover Street Market, SSENSE, END, Mr. Porter, and Beams Japan — punching well above its weight class for a 5-10 person operation. Pete Macnee explicitly handles all design, development, and sales personally. Has done collabs (Gramicci, Vans, Merrell, Nanga, Reebok) — all founder-driven, no dedicated partnerships pipeline. Needs someone to develop the inbound/outbound collab pipeline so Pete can focus on design.",
        instagram="https://instagram.com/adsumnyc",
        website="https://adsumnyc.com",
        industry="Menswear / Outdoor / Lifestyle",
        revenue_est="$1M-5M",
        score=8,
        notes="Collab credentials proven (Vans, Reebok, Merrell) — no pipeline, all founder",
        fractional_role="Fractional Head of Brand Partnerships",
        headcount="5-10",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Metalwood Studio",
        founder="Cole Young",
        contact="Cole Young",
        contact_title="Founder & Creative Director",
        gap="Golf-meets-streetwear lifestyle brand at ~$10-15M revenue. Partnerships (adidas, FootJoy, Maxfli, Del Toro) come reactively — brands come to them because of cultural relevance, not because Metalwood has a proactive partnerships strategy. Post-raise ($28M) with international expansion pressure and no one building a systematic creator, athlete, or brand partnership pipeline. The window to shape the commercial identity before the brand scales past this stage is now.",
        instagram="https://instagram.com/metalwoodstudio",
        website="https://metalwood.studio",
        industry="Menswear / Golf / Lifestyle",
        revenue_est="$10M-15M",
        score=8,
        notes="Post-raise growth pressure — reactive partnerships need to become systematic",
        fractional_role="Fractional Head of Brand Partnerships & GTM Strategy",
        headcount="10-20",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Pilgrim Surf + Supply",
        founder="Chris Gentile",
        contact="Chris Gentile",
        contact_title="Co-Founder & CEO",
        gap="One of the most credible lifestyle/surf/menswear retail-to-brand crossovers in the US. International partnership with Beams (Tokyo/Kyoto stores) proves they can execute on brand relationships. But with only 7 employees and ~$13M revenue, Chris Gentile is running commercial strategy alongside everything else. No dedicated partnerships or wholesale growth operator. At this revenue level, the brand either builds commercial infrastructure or plateaus.",
        instagram="https://instagram.com/pilgrimsurfsupply",
        website="https://pilgrimsurfsupply.com",
        industry="Surf / Lifestyle / Menswear",
        revenue_est="$10M-15M",
        score=9,
        notes="7 employees at $13M — no dedicated commercial op, Beams collab proves the model",
        fractional_role="Fractional Head of Brand Partnerships & Retail Expansion",
        headcount="7-9",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Blackstock & Weber",
        founder="Chris Echevarria",
        contact="Chris Echevarria",
        contact_title="Founder & Creative Director",
        gap="Chris Echevarria is one of the most in-demand men's style figures in the US — Kith, Pharrell's BBC, Sperry have all come to him. Every partnership deal flows through Chris personally. He is simultaneously running Blackstock & Weber and launching Academy (a new apparel line) — both need commercial infrastructure he cannot give them alone. The Academy launch is the specific gap: it needs GTM attention Chris cannot fully provide.",
        instagram="https://instagram.com/blackstockandweber",
        website="https://blackstockandweber.com",
        industry="Menswear / Footwear / Lifestyle",
        revenue_est="$1M-5M",
        score=8,
        notes="Academy launch = new GTM need, every deal is founder-only, Pharrell/Kith credibility",
        fractional_role="Fractional Head of Brand Partnerships & GTM",
        headcount="7",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Dehen 1920",
        founder="Gary Hilde",
        contact="Gary Hilde",
        contact_title="President & Master Knitter",
        gap="America's best varsity and knit jacket maker — family-owned since 1920, Portland OR, 70-80 global boutique accounts (Berlin, Tokyo, Paris). Just opened their first public storefront. No brand partnerships strategy, no creator outreach, no proactive commercial pipeline. Their product is exactly what menswear creators and heritage-adjacent brands want to co-brand — no one is building that pipeline. A maker's operation that needs a fractional commercial operator to unlock partnership revenue.",
        instagram="https://instagram.com/dehen1920",
        website="https://dehen1920.com",
        industry="Menswear / Heritage / Lifestyle Goods",
        revenue_est="$3M-6M",
        score=7,
        notes="New storefront = growth signal, maker mentality, no partnerships pipeline",
        fractional_role="Fractional Head of Brand Partnerships & Creator Strategy",
        headcount="11-35",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Carter Young",
        founder="Carter Altman",
        contact="Carter Altman",
        contact_title="Founder & Designer",
        gap="New Americana menswear brand with extraordinary press heat for its size — Vogue, NYT, WWD, Forbes, GQ coverage. Pedigree includes Helmut Lang, Kith womenswear, 1017 ALYX 9SM. Notable wearers include Ethan Hawke and Interpol's Paul Banks. Made in NYC garment district. But: no wholesale strategy, no creator program, no brand partnerships, no commercial structure whatsoever. There's a 12-18 month window before the press momentum fades without commercial conversion.",
        instagram="https://instagram.com/carteryoungus",
        website="https://carteryoungus.com",
        industry="Menswear / DTC",
        revenue_est="Under $1M",
        score=7,
        notes="Press heat (NYT, Vogue, GQ) with zero commercial infrastructure — 12-18mo window",
        fractional_role="Fractional GTM Strategist & Brand Partnerships",
        headcount="3-5",
        engagement_type="fractional",
    )

    # ── TRAVEL & ACCESSORIES — Opulist background ────────────────────────────
    add_prospect(
        brand="Paravel",
        founder="Indré Rockefeller",
        contact="Indré Rockefeller",
        contact_title="Co-Founder",
        gap="Paravel has built one of the most visually coherent sustainable luggage brands in the market. Founder-led creative identity, strong editorial voice, genuinely differentiated product. The commercial partnership layer — brand collabs, travel partnerships, wholesale strategy — is underdeveloped relative to what the brand's aesthetic equity could support.",
        instagram="https://instagram.com/travelparavel",
        website="https://travelparavel.com",
        industry="Travel / Sustainable Accessories",
        revenue_est="$10M-30M",
        score=8,
        notes="Founder-led brand with underbuilt commercial layer",
        fractional_role="Fractional Brand Partnerships & GTM",
        headcount="15-30",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Pakt",
        founder="Chad Rubin",
        contact="Chad Rubin",
        contact_title="Co-Founder",
        gap="Pakt makes minimal, carry-on-only travel bags for people who travel intentionally. Extremely small team, founder-operated, product-first. The brand has a clear POV and a devoted early community but no partnerships, collab, or GTM infrastructure built.",
        instagram="https://instagram.com/paktbag",
        website="https://paktbag.com",
        industry="Travel / Accessories / DTC",
        revenue_est="$1M-5M",
        score=8,
        notes="Tiny team, founder-operated, strong niche brand",
        fractional_role="Fractional Brand & GTM Operator",
        headcount="3-8",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Abroad",
        founder="",
        contact="",
        contact_title="Founder",
        gap="Abroad is building a travel lifestyle brand around intentional, slower travel. Editorial-forward, community-driven, founder-operated. Strong fit for turning engaged travel content into commercial partnerships with hotels, gear, and experience brands.",
        instagram="https://instagram.com/abroad",
        website="https://abroadlife.com",
        industry="Travel / Editorial / Lifestyle",
        revenue_est="Under $2M",
        score=7,
        notes="Early stage — travel editorial background is a direct match",
        fractional_role="Fractional Partnerships & Brand",
        headcount="2-8",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Monos",
        founder="Victor Tam",
        contact="Victor Tam",
        contact_title="Co-Founder & CEO",
        gap="Monos has built exceptional brand credibility in design-forward luggage and is growing aggressively in the US market from a Canada base. The partnership and collaboration infrastructure has not kept pace with the brand's aesthetic ambition. No dedicated partnerships operator.",
        instagram="https://instagram.com/monos",
        website="https://monos.com",
        industry="Travel / Accessories / DTC",
        revenue_est="$20M-50M",
        score=7,
        notes="Canada-based, aggressive US expansion — partnership gap",
        fractional_role="Fractional Brand Partnerships",
        headcount="30-60",
        engagement_type="fractional",
        region="EU",
    )

    # ── SPORTS / RUNNING CULTURE — Fandom sports vertical + athletic editorial ─
    add_prospect(
        brand="JANJI",
        founder="Dave Spandorfer",
        contact="Dave Spandorfer",
        contact_title="Co-Founder & CEO",
        gap="JANJI makes running apparel and uses a percentage of revenue to fund water projects in the countries their fabrics come from. Strong community, clear social mission, genuine brand identity. Small team, founder-operated, and the commercial partnership layer — brand collabs, ambassador programs, race partnerships — has room to be built into a real commercial asset.",
        instagram="https://instagram.com/janjisports",
        website="https://janji.com",
        industry="Running / Athletic Lifestyle / Social Impact",
        revenue_est="$5M-15M",
        score=8,
        notes="Mission-driven brand with community — partnership infrastructure gap",
        fractional_role="Fractional Brand Partnerships & GTM",
        headcount="10-20",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Bandit Running",
        founder="Nils Arend",
        contact="Nils Arend",
        contact_title="Co-Founder",
        gap="Bandit Running has built one of the most culturally resonant brands in the running space. Born in NYC, community-first, genuinely underground before it became the brand of the running revival moment. Very small team, the brand partnerships and collab program is founder-run and ad hoc. There is a real commercial layer to build here before the moment passes.",
        instagram="https://instagram.com/banditrunning",
        website="https://banditrunning.com",
        industry="Running / Athletic Culture / DTC",
        revenue_est="$2M-8M",
        score=9,
        notes="Peak cultural moment — commercial infrastructure needs to catch up",
        fractional_role="Fractional Brand & Partnerships Operator",
        headcount="5-15",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Ciele Athletics",
        founder="Mike Giles",
        contact="Mike Giles",
        contact_title="Co-Founder",
        gap="Ciele has become the hat brand of the running culture moment. Montreal-based, US-expanding, deeply community-oriented. The brand identity is strong and the audience is committed. The commercial partnership and collab infrastructure is not built to the level the brand equity warrants.",
        instagram="https://instagram.com/cieleathletiques",
        website="https://cieleathletiques.com",
        industry="Running / Athletic Accessories",
        revenue_est="$5M-20M",
        score=7,
        notes="Canada-based, strong US cultural moment — commercial gap",
        fractional_role="Fractional Brand Partnerships",
        headcount="15-30",
        engagement_type="fractional",
        region="EU",
    )
    add_prospect(
        brand="Rabbit Running",
        founder="Monica DeVreese",
        contact="Monica DeVreese",
        contact_title="Co-Founder",
        gap="Rabbit makes running apparel with a California-casual identity and a genuine community around the brand. Small team, founder-operated. The partnership and ambassador infrastructure is informal and the commercial layer is underdeveloped relative to the brand's reach in the running community.",
        instagram="https://instagram.com/runinrabbit",
        website="https://runinrabbit.com",
        industry="Running / Athletic Lifestyle",
        revenue_est="$5M-12M",
        score=7,
        notes="Small team, community-strong — partnership layer to build",
        fractional_role="Fractional Brand & GTM",
        headcount="10-20",
        engagement_type="fractional",
    )

    # ── STREETWEAR / CULTURAL FASHION — gaming/entertainment/culture crossover ─
    add_prospect(
        brand="Museum of Peace and Quiet",
        founder="Aaron Bondaroff",
        contact="Aaron Bondaroff",
        contact_title="Founder",
        gap="Museum of Peace and Quiet has one of the most distinct brand identities in LA streetwear and lifestyle. Cultural credibility, editorial sensibility, deep creative community. The brand is founder-operated with no structured commercial partnership program. The crossover between gaming, music, and street culture is exactly where James's background maps.",
        instagram="https://instagram.com/museumofpeaceandquiet",
        website="https://museumofpeaceandquiet.com",
        industry="Streetwear / Cultural Lifestyle",
        revenue_est="$3M-10M",
        score=8,
        notes="Cultural credibility without commercial infrastructure",
        fractional_role="Fractional Brand Partnerships & Collabs",
        headcount="5-15",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Awake NY",
        founder="Angelo Baque",
        contact="Angelo Baque",
        contact_title="Founder & Creative Director",
        gap="Angelo Baque built one of the most culturally connected streetwear brands in New York. Deep relationships across music, art, and sports. The commercial partnership layer — brand collabs, licensing, retail strategy — is founder-run and selective. A fractional operator who understands both the creative credibility and the commercial opportunity is exactly what this brand needs.",
        instagram="https://instagram.com/awakeny",
        website="https://awakeny.com",
        industry="Streetwear / Cultural Fashion",
        revenue_est="$2M-8M",
        score=7,
        notes="High creative credibility, founder-operated commercial layer",
        fractional_role="Fractional Brand & Partnerships Operator",
        headcount="5-12",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Market",
        founder="Brandon Svarc",
        contact="Brandon Svarc",
        contact_title="Founder",
        gap="Market (formerly Grocery) has built a distinctive irreverent streetwear brand with real cultural cachet and a growing retail footprint. The brand does humor and community better than almost anyone at their size. The commercial partnership and brand collab program is informal and has room to be systematized.",
        instagram="https://instagram.com/shopmarket",
        website="https://shopmarket.com",
        industry="Streetwear / DTC / Cultural Fashion",
        revenue_est="$3M-10M",
        score=7,
        notes="Irreverent brand voice — collab and partnership program to build",
        fractional_role="Fractional Brand Partnerships",
        headcount="5-15",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Noon Goons",
        founder="Andrew Morrison",
        contact="Andrew Morrison",
        contact_title="Founder",
        gap="Noon Goons sits at the intersection of skate, surf, and LA streetwear with a genuine aesthetic identity. Small team, founder-operated, strong retail relationships. The brand partnership and collab infrastructure is informal — no dedicated operator building the commercial layer.",
        instagram="https://instagram.com/noongoons",
        website="https://noongoons.com",
        industry="Skate / Surf / Streetwear",
        revenue_est="$1M-5M",
        score=7,
        notes="Founder-operated, authentic subculture brand",
        fractional_role="Fractional Brand Partnerships",
        headcount="3-10",
        engagement_type="fractional",
    )

    # ── CREATOR ECONOMY / NEWSLETTER — Fandom audience intelligence background ─
    add_prospect(
        brand="Blackbird Spyplane",
        founder="Jonah Weiner",
        contact="Jonah Weiner",
        contact_title="Co-Founder & Editor",
        gap="Blackbird Spyplane is the most culturally credible fashion and lifestyle newsletter in the game. Real editorial authority, devoted reader base, and a POV that brands genuinely want to be adjacent to. The commercial partnership layer — brand integrations, sponsored deep dives, product collabs — is founder-run and not systematized. There is a meaningful commercial layer to build here without touching the editorial integrity.",
        instagram="https://instagram.com/blackbirdspyplane",
        website="https://blackbirdspyplane.substack.com",
        industry="Creator Economy / Editorial / Fashion",
        revenue_est="$500K-2M",
        score=8,
        notes="High editorial authority — commercial layer needs an operator",
        fractional_role="Fractional Commercial Partnerships",
        headcount="2-5",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Dirt",
        founder="Kate Lindsay",
        contact="Kate Lindsay",
        contact_title="Co-Founder",
        gap="Dirt is a culture and internet newsletter with genuine critical authority and a growing reader base. Small operation, founder-run, and the commercial partnership infrastructure is minimal. The Fandom background — understanding how editorial and brand coexist — maps directly to what this publication needs.",
        instagram="https://instagram.com/dirtdotfyi",
        website="https://dirt.fyi",
        industry="Creator Economy / Internet Culture / Editorial",
        revenue_est="Under $500K",
        score=7,
        notes="Early-stage editorial brand — brand partnership layer to build",
        fractional_role="Fractional Brand & Partnerships",
        headcount="2-5",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Every",
        founder="Dan Shipper",
        contact="Dan Shipper",
        contact_title="Co-Founder & CEO",
        gap="Every is building a high-quality newsletter bundle at the intersection of technology, business, and culture. Growing subscriber base, strong brand among professional audiences. The commercial partnership layer — sponsorships, brand integrations, product collabs — is not built out at the level the audience warrants.",
        instagram="",
        website="https://every.to",
        industry="Creator Economy / Business Media",
        revenue_est="$1M-5M",
        score=7,
        notes="High-quality audience, underbuilt commercial layer",
        fractional_role="Fractional Brand Partnerships",
        headcount="5-15",
        engagement_type="fractional",
    )

    # ── MUSIC / CULTURE — Fandom music/entertainment vertical ────────────────
    add_prospect(
        brand="Ghostly International",
        founder="Sam Valenti IV",
        contact="Sam Valenti IV",
        contact_title="Founder",
        gap="Ghostly International has one of the most coherent aesthetic identities of any independent label — visual design, artist curation, merchandise, and brand are all part of a unified world. Small team, founder-operated. The brand partnership and licensing infrastructure is not built to the level the label's cultural credibility warrants.",
        instagram="https://instagram.com/ghostlyintl",
        website="https://ghostly.com",
        industry="Music / Indie Label / Culture",
        revenue_est="$2M-8M",
        score=8,
        notes="Extraordinary brand identity — partnership layer gap",
        fractional_role="Fractional Brand Partnerships & Licensing",
        headcount="5-15",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Numero Group",
        founder="Ken Shipley",
        contact="Ken Shipley",
        contact_title="Co-Founder",
        gap="Numero Group is one of the most culturally important reissue labels operating right now. Deep curatorial identity, devoted collector audience, and incredible visual output. The commercial partnership layer — brand collabs, licensing, cultural integrations — is essentially nonexistent. There is a real opportunity to build commercial infrastructure without compromising curatorial integrity.",
        instagram="https://instagram.com/numerogroup",
        website="https://numerogroup.com",
        industry="Music / Reissue / Culture",
        revenue_est="$1M-5M",
        score=7,
        notes="Extraordinary curatorial brand — zero commercial infrastructure",
        fractional_role="Fractional Brand & Commercial Partnerships",
        headcount="5-10",
        engagement_type="fractional",
    )
    add_prospect(
        brand="indify",
        founder="Will Huston",
        contact="Will Huston",
        contact_title="Co-Founder & CEO",
        gap="indify is building infrastructure for independent artists to raise funding and build commercial relationships directly. Small team, fast-growing, operating at the intersection of music, creator economy, and brand. The GTM and partnership infrastructure is founder-operated and not yet systematized.",
        instagram="https://instagram.com/indifymusic",
        website="https://indify.co",
        industry="Music / Creator Economy / Fintech",
        revenue_est="$1M-5M",
        score=7,
        notes="Music + creator economy crossover — GTM gap",
        fractional_role="Fractional GTM & Brand Partnerships",
        headcount="5-15",
        engagement_type="fractional",
    )

    # ── HERITAGE CRAFT / MADE IN USA — Uncle Bill's / Seager Hats background ─
    add_prospect(
        brand="Rogue Territory",
        founder="Kyle Mowat",
        contact="Kyle Mowat",
        contact_title="Founder",
        gap="Rogue Territory makes some of the best selvedge denim and workwear in Los Angeles. Small team, founder-operated, deep community of devotees. The brand has real heritage credibility but no commercial partnership or brand collab infrastructure. Wholesale relationships are informal, the brand partnership layer is nonexistent.",
        instagram="https://instagram.com/rogueterritory",
        website="https://rogueterritory.com",
        industry="Heritage / Menswear / Made in USA",
        revenue_est="$1M-5M",
        score=7,
        notes="Heritage craft brand — founder-operated with real collab potential",
        fractional_role="Fractional Brand Partnerships & GTM",
        headcount="3-10",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Imogene + Willie",
        founder="Matt & Carrie Eddmenson",
        contact="Matt Eddmenson",
        contact_title="Co-Founder",
        gap="Imogene + Willie makes handmade denim out of Nashville with a genuine American craft story and a devoted following. Tiny team, founder-operated, deeply local identity. The commercial partnership layer — brand collabs, wholesale strategy, maker-brand integrations — is essentially not built. The Uncle Bill's and Seager Hats experience maps directly here.",
        instagram="https://instagram.com/imogeneandwillie",
        website="https://imogeneandwillie.com",
        industry="Heritage / Denim / Made in USA",
        revenue_est="$2M-6M",
        score=7,
        notes="Maker brand with devoted community — no commercial layer built",
        fractional_role="Fractional GTM & Brand Partnerships",
        headcount="5-15",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Billykirk",
        founder="Chris Bray",
        contact="Chris Bray",
        contact_title="Co-Founder",
        gap="Billykirk has built one of the most respected small leather goods brands in the US. Handmade, family-operated, deeply craft-oriented. The brand identity is exceptional but the commercial infrastructure — wholesale, brand partnerships, retail strategy — is founder-operated and not growing at the rate the product quality warrants.",
        instagram="https://instagram.com/billykirk",
        website="https://billykirk.com",
        industry="Heritage / Leather Goods / Made in USA",
        revenue_est="$500K-2M",
        score=7,
        notes="Family-operated craft brand — real partnership and wholesale gap",
        fractional_role="Fractional Brand & Commercial Partnerships",
        headcount="3-8",
        engagement_type="fractional",
    )

    # ── GAMING (DEEPER) — indie.io + Fandom background ──────────────────────
    add_prospect(
        brand="Humble Games",
        founder="",
        contact="",
        contact_title="Head of Publishing",
        gap="Humble Games publishes a strong catalog of indie titles and has real brand equity from the Humble Bundle legacy. The brand partnership and creator program infrastructure is not built out at the scale the catalog and community warrants. Mid-size, with room for a dedicated partnerships operator.",
        instagram="https://instagram.com/humblegames",
        website="https://humblegames.com",
        industry="Gaming / Indie Publishing",
        revenue_est="$10M-40M",
        score=7,
        notes="Strong catalog, underbuilt brand partnership layer",
        fractional_role="Fractional Brand Partnerships & Creator",
        headcount="20-50",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Fellow Traveller",
        founder="Chris Wright",
        contact="Chris Wright",
        contact_title="Director",
        gap="Fellow Traveller publishes narrative and walking simulator games with a distinctive curatorial identity — the games label equivalent of A24. Small team, founder-operated, strong critical reputation. The commercial partnership and creator program infrastructure is minimal relative to the brand's cultural credibility.",
        instagram="https://instagram.com/ftgames",
        website="https://fellowtraveller.games",
        industry="Gaming / Indie Publishing / Narrative",
        revenue_est="$1M-5M",
        score=8,
        notes="A24 of games — brand identity without commercial infrastructure",
        fractional_role="Fractional Brand & Creator Partnerships",
        headcount="5-15",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Playstack",
        founder="Harvey Elliott",
        contact="Harvey Elliott",
        contact_title="CEO",
        gap="Playstack publishes mid-size indie games and is growing aggressively. The brand partnership, influencer, and creator program infrastructure is not built out. London-based with active US expansion — a fractional US partnerships operator makes sense at this stage.",
        instagram="https://instagram.com/playstack",
        website="https://playstack.com",
        industry="Gaming / Indie Publishing",
        revenue_est="$5M-20M",
        score=7,
        notes="London-based, US expansion mode — fractional US partnerships fit",
        fractional_role="Fractional Brand & Creator Partnerships (US)",
        headcount="15-30",
        engagement_type="fractional",
        region="EU",
    )

    # ── EXPERIENTIAL / BRAND ACTIVATION — Smilebooth background ─────────────
    add_prospect(
        brand="Fly By Jing",
        founder="Jing Gao",
        contact="Jing Gao",
        contact_title="Founder & CEO",
        gap="Fly By Jing has built a category-defining brand around Sichuan flavors and a strong founder identity. The experiential and brand partnership layer — pop-ups, chef collabs, cultural activations — is founder-operated and event-driven but not systematized. The Smilebooth experience (building experiential frameworks that connect brand moments to ongoing relationships) maps directly to what Jing is doing with the brand.",
        instagram="https://instagram.com/flybyjing",
        website="https://flybyjing.com",
        industry="Food & Beverage / Experiential / DTC",
        revenue_est="$5M-20M",
        score=8,
        notes="Experiential and collab layer is founder-operated — gap for operator",
        fractional_role="Fractional Brand Partnerships & Experiential",
        headcount="10-25",
        engagement_type="fractional",
    )
    add_prospect(
        brand="Blind Barber",
        founder="Jeff Laub",
        contact="Jeff Laub",
        contact_title="Co-Founder",
        gap="Blind Barber operates at the intersection of grooming, hospitality, and creative culture — barbershop-as-community-space, product brand, and event venue. The brand partnership and commercial activation layer is not built out at the level the concept's cultural position warrants. The Smilebooth framework (brand moment to ongoing relationship) maps directly to their physical experience model.",
        instagram="https://instagram.com/blindbarber",
        website="https://blindbarber.com",
        industry="Grooming / Experiential / Lifestyle",
        revenue_est="$5M-15M",
        score=7,
        notes="Hospitality + brand + grooming — experiential partnership gap",
        fractional_role="Fractional Brand & Experiential Partnerships",
        headcount="15-30",
        engagement_type="fractional",
    )

def seed_known_agencies():
    """Return the curated list of boutique creative agencies for James to target."""
    return [
        # ── Austin ────────────────────────────────────────────────
        {"id":"preacher","name":"Preacher","city":"Austin, TX","location_type":"Austin","type":"Creative Agency","size":"20-50",
         "focus":"Full-service creative and brand agency. Austin-based. Challenger brands and cultural storytelling.",
         "why_relevant":"Austin-based means in-person relationship building. Right size for a fractional operator to matter.",
         "website":"https://preacher.co","linkedin":"https://www.linkedin.com/company/preacher-co/","instagram":"",
         "platforms":["Direct outreach","Working Not Working"],"score":8},
        {"id":"mcgarrah-jessee","name":"McGarrah Jessee","city":"Austin, TX","location_type":"Austin","type":"Creative Agency","size":"20-50",
         "focus":"Craft-first independent creative agency. Austin-based. Known for brand storytelling and quality over volume.",
         "why_relevant":"Local Austin agency with a long track record. Freelance or project-basis entry point.",
         "website":"https://mcgarrahjessee.com","linkedin":"https://www.linkedin.com/company/mcgarrah-jessee/","instagram":"",
         "platforms":["Direct outreach"],"score":7},
        {"id":"sunday-afternoon","name":"Sunday Afternoon","city":"Austin, TX","location_type":"Austin","type":"Brand Studio","size":"under 20",
         "focus":"Small brand studio, Austin. Consumer-focused, design-led.",
         "why_relevant":"Austin-based. Very small means every person matters and project relationships are the norm.",
         "website":"https://www.sundayafternoon.us","linkedin":"","instagram":"",
         "platforms":["Direct outreach"],"score":7},
        # ── National boutiques (remote-friendly, under 50) ────────
        {"id":"red-antler","name":"Red Antler","city":"New York, NY","location_type":"Remote","type":"Brand Studio","size":"20-50",
         "focus":"Consumer startup brand studio. Behind Casper, Allbirds, Hims. Actively brings in freelance talent on a project basis.",
         "why_relevant":"Primary target. Actively uses freelancers. Consumer startups is exactly the terrain. Working Not Working is the entry point.",
         "website":"https://redantler.com","linkedin":"https://www.linkedin.com/company/red-antler/","instagram":"https://instagram.com/redantler",
         "platforms":["Working Not Working","Direct outreach"],"score":9},
        {"id":"mythology","name":"Mythology","city":"New York, NY","location_type":"Remote","type":"Brand Studio","size":"under 20",
         "focus":"Brand studio with a strong cultural POV. NYC-based. Premium consumer brand work with genuine strategic depth.",
         "why_relevant":"Cultural brand work with strategic rigor is the exact overlap. Project relationships are the entry point.",
         "website":"https://wearemythology.com","linkedin":"https://www.linkedin.com/company/mythology/","instagram":"https://instagram.com/wearemythology",
         "platforms":["Working Not Working","Direct outreach"],"score":8},
        {"id":"humanaut","name":"Humanaut","city":"Chattanooga, TN","location_type":"Remote","type":"Creative Agency","size":"20-50",
         "focus":"Fully remote-friendly creative agency. Purpose-led brands. Known for Oatly, Athletic Greens.",
         "why_relevant":"Fully remote friendly. Purpose-led consumer brands in wellness is James's terrain. Actively uses freelancers.",
         "website":"https://humanaut.com","linkedin":"https://www.linkedin.com/company/humanaut/","instagram":"https://instagram.com/humanaut",
         "platforms":["Working Not Working","Contra","Direct outreach"],"score":8},
        {"id":"established","name":"Established","city":"New York, NY","location_type":"Remote","type":"Brand Studio","size":"under 20",
         "focus":"Brand studio focused on consumer brands. NYC-based. Small team that brings in project talent.",
         "why_relevant":"Consumer brand focus. Small enough that a strong freelancer gets real work.",
         "website":"https://established.design","linkedin":"","instagram":"",
         "platforms":["Working Not Working","Direct outreach"],"score":7},
        {"id":"quality-meats","name":"Quality Meats","city":"New York, NY","location_type":"Remote","type":"Creative Studio","size":"under 20",
         "focus":"Boutique creative studio. Pop culture-savvy, brand-forward work. NYC.",
         "why_relevant":"Pop culture and brand work is the right intersection. Small studio means project work is the primary model.",
         "website":"https://qualitymeats.nyc","linkedin":"","instagram":"https://instagram.com/qualitymeatsnyc",
         "platforms":["Working Not Working","Direct outreach"],"score":7},
        {"id":"oddfellows","name":"Oddfellows","city":"Portland, OR","location_type":"Remote","type":"Creative Studio","size":"20-50",
         "focus":"Motion and brand studio. Remote-friendly. Known for animated brand work and cultural clients.",
         "why_relevant":"Remote-friendly. Brand and cultural work is the overlap. Strategy and partnerships framing is the entry point.",
         "website":"https://oddfellows.tv","linkedin":"https://www.linkedin.com/company/oddfellows/","instagram":"https://instagram.com/oddfellows",
         "platforms":["Working Not Working","Direct outreach"],"score":7},
        {"id":"franklyn","name":"Franklyn","city":"New York, NY","location_type":"Remote","type":"Brand Studio","size":"under 20",
         "focus":"Small brand studio, NYC. Craft and identity-focused. Selective client roster.",
         "why_relevant":"Small studio means every relationship matters. Brand and cultural work. Project-based model.",
         "website":"https://franklyn.co","linkedin":"","instagram":"https://instagram.com/franklyn.co",
         "platforms":["Direct outreach","Working Not Working"],"score":7},
        {"id":"athletics","name":"Athletics","city":"New York, NY","location_type":"Remote","type":"Brand Studio","size":"under 20",
         "focus":"Brand studio known for consumer and cultural brand work. NYC-based.",
         "why_relevant":"Consumer and cultural brand focus is the right lane. Small studio model.",
         "website":"https://athletics.nyc","linkedin":"","instagram":"https://instagram.com/athletics.nyc",
         "platforms":["Direct outreach","Working Not Working"],"score":7},
        {"id":"gretel","name":"Gretel","city":"New York, NY","location_type":"Remote","type":"Brand Studio","size":"under 20",
         "focus":"Highly selective small brand studio, NYC. Known for Netflix, HBO, high-end cultural clients.",
         "why_relevant":"Selective but prestigious. Cultural and entertainment focus is right. Media and brand fluency matters here.",
         "website":"https://gretelny.com","linkedin":"","instagram":"https://instagram.com/gretel_ny",
         "platforms":["Direct outreach"],"score":6},
        {"id":"focus-lab","name":"Focus Lab","city":"Remote","location_type":"Remote","type":"Brand Studio","size":"under 50",
         "focus":"Remote-first brand and design studio. Growing into consumer brand territory. Strong freelance network.",
         "why_relevant":"Remote-first means accessibility. Growing into consumer brand territory is the window.",
         "website":"https://focuslabllc.com","linkedin":"https://www.linkedin.com/company/focus-lab/","instagram":"",
         "platforms":["Working Not Working","Direct outreach"],"score":6},
        {"id":"sibling-rivalry","name":"Sibling Rivalry","city":"New York, NY","location_type":"Remote","type":"Creative Studio","size":"under 20",
         "focus":"Small creative studio. Known for editorial and cultural brand work with a strong visual and conceptual POV.",
         "why_relevant":"Editorial and cultural work is exactly the overlap. Small enough for project relationships to be meaningful.",
         "website":"https://www.siblingrivalryny.com","linkedin":"","instagram":"https://instagram.com/siblingrivalry",
         "platforms":["Direct outreach","Working Not Working"],"score":7},
        {"id":"hecho","name":"Hecho","city":"New York, NY","location_type":"Remote","type":"Boutique Agency","size":"under 20",
         "focus":"Boutique agency focused on cultural brands and multicultural audiences.",
         "why_relevant":"Cultural brand focus is the exact intersection. Boutique means relationships matter.",
         "website":"https://www.wearehecho.com","linkedin":"","instagram":"",
         "platforms":["Direct outreach"],"score":7},
        {"id":"heroes-ghosts","name":"Heroes & Ghosts","city":"New York, NY","location_type":"Remote","type":"Creative Studio","size":"under 20",
         "focus":"Small creative studio. Brand and cultural work with a consumer focus.",
         "why_relevant":"Consumer brand and cultural work. Small studio model means project relationships are how they grow.",
         "website":"https://www.heroesghosts.com","linkedin":"","instagram":"",
         "platforms":["Direct outreach","Working Not Working"],"score":7},
        {"id":"and-rising","name":"And Rising","city":"Los Angeles, CA","location_type":"Remote","type":"Creative Studio","size":"under 20",
         "focus":"LA-based creative studio, remote-friendly. Creative capital model. Consumer and cultural brand focus.",
         "why_relevant":"Remote-friendly. The creative capital model means freelance relationships are built into how they operate.",
         "website":"https://andrising.com","linkedin":"","instagram":"https://instagram.com/andrising",
         "platforms":["Direct outreach","Working Not Working"],"score":8},
        {"id":"bullish","name":"Bullish","city":"New York, NY","location_type":"Remote","type":"Agency / Venture Hybrid","size":"under 50",
         "focus":"Hybrid creative agency and consumer brand venture. Works with emerging consumer brands at the intersection of strategy and investment.",
         "why_relevant":"Consumer brand focus at the strategy and commercial layer is exactly the overlap. Hybrid model means diverse briefs.",
         "website":"https://www.dobullish.com","linkedin":"https://www.linkedin.com/company/bullish-inc/","instagram":"",
         "platforms":["Direct outreach","Working Not Working"],"score":8},
        {"id":"teak","name":"Teak","city":"New York, NY","location_type":"Remote","type":"Brand Studio","size":"under 20",
         "focus":"Small brand studio. Consumer brand and strategy focus.",
         "why_relevant":"Small enough for a meaningful project relationship. Consumer brand and strategy focus.",
         "website":"https://teak.studio","linkedin":"","instagram":"",
         "platforms":["Direct outreach"],"score":6},
        {"id":"superhero-cheesecake","name":"Superhero Cheesecake","city":"New York, NY","location_type":"Remote","type":"Creative Studio","size":"under 20",
         "focus":"Boutique NYC creative studio. Brand and cultural work.",
         "why_relevant":"Cultural and brand work at boutique scale. Project-based model.",
         "website":"https://www.superheroesc.com","linkedin":"","instagram":"",
         "platforms":["Direct outreach","Working Not Working"],"score":6},
        {"id":"waterfall","name":"Waterfall","city":"New York, NY","location_type":"Remote","type":"Brand & Strategy Studio","size":"under 20",
         "focus":"Small brand and strategy studio. Consumer and cultural focus.",
         "why_relevant":"Brand and strategy studio is the exact overlap. Small means project relationships matter.",
         "website":"https://waterfall.is","linkedin":"","instagram":"",
         "platforms":["Direct outreach"],"score":7},
        # ── Cultural strategy boutiques ───────────────────────────
        {"id":"dazed-studio","name":"Dazed Studio","city":"London, UK","location_type":"Remote","type":"Cultural Strategy Studio","size":"under 50",
         "focus":"Creative and cultural strategy studio from Dazed Media. Maintains a freelance network of cultural strategists and creatives. Remote-friendly.",
         "why_relevant":"Explicitly maintains a freelance network. Cultural strategy is the exact brief. The connective tissue story maps directly.",
         "website":"https://dazedstudio.com","linkedin":"https://www.linkedin.com/company/dazed-media/","instagram":"https://instagram.com/dazedstudio",
         "platforms":["Direct outreach","The Dots","Working Not Working"],"score":9},
        {"id":"cassette","name":"Cassette","city":"Remote","location_type":"Remote","type":"Cultural Strategy","size":"under 20",
         "focus":"Cultural strategy consultancy. Works with brands on cultural insight, trend intelligence, and positioning.",
         "why_relevant":"Cultural strategy is the direct overlap. Boutique consultancy model means project relationships are the norm.",
         "website":"https://www.cassetteagency.com","linkedin":"","instagram":"",
         "platforms":["Direct outreach"],"score":8},
        {"id":"canvas8","name":"Canvas8","city":"London, UK","location_type":"Remote","type":"Cultural Intelligence","size":"20-50",
         "focus":"Cultural intelligence and consumer insight firm. Publishes research, works with global brands on audience and trend strategy. Maintains a contributor network.",
         "why_relevant":"Cultural and consumer intelligence is the direct overlap. Maintains a contributor and freelance network.",
         "website":"https://canvas8.com","linkedin":"https://www.linkedin.com/company/canvas8/","instagram":"",
         "platforms":["Direct outreach","Working Not Working"],"score":8},
        {"id":"sparks-honey","name":"Sparks & Honey","city":"New York, NY","location_type":"Remote","type":"Cultural Intelligence","size":"20-50",
         "focus":"Cultural intelligence and trend strategy consultancy. Works with large brands on cultural foresight and consumer insight.",
         "why_relevant":"Cultural intelligence is the exact through line. The connective tissue story maps directly to what they sell.",
         "website":"https://sparksandhoney.com","linkedin":"https://www.linkedin.com/company/sparks-honey/","instagram":"",
         "platforms":["Direct outreach","Working Not Working"],"score":8},
    ]

def scrape_product_hunt_prospects():
    """Scrape Product Hunt for recent brand launches across all target verticals."""
    print("  Scraping Product Hunt for prospects...")
    categories = [
        "gaming", "creator-tools", "podcasts", "music", "design-tools",
        "lifestyle", "health-fitness", "sports", "travel", "fashion",
        "consumer-goods", "social-media", "content-creation",
    ]
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

def scrape_thingtesting():
    """Scrape Thingtesting for recently launched DTC brands."""
    print("  Scraping Thingtesting for new brand launches...")
    try:
        resp = requests.get("https://thingtesting.com/brands?sort=newest", headers=HEADERS, timeout=12)
        soup = BeautifulSoup(resp.text, "html.parser")
        for item in soup.select("[class*='brand'], [class*='card'], article")[:20]:
            name_el = item.select_one("h2, h3, [class*='name'], [class*='title']")
            desc_el = item.select_one("p, [class*='desc'], [class*='tagline']")
            link_el = item.select_one("a[href]")
            if not name_el:
                continue
            brand = name_el.get_text(strip=True)
            desc = desc_el.get_text(strip=True) if desc_el else ""
            href = link_el.get("href", "") if link_el else ""
            site = f"https://thingtesting.com{href}" if href.startswith("/") else href
            if not brand or len(brand) < 3:
                continue
            sc = score_prospect(brand, desc, "DTC consumer")
            if sc < 4:
                continue
            add_prospect(
                brand=brand,
                gap=f"{desc} Newly launched DTC brand discovered on Thingtesting. Likely founder-operated with minimal commercial infrastructure.",
                website=site,
                industry="DTC / Consumer",
                score=sc,
                notes="Thingtesting discovery — new launch",
            )
    except Exception:
        pass

def scrape_bevnet():
    """Scrape BevNet news for emerging food/bev brand mentions."""
    print("  Scanning BevNet for emerging brands...")
    try:
        feed = feedparser.parse("https://www.bevnet.com/feed/")
        for entry in feed.entries[:15]:
            title = entry.get("title", "")
            content_raw = entry.get("content", [{}])
            content_html = content_raw[0].get("value", entry.get("summary", "")) if content_raw else entry.get("summary", "")
            content = BeautifulSoup(content_html, "html.parser").get_text()
            full_text = f"{title} {content}"
            brand_candidates = re.findall(r"\b([A-Z][a-zA-Z]{2,18}(?:\s[A-Z][a-zA-Z]{2,14})?)\b", full_text)
            checked = set()
            for brand in brand_candidates:
                if brand in checked or brand in seen_brands or len(brand) < 4:
                    continue
                if brand.lower() in {"the", "and", "for", "with", "this", "that", "they", "from",
                                      "have", "been", "their", "what", "when", "where", "which",
                                      "bevnet", "news", "brand", "drink", "food", "new"}:
                    continue
                checked.add(brand)
                idx = full_text.find(brand)
                ctx = full_text[max(0, idx - 80):idx + 200].lower()
                sc = score_prospect(brand, ctx, "food beverage DTC")
                if sc >= 5:
                    add_prospect(
                        brand=brand,
                        gap=f"Mentioned in BevNet coverage. Context: {ctx[:200].strip()}",
                        industry="Food & Beverage / DTC",
                        score=sc,
                        notes="BevNet discovery",
                    )
    except Exception:
        pass

def scrape_gaming_prospects():
    """Scrape gaming industry news for emerging indie studios and publishers."""
    print("  Scanning gaming industry for prospects...")
    feeds = [
        ("https://www.gamesindustry.biz/feed", "Gaming / Indie Publishing"),
        ("https://www.indiegames.com/feed", "Gaming / Indie"),
        ("https://hitmarker.net/feed", "Gaming / Esports"),
    ]
    for feed_url, industry in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:12]:
                content_raw = entry.get("content", [{}])
                content_html = content_raw[0].get("value", entry.get("summary", "")) if content_raw else entry.get("summary", "")
                content = BeautifulSoup(content_html, "html.parser").get_text()
                title = entry.get("title", "")
                full_text = f"{title} {content}"
                brand_candidates = re.findall(r"\b([A-Z][a-zA-Z]{2,20}(?:\s(?:Games?|Studios?|Interactive|Publishing|Entertainment|Media))?)\b", full_text)
                checked = set()
                for brand in brand_candidates:
                    if brand in checked or brand in seen_brands or len(brand) < 4:
                        continue
                    skip_words = {"The", "This", "That", "They", "When", "Where", "Which", "With",
                                  "From", "Have", "Been", "Their", "What", "Also", "More", "Game",
                                  "Games", "News", "New", "New", "Studios", "Here", "Read", "View"}
                    if brand in skip_words:
                        continue
                    checked.add(brand)
                    idx = full_text.find(brand)
                    ctx = full_text[max(0, idx - 80):idx + 200].lower()
                    sc = score_prospect(brand, ctx, industry)
                    if sc >= 4:
                        add_prospect(
                            brand=brand,
                            gap=f"Emerging studio or publisher discovered via gaming industry press. Context: {ctx[:180].strip()}",
                            industry=industry,
                            score=sc,
                            notes="Gaming industry discovery",
                        )
        except Exception:
            pass


def scrape_music_culture_prospects():
    """Scrape music and culture press for emerging independent labels and platforms."""
    print("  Scanning music/culture press for prospects...")
    feeds = [
        ("https://pitchfork.com/feed/feed-news/rss", "Music / Culture"),
        ("https://www.billboard.com/feed/", "Music / Culture"),
        ("https://www.thefader.com/rss", "Music / Culture / Editorial"),
    ]
    for feed_url, industry in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:8]:
                content_raw = entry.get("content", [{}])
                content_html = content_raw[0].get("value", entry.get("summary", "")) if content_raw else entry.get("summary", "")
                content = BeautifulSoup(content_html, "html.parser").get_text()
                title = entry.get("title", "")
                full_text = f"{title} {content}"
                # Look for label, platform, brand-like names
                brand_candidates = re.findall(r"\b([A-Z][a-zA-Z]{2,20}(?:\s(?:Records?|Music|Label|Collective|Sound|Media|Entertainment))?)\b", full_text)
                checked = set()
                for brand in brand_candidates:
                    if brand in checked or brand in seen_brands or len(brand) < 4:
                        continue
                    skip_words = {"The", "This", "That", "They", "When", "Where", "Which", "With",
                                  "From", "Have", "Been", "Their", "What", "Also", "More", "Music",
                                  "Records", "Label", "Artist", "Album", "Song", "Tour", "Read"}
                    if brand in skip_words:
                        continue
                    checked.add(brand)
                    idx = full_text.find(brand)
                    ctx = full_text[max(0, idx - 80):idx + 200].lower()
                    if not any(k in ctx for k in ["label", "platform", "brand", "partner", "launch", "indie", "independent", "distribute", "deal"]):
                        continue
                    sc = score_prospect(brand, ctx, industry)
                    if sc >= 5:
                        add_prospect(
                            brand=brand,
                            gap=f"Independent music entity with commercial potential. Context: {ctx[:180].strip()}",
                            industry=industry,
                            score=sc,
                            notes="Music/culture press discovery",
                        )
        except Exception:
            pass


def scrape_fashion_streetwear_prospects():
    """Scrape fashion/streetwear media for emerging brand mentions."""
    print("  Scanning fashion/streetwear media for prospects...")
    feeds = [
        ("https://hypebeast.com/feed", "Streetwear / Fashion / Culture"),
        ("https://highsnobiety.com/feed", "Fashion / Menswear / Culture"),
        ("https://sneakernews.com/feed", "Streetwear / Footwear / Culture"),
    ]
    for feed_url, industry in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:10]:
                content_raw = entry.get("content", [{}])
                content_html = content_raw[0].get("value", entry.get("summary", "")) if content_raw else entry.get("summary", "")
                content = BeautifulSoup(content_html, "html.parser").get_text()
                title = entry.get("title", "")
                full_text = f"{title} {content}"
                brand_candidates = re.findall(r"\b([A-Z][a-zA-Z]{2,20}(?:\s[A-Z][a-zA-Z]{2,14})?)\b", full_text)
                checked = set()
                for brand in brand_candidates:
                    if brand in checked or brand in seen_brands or len(brand) < 4:
                        continue
                    skip_words = {"The", "This", "That", "They", "When", "Where", "Which", "With",
                                  "From", "Have", "Been", "Their", "What", "Also", "More", "New",
                                  "Drop", "Release", "Style", "Look", "Week", "Read", "Shop"}
                    if brand in skip_words:
                        continue
                    checked.add(brand)
                    idx = full_text.find(brand)
                    ctx = full_text[max(0, idx - 80):idx + 200].lower()
                    if not any(k in ctx for k in ["brand", "label", "launch", "collab", "collection", "indie", "independent", "founder", "drop", "exclusive"]):
                        continue
                    sc = score_prospect(brand, ctx, industry)
                    if sc >= 5:
                        add_prospect(
                            brand=brand,
                            gap=f"Emerging fashion or streetwear brand with cultural traction. Context: {ctx[:180].strip()}",
                            industry=industry,
                            score=sc,
                            notes="Fashion/streetwear media discovery",
                        )
        except Exception:
            pass


def scrape_creator_economy_prospects():
    """Scrape creator economy and newsletter media for emerging platforms and brands."""
    print("  Scanning creator economy media for prospects...")
    feeds = [
        ("https://www.theinformation.com/feed", "Creator Economy / Media"),
        ("https://www.axios.com/feeds/feed.rss", "Creator Economy / Media"),
        ("https://trends.vc/feed", "Creator Economy / Startup"),
    ]
    for feed_url, industry in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:8]:
                content_raw = entry.get("content", [{}])
                content_html = content_raw[0].get("value", entry.get("summary", "")) if content_raw else entry.get("summary", "")
                content = BeautifulSoup(content_html, "html.parser").get_text()
                title = entry.get("title", "")
                full_text = f"{title} {content}"
                brand_candidates = re.findall(r"\b([A-Z][a-zA-Z]{2,20}(?:\s[A-Z][a-zA-Z]{2,14})?)\b", full_text)
                checked = set()
                for brand in brand_candidates:
                    if brand in checked or brand in seen_brands or len(brand) < 4:
                        continue
                    skip_words = {"The", "This", "That", "They", "When", "Where", "Which", "With",
                                  "From", "Have", "Been", "Their", "What", "Also", "More", "New",
                                  "Read", "Here", "View", "Said", "Says", "Will", "Would"}
                    if brand in skip_words:
                        continue
                    checked.add(brand)
                    idx = full_text.find(brand)
                    ctx = full_text[max(0, idx - 80):idx + 200].lower()
                    if not any(k in ctx for k in ["creator", "newsletter", "platform", "brand", "startup", "launch", "funding", "raise", "series", "partner"]):
                        continue
                    sc = score_prospect(brand, ctx, industry)
                    if sc >= 5:
                        add_prospect(
                            brand=brand,
                            gap=f"Creator economy platform or brand with commercial potential. Context: {ctx[:180].strip()}",
                            industry=industry,
                            score=sc,
                            notes="Creator economy media discovery",
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
scrape_remotive()
scrape_weworkremotely()
scrape_remoteok()
scrape_substacks()
scrape_linkedin_contract()
scrape_fractionaljobs_io()
scrape_wellfound_contract()
scrape_contra()
scrape_working_not_working()
scrape_himalayas()

jobs.sort(key=lambda x: x["score"], reverse=True)
top_jobs = jobs  # no cap — show everything that passes the score filter

# Contact enrichment for top jobs (Apollo first, Hunter fallback)
print("\n--- CONTACT ENRICHMENT (JOBS) ---")
for job in top_jobs[:30]:
    if job.get("contacts"):
        continue
    contacts = apollo_get_contacts(job["company"]) if APOLLO_API_KEY else []
    if not contacts:
        contacts = hunter_get_contacts(job["company"]) if HUNTER_API_KEY else []
    if contacts:
        job["contacts"] = contacts
        print(f"  {job['company']}: {len(contacts)} contacts via {'Apollo' if contacts[0].get('source') == 'Apollo' else 'Hunter'}")

print("\n--- PROSPECT SCRAPERS ---")
seed_known_prospects()
scrape_product_hunt_prospects()
scrape_thingtesting()
scrape_bevnet()
scrape_words_of_mouth()
scrape_gaming_prospects()
scrape_music_culture_prospects()
scrape_fashion_streetwear_prospects()
scrape_creator_economy_prospects()

# Agencies are a static curated list — no scraping needed
known_agencies = seed_known_agencies()

prospects.sort(key=lambda x: x["score"], reverse=True)

# ── Industry cap — prevent any one category from flooding the list ────────────
# Food & Bev / DTC dynamic scrapers can pull 100+ similar brands.
# Cap each broad category so the dashboard stays diverse.
INDUSTRY_CAPS = {
    "food": 15,
    "beverage": 15,
    "dtc": 10,
    "cpg": 8,
    "gaming": 20,
    "streetwear": 15,
    "fashion": 15,
    "creator economy": 15,
    "music": 12,
}
industry_counts: dict = {}
capped_prospects = []
for p in prospects:
    ind = p.get("industry", "").lower()
    # Find which cap bucket this prospect belongs to
    bucket = next((k for k in INDUSTRY_CAPS if k in ind), None)
    if bucket:
        industry_counts[bucket] = industry_counts.get(bucket, 0) + 1
        if industry_counts[bucket] > INDUSTRY_CAPS[bucket]:
            continue  # skip — over the cap for this category
    capped_prospects.append(p)
prospects = capped_prospects

# Contact enrichment for prospects (Apollo first, Hunter fallback)
print("\n--- CONTACT ENRICHMENT (PROSPECTS) ---")
for p in prospects[:30]:
    if p.get("contacts"):
        continue
    domain = None
    if p.get("website"):
        domain = p["website"].replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
    contacts = apollo_get_contacts(p["brand"], domain=domain) if APOLLO_API_KEY else []
    if not contacts:
        contacts = hunter_get_contacts(p["brand"], domain=domain) if HUNTER_API_KEY else []
    if contacts:
        p["contacts"] = contacts
        print(f"  {p['brand']}: {len(contacts)} contacts via {'Apollo' if contacts[0].get('source') == 'Apollo' else 'Hunter'}")

print(f"\nDone.")
print(f"  Jobs found:      {len(jobs)}, keeping top {len(top_jobs)}")
print(f"  Prospects found: {len(prospects)}\n")

# ─────────────────────────────────────────────
# WRITE JSON FILES FOR DASHBOARD
# ─────────────────────────────────────────────

jobs_path = os.path.join(OUTPUT_DIR, "jobs.json")
# Safety net: never overwrite with an empty list — keep existing data as fallback
if top_jobs:
    with open(jobs_path, "w") as f:
        json.dump(top_jobs, f, indent=2)
    print(f"Wrote {len(top_jobs)} jobs  ->  {jobs_path}")
else:
    print(f"WARNING: 0 jobs found this run — keeping existing jobs.json to avoid wiping data")

prospects_path = os.path.join(OUTPUT_DIR, "prospects.json")
with open(prospects_path, "w") as f:
    json.dump(prospects, f, indent=2)
print(f"Wrote {len(prospects)} prospects  ->  {prospects_path}")

agencies_path = os.path.join(OUTPUT_DIR, "agencies.json")
with open(agencies_path, "w") as f:
    json.dump(known_agencies, f, indent=2)
print(f"Wrote {len(known_agencies)} agencies  ->  {agencies_path}")

meta_path = os.path.join(OUTPUT_DIR, "meta.json")
with open(meta_path, "w") as f:
    json.dump({
        "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "jobs": len(top_jobs),
        "prospects": len(prospects),
        "agencies": len(known_agencies),
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
