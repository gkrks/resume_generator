"""Extract years of experience from job listings using Claude API."""

import os
import re
import json
import time
import httpx
from dotenv import load_dotenv

load_dotenv()

from supabase_client import _rest_url, _HEADERS

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]


def call_claude(texts: list[dict]) -> list[dict]:
    """Send a batch of job listing texts to Claude for YOE extraction.

    Each item in texts: {"id": ..., "text": ...}
    Returns: [{"id": ..., "yoe_min": int|null, "yoe_max": int|null, "yoe_raw": str}, ...]
    """
    listings_block = ""
    for item in texts:
        listings_block += f'\n<listing id="{item["id"]}">\n{item["text"][:3000]}\n</listing>\n'

    prompt = f"""Extract the minimum and maximum years of experience required from each job listing below.

Rules:
- If it says "2+ years", yoe_min=2, yoe_max=null
- If it says "3-5 years", yoe_min=3, yoe_max=5
- If it says "at least 4 years", yoe_min=4, yoe_max=null
- If it says "up to 3 years", yoe_min=0, yoe_max=3
- If no years of experience are mentioned at all, yoe_min=null, yoe_max=null
- Look for patterns like "X years of experience", "X+ years", "X-Y years", etc.
- Focus on the REQUIRED qualifications, not preferred/nice-to-have
- yoe_raw should be the exact text snippet mentioning years (e.g. "5+ years of experience in software engineering")
- If there are multiple year requirements, use the one most relevant to the overall role

Return ONLY a JSON array, no other text:
[{{"id": "...", "yoe_min": ..., "yoe_max": ..., "yoe_raw": "..."}}]

{listings_block}"""

    resp = httpx.post(
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
    resp.raise_for_status()
    content = resp.json()["content"][0]["text"]

    # Parse JSON from response
    match = re.search(r'\[.*\]', content, re.DOTALL)
    if match:
        return json.loads(match.group())
    return []


def build_text(row: dict) -> str:
    """Build a text blob from available fields for YOE extraction."""
    parts = []
    if row.get("title"):
        parts.append(f"Title: {row['title']}")

    quals = row.get("jd_required_qualifications")
    if quals:
        if isinstance(quals, list):
            parts.append("Required Qualifications:\n" + "\n".join(f"- {q}" for q in quals))
        else:
            parts.append(f"Required Qualifications: {quals}")

    pref = row.get("jd_preferred_qualifications")
    if pref:
        if isinstance(pref, list):
            parts.append("Preferred Qualifications:\n" + "\n".join(f"- {q}" for q in pref))
        else:
            parts.append(f"Preferred Qualifications: {pref}")

    excerpt = row.get("raw_jd_excerpt") or ""
    if excerpt:
        # Strip HTML tags for cleaner text
        clean = re.sub(r'<[^>]+>', ' ', excerpt)
        clean = re.sub(r'\s+', ' ', clean).strip()
        parts.append(f"Job Description:\n{clean[:2500]}")

    return "\n\n".join(parts) if parts else ""


def main():
    # Fetch all rows with yoe_min NULL
    all_rows = []
    offset = 0
    while True:
        resp = httpx.get(
            _rest_url("job_listings"),
            headers=_HEADERS,
            params={
                "select": "id,title,raw_jd_excerpt,jd_required_qualifications,jd_preferred_qualifications,qualifications",
                "yoe_min": "is.null",
                "limit": "1000",
                "offset": str(offset),
            },
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    print(f"Total rows to process: {len(all_rows)}")

    # Split into rows with text and without
    with_text = []
    without_text = []
    for r in all_rows:
        text = build_text(r)
        if len(text) > 20:
            with_text.append({"id": r["id"], "text": text})
        else:
            without_text.append(r["id"])

    print(f"Rows with text to analyze: {len(with_text)}")
    print(f"Rows with no text (will skip): {len(without_text)}")

    # Process in batches of 15
    batch_size = 15
    all_results = []
    for i in range(0, len(with_text), batch_size):
        batch = with_text[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(with_text) + batch_size - 1) // batch_size
        print(f"Processing batch {batch_num}/{total_batches} ({len(batch)} listings)...")

        try:
            results = call_claude(batch)
            all_results.extend(results)
            print(f"  Got {len(results)} results")
        except Exception as e:
            print(f"  ERROR: {e}")
            # Retry once after a pause
            time.sleep(5)
            try:
                results = call_claude(batch)
                all_results.extend(results)
                print(f"  Retry got {len(results)} results")
            except Exception as e2:
                print(f"  Retry also failed: {e2}")

        # Rate limit
        time.sleep(0.5)

    print(f"\nTotal results from LLM: {len(all_results)}")

    # Update Supabase
    updated = 0
    skipped = 0
    for result in all_results:
        rid = result.get("id")
        ymin = result.get("yoe_min")
        ymax = result.get("yoe_max")
        yraw = result.get("yoe_raw", "")

        if ymin is None and ymax is None:
            skipped += 1
            continue

        patch = {}
        if ymin is not None:
            patch["yoe_min"] = ymin
        if ymax is not None:
            patch["yoe_max"] = ymax
        if yraw:
            patch["yoe_raw"] = yraw

        if not patch:
            skipped += 1
            continue

        try:
            resp = httpx.patch(
                _rest_url("job_listings"),
                headers=_HEADERS,
                params={"id": f"eq.{rid}"},
                json=patch,
            )
            resp.raise_for_status()
            updated += 1
        except Exception as e:
            print(f"  Failed to update {rid}: {e}")

    print(f"\nUpdated: {updated}")
    print(f"Skipped (no YOE found): {skipped}")
    print(f"No text available: {len(without_text)}")

    # Final count
    resp = httpx.get(
        _rest_url("job_listings"),
        headers={**_HEADERS, "Prefer": "count=exact"},
        params={"select": "id", "yoe_min": "is.null", "limit": "1"},
    )
    remaining = resp.headers.get("content-range", "")
    print(f"Rows still missing yoe_min: {remaining}")


if __name__ == "__main__":
    main()
