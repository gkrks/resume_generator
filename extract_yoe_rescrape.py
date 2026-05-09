"""Re-scrape job listings with empty JD text and extract YOE."""

import os
import re
import json
import time
import httpx
from dotenv import load_dotenv

load_dotenv(".env")

from supabase_client import _rest_url, _HEADERS
from scraper import scrape_jd

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]


def call_claude(texts):
    listings_block = ""
    for item in texts:
        clean = re.sub(r"<[^>]+>", " ", item["text"][:3000])
        clean = re.sub(r"\s+", " ", clean).strip()
        listings_block += f'\n<listing id="{item["id"]}">\nTitle: {item["title"]}\n{clean}\n</listing>\n'

    prompt = f"""Extract the minimum and maximum years of experience required from each job listing below.

Rules:
- If it says "2+ years", yoe_min=2, yoe_max=null
- If it says "3-5 years", yoe_min=3, yoe_max=5
- If it says "at least 4 years", yoe_min=4, yoe_max=null
- If no years of experience are mentioned at all, yoe_min=null, yoe_max=null
- Look for patterns like "X years of experience", "X+ years", "X-Y years", etc.
- Focus on the REQUIRED qualifications, not preferred/nice-to-have
- yoe_raw should be the exact text snippet mentioning years
- If there are multiple year requirements, use the one most relevant to the overall role

Return ONLY a JSON array:
[{{"id": "...", "yoe_min": ..., "yoe_max": ..., "yoe_raw": "..."}}]

{listings_block}"""

    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    r.raise_for_status()
    content = r.json()["content"][0]["text"]
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if match:
        return json.loads(match.group())
    return []


def main():
    # Fetch rows with yoe_min=null and empty raw_jd_excerpt
    resp = httpx.get(
        _rest_url("job_listings"),
        headers=_HEADERS,
        params={
            "select": "id,title,role_url",
            "yoe_min": "is.null",
            "raw_jd_excerpt": "eq.",
            "limit": "100",
        },
    )
    resp.raise_for_status()
    rows = resp.json()
    print(f"Re-scraping {len(rows)} listings with empty JD text...")

    scraped = []
    for i, r in enumerate(rows):
        url = r.get("role_url", "")
        print(f"  [{i+1}/{len(rows)}] {r['title'][:50]}...")
        if not url:
            print("    No URL, skipping")
            continue
        try:
            text = scrape_jd(url)
            if text and len(text) > 50:
                scraped.append({"id": r["id"], "title": r["title"], "text": text})
                print(f"    Got {len(text)} chars")
            else:
                print(f"    Too short or empty ({len(text) if text else 0} chars)")
        except Exception as e:
            print(f"    Error: {e}")

    print(f"\nSuccessfully scraped: {len(scraped)}/{len(rows)}")

    if not scraped:
        print("Nothing to process.")
        return

    # Send to LLM in batches
    batch_size = 15
    all_results = []
    for i in range(0, len(scraped), batch_size):
        batch = scraped[i : i + batch_size]
        print(f"LLM batch {i // batch_size + 1}...")
        try:
            results = call_claude(batch)
            all_results.extend(results)
            print(f"  Got {len(results)} results")
        except Exception as e:
            print(f"  Error: {e}")
        time.sleep(0.5)

    # Update Supabase
    updated = 0
    for result in all_results:
        rid = result.get("id")
        ymin = result.get("yoe_min")
        ymax = result.get("yoe_max")
        yraw = result.get("yoe_raw", "")

        if ymin is None and ymax is None:
            continue

        patch = {}
        if ymin is not None:
            patch["yoe_min"] = ymin
        if ymax is not None:
            patch["yoe_max"] = ymax
        if yraw:
            patch["yoe_raw"] = yraw

        if patch:
            resp = httpx.patch(
                _rest_url("job_listings"),
                headers=_HEADERS,
                params={"id": f"eq.{rid}"},
                json=patch,
            )
            resp.raise_for_status()
            updated += 1
            print(f"  Updated {rid[:8]}: min={ymin} max={ymax} raw={yraw[:60]}")

    print(f"\nNewly updated from re-scrape: {updated}")

    # Final stats
    resp = httpx.get(
        _rest_url("job_listings"),
        headers={**_HEADERS, "Prefer": "count=exact"},
        params={"select": "id", "yoe_min": "is.null", "limit": "1"},
    )
    print(f"Rows still missing yoe_min: {resp.headers.get('content-range')}")

    resp2 = httpx.get(
        _rest_url("job_listings"),
        headers={**_HEADERS, "Prefer": "count=exact"},
        params={"select": "id", "yoe_min": "not.is.null", "limit": "1"},
    )
    print(f"Rows with yoe_min filled: {resp2.headers.get('content-range')}")


if __name__ == "__main__":
    main()
