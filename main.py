#!/usr/bin/env python3
"""Resume Generator — Multi-agent orchestration CLI.

Usage:
    # Process all pending jobs from Supabase resume_queue:
    python main.py --queue

    # Process up to N pending jobs:
    python main.py --queue --limit 5

    # From a JD URL (auto-fetches):
    python main.py --url "https://jobs.lever.co/company/abc123"

    # From a pasted JD file:
    python main.py --file jd.txt

    # From stdin:
    echo "JD text here" | python main.py --stdin

    # With role type override (default: PM):
    python main.py --file jd.txt --role SWE

    # With custom output directory:
    python main.py --file jd.txt --output ~/Desktop/MyCompany
"""

import argparse
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env before anything else touches env vars
load_dotenv()


def fetch_url(url: str) -> str:
    """Fetch a URL and return its text content."""
    import httpx

    resp = httpx.get(url, follow_redirects=True, timeout=30)
    resp.raise_for_status()

    content = resp.text
    if "<html" in content.lower():
        import re

        content = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL)
        content = re.sub(r"<style[^>]*>.*?</style>", "", content, flags=re.DOTALL)
        content = re.sub(r"<[^>]+>", "\n", content)
        content = re.sub(r"\n{3,}", "\n\n", content)
        content = content.strip()
    return content


def main():
    parser = argparse.ArgumentParser(
        description="Resume Generator — Multi-agent pipeline that creates "
        "tailored resumes, cover letters, and cold outreach from a JD.",
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--queue",
        action="store_true",
        help="Process pending jobs from Supabase resume_queue",
    )
    input_group.add_argument("--url", help="URL of the job posting")
    input_group.add_argument("--file", help="Path to a text file containing the JD")
    input_group.add_argument(
        "--stdin", action="store_true", help="Read JD from stdin"
    )

    parser.add_argument(
        "--role",
        default="PM",
        help="Target role type: PM, APM, TPM, SWE, PLM, etc. (default: PM)",
    )
    parser.add_argument(
        "--output", help="Output directory (default: ~/Desktop/<company>/)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max pending jobs to process in --queue mode (default: 10)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="Parallel resume pipelines in --queue mode (default: 3, max ~10)",
    )

    args = parser.parse_args()

    # ── Queue mode: pull from Supabase ───────────────────────────
    if args.queue:
        from queue_processor import process_all

        print(f"Checking Supabase resume_queue for pending items (limit={args.limit})...\n")
        results = process_all(limit=args.limit, concurrency=args.concurrency)

        success = sum(1 for r in results if r["status"] == "success")
        failed = sum(1 for r in results if r["status"] == "error")
        print(f"\nDone. {success} succeeded, {failed} failed out of {len(results)} total.")
        sys.exit(1 if failed else 0)

    # ── Direct mode: URL / file / stdin ──────────────────────────
    if args.url:
        print(f"Fetching JD from {args.url}...")
        jd_text = fetch_url(args.url)
    elif args.file:
        jd_path = Path(args.file)
        if not jd_path.exists():
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        jd_text = jd_path.read_text()
    else:
        print("Reading JD from stdin (paste JD text, then Ctrl+D)...")
        jd_text = sys.stdin.read()

    if not jd_text.strip():
        print("Error: Empty job description", file=sys.stderr)
        sys.exit(1)

    print(f"\nJD loaded ({len(jd_text)} chars)")
    print(f"Role type: {args.role}")
    print(f"Starting multi-agent pipeline...\n")

    from orchestrator import run

    results = run(
        jd_text=jd_text,
        role_type=args.role,
        output_base=args.output,
    )

    print(f"\nAll done! Output directory: {results['output_dir']}")


if __name__ == "__main__":
    main()
