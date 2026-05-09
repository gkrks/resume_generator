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


# ── Reads ────────────────────────────────────────────────────────

def fetch_pending_queue_items(limit: int = 10) -> list[dict]:
    """Get resume_queue rows where was_resume_created = false,
    ordered by requested_at DESC."""
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
    return resp.json()


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
