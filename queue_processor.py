"""Queue Processor — pulls pending jobs from Supabase and runs the pipeline.

Reads resume_queue (was_resume_created = false), joins with job_listings
to get the full JD, assembles a rich JD text block, runs the orchestrator,
and marks the row done.
"""

import json
import os
import traceback
from pathlib import Path

from supabase_client import (
    fetch_pending_queue_items,
    fetch_job_listing,
    mark_resume_completed,
)
from orchestrator import run as run_pipeline
from scraper import scrape_jd

# Google Drive upload is optional — skipped if credentials aren't set
_DRIVE_ENABLED = bool(
    os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    or os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
)


def _upload_to_drive(output_dir: str):
    """Upload output to Google Drive if credentials are configured."""
    if not _DRIVE_ENABLED:
        return
    try:
        from drive_uploader import upload_output_dir
        print(f"\n  Uploading to Google Drive...")
        links = upload_output_dir(output_dir)
        print(f"  Uploaded {len(links)} file(s) to Drive")
    except Exception as e:
        print(f"  WARNING: Drive upload failed: {e}")


def _build_jd_text(listing: dict, queue_item: dict) -> str:
    """Assemble a rich JD text block from the structured job_listings data
    so the agents get maximum context."""

    parts = []

    # Header
    company = listing.get("jd_company_name") or queue_item.get("company_name", "")
    title = listing.get("jd_job_title") or queue_item.get("title", "")
    location = queue_item.get("location_raw") or listing.get("location_raw", "")
    parts.append(f"Company: {company}")
    parts.append(f"Role: {title}")
    parts.append(f"Location: {location}")
    parts.append(f"URL: {queue_item.get('role_url', '')}")

    # YOE
    exp = listing.get("jd_experience") or {}
    yoe_min = queue_item.get("yoe_min") or exp.get("years_min")
    yoe_max = queue_item.get("yoe_max") or exp.get("years_max")
    if yoe_min or yoe_max:
        parts.append(f"Years of experience: {yoe_min or '?'}-{yoe_max or '?'}")

    # Employment info
    emp = listing.get("jd_employment") or {}
    if emp:
        parts.append(f"Employment type: {emp.get('type', 'unknown')}")
        parts.append(f"Seniority: {emp.get('seniority_level', 'unknown')}")

    # Education
    edu = listing.get("jd_education") or {}
    if edu:
        parts.append(f"Education: {edu.get('minimum_degree', '')} in {', '.join(edu.get('fields_of_study', []))}")

    parts.append("")

    # Raw JD excerpt (the full description text)
    # If missing, scrape from URL as fallback
    raw_jd = listing.get("raw_jd_excerpt") or ""
    if not raw_jd.strip():
        role_url = queue_item.get("role_url", "")
        if role_url:
            print(f"  raw_jd_excerpt is empty — scraping from {role_url}")
            raw_jd = scrape_jd(role_url)

    if raw_jd:
        parts.append("--- FULL JOB DESCRIPTION ---")
        parts.append(raw_jd)
        parts.append("")

    # Structured qualifications (pre-parsed by the scraper)
    req_quals = listing.get("jd_required_qualifications") or []
    if req_quals:
        parts.append("--- REQUIRED QUALIFICATIONS ---")
        for i, q in enumerate(req_quals, 1):
            parts.append(f"{i}. {q}")
        parts.append("")

    pref_quals = listing.get("jd_preferred_qualifications") or []
    if pref_quals:
        parts.append("--- PREFERRED QUALIFICATIONS ---")
        for i, q in enumerate(pref_quals, 1):
            parts.append(f"{i}. {q}")
        parts.append("")

    responsibilities = listing.get("jd_responsibilities") or []
    if responsibilities:
        parts.append("--- RESPONSIBILITIES ---")
        for i, r in enumerate(responsibilities, 1):
            parts.append(f"{i}. {r}")
        parts.append("")

    # Skills (pre-parsed)
    skills = listing.get("jd_skills") or {}
    if skills:
        parts.append("--- SKILLS FROM JD ---")
        for category, items in skills.items():
            if items:
                parts.append(f"  {category}: {', '.join(items) if isinstance(items, list) else items}")
        parts.append("")

    # APM signal
    apm = queue_item.get("apm_signal") or listing.get("apm_signal", "")
    if apm and apm != "none":
        parts.append(f"APM Signal: {apm}")

    # Domain tags
    tags = listing.get("domain_tags", [])
    if tags:
        parts.append(f"Domain tags: {', '.join(tags)}")

    return "\n".join(parts)


def process_one(queue_item: dict) -> dict:
    """Process a single queue item end-to-end.

    Returns the orchestrator result dict on success, raises on failure.
    """
    queue_id = queue_item["id"]
    listing_id = queue_item["listing_id"]
    company = queue_item.get("company_name", "Unknown")
    title = queue_item.get("title", "")
    role_category = queue_item.get("role_category", "PM")

    print(f"\n{'#'*60}")
    print(f"  Processing: {title} @ {company}")
    print(f"  Queue ID: {queue_id}")
    print(f"  Listing ID: {listing_id}")
    print(f"  Role category: {role_category}")
    print(f"{'#'*60}")

    # Fetch the full job listing
    listing = fetch_job_listing(listing_id)
    if not listing:
        raise ValueError(f"job_listings row not found for listing_id={listing_id}")

    # Build the JD text
    jd_text = _build_jd_text(listing, queue_item)
    print(f"  JD assembled: {len(jd_text)} chars")

    # Build job_meta for the evaluation report PDF
    emp = listing.get("jd_employment", {}) or {}
    exp = listing.get("jd_experience", {}) or {}
    job_meta = {
        "role_url": queue_item.get("role_url", ""),
        "posted_date": queue_item.get("posted_date") or listing.get("posted_date", ""),
        "location": queue_item.get("location_raw") or listing.get("location_raw", ""),
        "yoe_min": queue_item.get("yoe_min") or exp.get("years_min"),
        "yoe_max": queue_item.get("yoe_max") or exp.get("years_max"),
        "ats_platform": queue_item.get("ats_platform", ""),
        "apm_signal": queue_item.get("apm_signal", ""),
        "listing_id": listing_id,
        "queue_id": queue_id,
        "seniority": emp.get("seniority_level", ""),
        "employment_type": emp.get("type", ""),
    }

    # Run the pipeline
    result = run_pipeline(
        jd_text=jd_text,
        role_type=role_category,
        job_meta=job_meta,
    )

    # Write back check results and mark as done
    checks = result.get("checks", {})
    mark_resume_completed(
        queue_id=queue_id,
        ats_check=checks.get("ats_check", False),
        recruiter_check=checks.get("recruiter_check", False),
        hr_check=checks.get("hr_check", False),
    )
    tier = result.get("tier", "?")
    print(f"\n  Marked queue item {queue_id} as done. Tier: {tier}")

    # Upload to Google Drive
    _upload_to_drive(result.get("output_dir", ""))

    return result


def _process_one_safe(item: dict) -> dict:
    """Wrapper that catches exceptions for parallel execution."""
    company = item.get("company_name", "Unknown")
    title = item.get("title", "")
    try:
        result = process_one(item)
        return {"queue_id": item["id"], "status": "success", "result": result}
    except Exception as e:
        print(f"\n  ERROR processing {title} @ {company}: {e}")
        traceback.print_exc()
        return {"queue_id": item["id"], "status": "error", "error": str(e)}


# Default concurrency — safe for Anthropic Tier 1.
# Increase to 5 (Tier 2), 8 (Tier 3), or 10-15 (Tier 4).
DEFAULT_CONCURRENCY = int(os.environ.get("RESUME_CONCURRENCY", "3"))


def process_all(limit: int = 10, concurrency: int | None = None) -> list[dict]:
    """Process all pending queue items, optionally in parallel.

    Args:
        limit: Max items to fetch from queue.
        concurrency: Max parallel resume pipelines. Defaults to RESUME_CONCURRENCY
                     env var or 3. Set to 1 for sequential processing.
    """
    workers = concurrency or DEFAULT_CONCURRENCY
    items = fetch_pending_queue_items(limit=limit)

    if not items:
        print("No pending items in resume_queue.")
        return []

    print(f"Found {len(items)} pending item(s) in resume_queue.")
    print(f"Processing with concurrency={workers}\n")

    if workers == 1:
        # Sequential mode
        results = []
        for i, item in enumerate(items, 1):
            print(f"\n[{i}/{len(items)}] {item.get('title', '')} @ {item.get('company_name', '')}")
            results.append(_process_one_safe(item))
    else:
        # Parallel mode
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_item = {
                pool.submit(_process_one_safe, item): item
                for item in items
            }
            for future in as_completed(future_to_item):
                results.append(future.result())

    # Summary
    success = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "error")
    print(f"\n{'='*60}")
    print(f"  Queue processing complete: {success} succeeded, {failed} failed")
    print(f"  Concurrency: {workers} workers")
    print(f"{'='*60}")

    return results
