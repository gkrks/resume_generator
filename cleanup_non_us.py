"""Delete all non-US job listings from Supabase. Uses location_raw as ground truth."""

import os
from dotenv import load_dotenv
load_dotenv(".env")

from supabase_client import _rest_url, _HEADERS
import httpx

# Comprehensive list of non-US signals in location_raw
NON_US_KEYWORDS = [
    # Europe
    "italy", "spain", "portugal", "slovenia", "czech", "czechia", "switzerland",
    "zurich", "romania", "hungary", "budapest", "belgium", "brussels", "austria",
    "vienna, austria",  # but not Vienna, VA
    "germany", "oberkochen", "aalen", "bochum", "france", "la ciotat", "rungis",
    "limours", "finland", "helsinki", "sweden", "malmö", "malmo", "denmark",
    "aarhus", "poland", "krakow", "slovakia", "serbia", "cyprus", "armenia",
    "greece", "ghent", "cardiff", "belfast", "geneva", "barcelona", "madrid",
    "rome", "milan", "lainate", "ascoli piceno", "prague", "lisbon", "porto,",
    "cluj", "bucharest", ", hu", "valencia (es)", "(it)", "remoto",
    # UK/Ireland
    "united kingdom", "england", "london, uk", "edinburgh", "dublin",
    # Asia
    "indonesia", "thailand", "bangkok", "vietnam", "ho chi minh", "philippines",
    "taguig", "metro manila", "makati", "malaysia", "pakistan", "islamabad",
    "karachi", "kazakhstan", "uzbekistan", "tashkent", "qatar", "doha", "dubai",
    "tel-aviv", "tel aviv", "israel", "india", "bengaluru", "bangalore", "hyderabad",
    "mumbai", "delhi", "singapore", "japan", "tokyo", "china", "shanghai",
    "beijing", "shenzhen", "minhang", ", cn", "taiwan", "korea", "seoul",
    # Mexico / Central America
    "mexico", "zapopan", ", mx", "guadalajara",
    # South America
    "argentina", "buenos aires", "colombia", "medellín", "medellin", "chile",
    "santiago", "peru", "lima (andres reyes", "brazil", "são paulo", "sao paulo",
    "londrina",
    # Oceania
    "auckland", "new zealand", "australia", "sydney", "melbourne",
    # Africa
    "cape town", "south africa", "nigeria", "kenya", "nairobi",
    # Middle East
    "estonia", "turkey", "istanbul",
    # Other non-US
    "remote - estonia", "remote spain", "remote - spain", "spain (remote)",
    "remote - americas",  # ambiguous but not US-specific
    "malaysia - remote", "turkey - remote", "portugal - remote", "serbia - remote",
    "cyprus - remote", "armenia - remote", "argentina - remote", "spain - remote",
    "ch-zurich", "philippines remote",
]

# Exact matches for short/ambiguous values
NON_US_EXACT = {
    "Italy", "Spain", "Indonesia", "Kazakhstan", "Turkey", "Portugal",
    "Philippines", "Malaysia", "Czechia", "Slovakia", "Colombia",
    "Remoto", "Londrina", "Milan", "Bangkok", "Barcelona", "Zurich",
    "Malmö", "Krakow", "Auckland", "Dubai", "Geneva", "Belfast",
    "Buenos Aires", "Cape Town", "Tel-Aviv", "Bellevue",  # wait no, Bellevue is WA
}
# Bellevue is WA - remove
NON_US_EXACT.discard("Bellevue")

# Known US false positives to KEEP
US_OVERRIDES = {
    "vienna, va",
    "georgia - remote",  # US state
    "georgia",  # US state (ambiguous but in context of US job board, likely US)
}


def is_non_us(location_raw: str) -> bool:
    if not location_raw:
        return False
    loc = location_raw.strip()
    loc_lower = loc.lower().strip()

    # Check US overrides first
    for override in US_OVERRIDES:
        if override in loc_lower:
            return False

    # Exact match
    if loc in NON_US_EXACT:
        return True

    # Keyword match
    for kw in NON_US_KEYWORDS:
        if kw in loc_lower:
            return True

    return False


def main():
    # Fetch all rows
    all_rows = []
    offset = 0
    while True:
        resp = httpx.get(
            _rest_url("job_listings"),
            headers=_HEADERS,
            params={"select": "id,title,location_raw", "limit": "1000", "offset": str(offset)},
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    print(f"Total rows: {len(all_rows)}")

    to_delete = []
    for r in all_rows:
        loc = r.get("location_raw") or ""
        if is_non_us(loc):
            to_delete.append(r)

    print(f"Non-US rows to delete: {len(to_delete)}")
    for r in to_delete:
        print(f"  DELETE: {r.get('location_raw', 'N/A'):50} | {r.get('title', '')[:50]}")

    # Delete
    deleted = 0
    for r in to_delete:
        resp = httpx.delete(
            _rest_url("job_listings"),
            headers=_HEADERS,
            params={"id": f"eq.{r['id']}"},
        )
        resp.raise_for_status()
        deleted += 1

    print(f"\nDeleted: {deleted}")

    # Verify
    resp = httpx.get(
        _rest_url("job_listings"),
        headers={**_HEADERS, "Prefer": "count=exact"},
        params={"select": "id", "limit": "1"},
    )
    print(f"Remaining rows: {resp.headers.get('content-range')}")


if __name__ == "__main__":
    main()
