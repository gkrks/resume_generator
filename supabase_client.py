"""Lightweight Supabase REST client using httpx — no extra SDK needed."""

import os
from datetime import datetime, timezone
import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def _rest_url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


# ── Location filter ─────────────────────────────────────────────

_NON_US_KEYWORDS = [
    # Europe
    "italy", "spain", "portugal", "slovenia", "czech", "czechia", "switzerland",
    "zurich", "romania", "hungary", "budapest", "belgium", "brussels",
    "austria", "vienna, austria",
    "germany", "oberkochen", "aalen", "bochum", "munich", "berlin", "frankfurt",
    "france", "paris", "la ciotat", "rungis", "limours",
    "finland", "helsinki", "sweden", "malmö", "malmo", "stockholm",
    "denmark", "aarhus", "copenhagen",
    "poland", "krakow", "warsaw", "slovakia", "serbia", "cyprus", "armenia",
    "greece", "athens", "ghent", "cardiff", "belfast", "geneva",
    "barcelona", "madrid", "rome", "milan", "lainate", "ascoli piceno",
    "prague", "lisbon", "porto,", "cluj", "bucharest",
    "valencia (es)", "(it)", "remoto", ", hu",
    "united kingdom", "england", "london, uk", "edinburgh", "dublin",
    "norway", "oslo", "netherlands", "amsterdam", "luxembourg",
    # Asia
    "indonesia", "thailand", "bangkok", "vietnam", "ho chi minh",
    "philippines", "taguig", "metro manila", "makati",
    "malaysia", "kuala lumpur",
    "pakistan", "islamabad", "karachi",
    "kazakhstan", "uzbekistan", "tashkent",
    "qatar", "doha", "dubai", "uae", "abu dhabi",
    "tel-aviv", "tel aviv", "israel",
    "india", "bengaluru", "bangalore", "hyderabad", "mumbai", "delhi", "pune",
    "singapore", "japan", "tokyo", "china", "shanghai", "beijing", "shenzhen",
    "minhang", ", cn", "taiwan", "korea", "seoul",
    # Mexico / Central America
    "mexico", "zapopan", ", mx", "guadalajara", "monterrey",
    # South America
    "argentina", "buenos aires", "colombia", "medellín", "medellin", "bogota",
    "chile", "santiago", "peru", "lima (andres reyes",
    "brazil", "são paulo", "sao paulo", "londrina",
    # Oceania
    "auckland", "new zealand", "australia", "sydney", "melbourne",
    # Africa
    "cape town", "south africa", "nigeria", "kenya", "nairobi",
    # Middle East / Other
    "estonia", "turkey", "istanbul",
    # Remote-{country} patterns
    "remote - estonia", "remote spain", "remote - spain", "spain (remote)",
    "remote - americas", "malaysia - remote", "turkey - remote",
    "portugal - remote", "serbia - remote", "cyprus - remote",
    "armenia - remote", "argentina - remote", "spain - remote",
    "ch-zurich", "philippines remote",
]

_NON_US_EXACT = {
    "Italy", "Spain", "Indonesia", "Kazakhstan", "Turkey", "Portugal",
    "Philippines", "Malaysia", "Czechia", "Slovakia", "Colombia",
    "Remoto", "Londrina", "Milan", "Bangkok", "Barcelona", "Zurich",
    "Malmö", "Krakow", "Auckland", "Dubai", "Geneva", "Belfast",
    "Buenos Aires", "Cape Town", "Tel-Aviv", "Singapore", "Ireland",
}

_US_OVERRIDES = {"vienna, va", "georgia - remote", "georgia"}


def is_us_location(location_raw: str | None) -> bool:
    """Return True if location_raw looks like a US location (or is empty/unknown).

    Empty/null locations are treated as US (benefit of the doubt) so they
    aren't silently dropped — the queue processor logs a warning instead.
    """
    if not location_raw:
        return True

    loc = location_raw.strip()
    loc_lower = loc.lower().strip()

    # Explicit US overrides (e.g. Vienna, VA)
    for override in _US_OVERRIDES:
        if override in loc_lower:
            return True

    # Exact non-US match
    if loc in _NON_US_EXACT:
        return False

    # Keyword non-US match
    for kw in _NON_US_KEYWORDS:
        if kw in loc_lower:
            return False

    return True


# ── Reads ────────────────────────────────────────────────────────

def fetch_pending_queue_items(limit: int = 10) -> list[dict]:
    """Get resume_queue rows where was_resume_created = false,
    ordered by requested_at DESC. Filters out non-US locations."""
    resp = httpx.get(
        _rest_url("resume_queue"),
        headers=_HEADERS,
        params={
            "select": "*",
            "was_resume_created": "eq.false",
            "order": "requested_at.desc",
            "limit": str(limit),
        },
    )
    resp.raise_for_status()
    items = resp.json()

    us_items = []
    for item in items:
        loc = item.get("location_raw", "")
        if is_us_location(loc):
            us_items.append(item)
        else:
            print(f"  SKIPPED non-US listing: {item.get('title', '')} "
                  f"@ {item.get('company_name', '')} [{loc}]")
    return us_items


def fetch_job_listing(listing_id: str) -> dict | None:
    """Get a single job_listings row by id."""
    resp = httpx.get(
        _rest_url("job_listings"),
        headers=_HEADERS,
        params={
            "select": "*",
            "id": f"eq.{listing_id}",
            "limit": "1",
        },
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


# ── Writes ───────────────────────────────────────────────────────

def mark_resume_completed(
    queue_id: str,
    ats_check: bool,
    recruiter_check: bool,
    hr_check: bool,
) -> dict:
    """Mark a queue item as done and write back all evaluation results.

    Computes strong_apply and tier from the three check booleans:
      - All 3 pass → Strong
      - 2 pass     → Maybe
      - 0-1 pass   → DontWasteTime
    """
    passes = sum([ats_check, recruiter_check, hr_check])
    strong_apply = passes == 3
    if passes == 3:
        tier = "Strong"
    elif passes == 2:
        tier = "Maybe"
    else:
        tier = "DontWasteTime"

    resp = httpx.patch(
        _rest_url("resume_queue"),
        headers=_HEADERS,
        params={"id": f"eq.{queue_id}"},
        json={
            "was_resume_created": True,
            "ats_check": ats_check,
            "recruiter_check": recruiter_check,
            "hr_check": hr_check,
            "strong_apply": strong_apply,
            "tier": tier,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    resp.raise_for_status()
    return resp.json()
