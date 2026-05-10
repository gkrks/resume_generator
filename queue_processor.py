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
    is_us_location,
)
from orchestrator import run as run_pipeline
from scraper import scrape_jd

# Google Drive upload is optional — skipped if credentials aren't set
_DRIVE_ENABLED = bool(
    os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    or os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
)


def _upload_to_drive(output_dir: str, folder_parts: list[str] | None = None):
    """Upload output to Google Drive if credentials are configured."""
    if not _DRIVE_ENABLED:
        return
    try:
        from drive_uploader import upload_output_dir
        print(f"\n  Uploading to Google Drive...")
        links = upload_output_dir(output_dir, folder_parts=folder_parts)
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

    # Strict US-only check on the listing's location (second layer of defense)
    listing_loc = listing.get("location_raw", "")
    if not is_us_location(listing_loc):
        print(f"  SKIPPED: Non-US location on job_listing: [{listing_loc}]")
        print(f"  Title: {title} @ {company}")
        return {"output_dir": "", "tier": "Skipped", "checks": {
            "ats_check": False, "recruiter_check": False, "hr_check": False,
        }}

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

    # Only mark as done if the resume PDF was actually created on disk
    resume_pdf = result.get("resume_pdf", "")
    if not resume_pdf or not os.path.exists(resume_pdf):
        raise RuntimeError(
            f"Resume PDF was not created for {title} @ {company} "
            f"(expected: {resume_pdf})"
        )

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
    _upload_to_drive(result.get("output_dir", ""), result.get("folder_parts"))

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
DEFAULT_CONCURRENCY = int(os.environ.get("RESUME_CONCURRENCY", "8"))


def _warm_cache_for_batch(items: list[dict]) -> dict:
    """Load master_resume once and warm the prompt cache before parallel fan-out.

    Returns the loaded master_resume dict so callers don't re-read it.
    """
    from pathlib import Path
    from agents.base import warm_cache

    master_path = Path(__file__).resolve().parent / "config" / "master_resume.json"
    with open(master_path) as f:
        master_resume = json.load(f)

    if len(items) > 1:
        print(f"  Warming prompt cache for {len(items)} parallel runs...")
        warm_cache(master_resume)
    return master_resume


def _batch_analyze_jds(items: list[dict], master_resume: dict) -> dict[str, dict]:
    """Run batched JD analysis for multiple items in one API call.

    Returns a dict mapping queue_id -> jd_analysis.
    Falls back to individual calls if batch fails.
    """
    from agents.jd_analyzer import analyze_jds_batch, analyze_jd

    # Build JD texts for each item
    jd_items = []
    queue_ids = []
    for item in items:
        listing = fetch_job_listing(item["listing_id"])
        if not listing:
            continue

        # Check US location
        listing_loc = listing.get("location_raw", "")
        if not is_us_location(listing_loc):
            continue

        jd_text = _build_jd_text(listing, item)

        # Scrape if empty
        raw_jd = listing.get("raw_jd_excerpt") or ""
        if not raw_jd.strip():
            role_url = item.get("role_url", "")
            if role_url:
                scraped = scrape_jd(role_url)
                if scraped:
                    jd_text = jd_text + "\n\n--- FULL JOB DESCRIPTION ---\n" + scraped

        jd_items.append({
            "jd_text": jd_text,
            "role_type": item.get("role_category", "PM"),
        })
        queue_ids.append(item["id"])

    if not jd_items:
        return {}

    # Batch only makes sense for 2+ items
    if len(jd_items) < 2:
        analysis = analyze_jd(jd_items[0]["jd_text"], master_resume, jd_items[0]["role_type"])
        return {queue_ids[0]: analysis}

    print(f"\n  Batching JD analysis for {len(jd_items)} roles in one API call...")
    try:
        analyses = analyze_jds_batch(jd_items, master_resume)
        if len(analyses) == len(queue_ids):
            return dict(zip(queue_ids, analyses))
        else:
            print(f"  WARNING: Batch returned {len(analyses)} results for {len(queue_ids)} JDs — falling back")
    except Exception as e:
        print(f"  WARNING: Batch JD analysis failed ({e}) — falling back to individual calls")

    # Fallback: individual calls
    result = {}
    for qid, item in zip(queue_ids, jd_items):
        result[qid] = analyze_jd(item["jd_text"], master_resume, item["role_type"])
    return result


def process_all(limit: int = 10, concurrency: int | None = None) -> list[dict]:
    """Process all pending queue items, optionally in parallel.

    Optimizations:
      1. Cache warm-up: one cheap Haiku call primes the cache before fan-out
      2. Batched JD analysis: one API call for all JDs (when >1 item)
      3. Early exit: skip fix loops if all 3 checks fail on round 0

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

    # Warm the prompt cache before parallel fan-out
    _warm_cache_for_batch(items)

    STAGGER_DELAY = 5  # seconds between each parallel launch

    if workers == 1:
        # Sequential mode
        results = []
        for i, item in enumerate(items, 1):
            print(f"\n[{i}/{len(items)}] {item.get('title', '')} @ {item.get('company_name', '')}")
            results.append(_process_one_safe(item))
    else:
        # Parallel mode with staggered launches
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time

        results = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for i, item in enumerate(items):
                if i > 0:
                    print(f"  [stagger] Waiting {STAGGER_DELAY}s before launching next...")
                    time.sleep(STAGGER_DELAY)
                title = item.get('title', '')[:40]
                company = item.get('company_name', '')
                print(f"  [launch {i+1}/{len(items)}] {title} @ {company}")
                futures[pool.submit(_process_one_safe, item)] = item

            for future in as_completed(futures):
                results.append(future.result())

    # Summary
    success = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "error")
    print(f"\n{'='*60}")
    print(f"  Queue processing complete: {success} succeeded, {failed} failed")
    print(f"  Concurrency: {workers} workers")
    print(f"{'='*60}")

    return results
