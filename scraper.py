"""JD Scraper — fetches job description text from any ATS platform.

Strategy per platform:
  1. Lever        → Public JSON API (no auth needed)
  2. Greenhouse   → Public JSON API (no auth needed)
  3. Ashby        → Public JSON API (no auth needed)
  4. SmartRecruiters → Public JSON API (no auth needed)
  5. Workday      → Playwright (JS-rendered)
  6. Meta Careers → Playwright (JS-rendered)
  7. LinkedIn     → Playwright (JS-rendered, limited)
  8. Everything else → httpx first, Playwright fallback
"""

import re
import json
from urllib.parse import urlparse, parse_qs
import httpx
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError


# ── Platform detection ───────────────────────────────────────────

def _detect_platform(url: str) -> str:
    """Detect ATS platform from URL."""
    host = urlparse(url).hostname or ""
    path = urlparse(url).path or ""

    if "lever.co" in host:
        return "lever"
    if "greenhouse.io" in host or "boards.greenhouse" in host:
        return "greenhouse"
    if "ashbyhq.com" in host:
        return "ashby"
    if "smartrecruiters.com" in host:
        return "smartrecruiters"
    if "myworkdayjobs.com" in host or "myworkday.com" in host or "wd5.myworkdaysite" in host:
        return "workday"
    if "metacareers.com" in host or "meta.com/careers" in host:
        return "meta"
    if "linkedin.com" in host:
        return "linkedin"
    if "icims.com" in host:
        return "icims"
    if "jobvite.com" in host:
        return "jobvite"
    if "google.com" in host and "careers" in (host + path):
        return "google"
    if "careers.google.com" in host:
        return "google"
    if "amazon.jobs" in host:
        return "amazon"

    # Embedded Ashby — career pages that use ashby_jid query param
    qs = parse_qs(urlparse(url).query)
    if "ashby_jid" in qs:
        return "ashby"

    return "generic"


# ── API-based scrapers (fast, reliable) ──────────────────────────

def _scrape_lever(url: str) -> str:
    """Lever public API: GET /v0/postings/{company}/{posting_id}"""
    # URL format: https://jobs.lever.co/{company}/{posting_id}
    parts = urlparse(url).path.strip("/").split("/")
    if len(parts) < 2:
        return ""

    company = parts[0]
    posting_id = parts[1]
    api_url = f"https://api.lever.co/v0/postings/{company}/{posting_id}"

    try:
        resp = httpx.get(api_url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  Lever API failed: {e}")
        return ""

    sections = []
    sections.append(f"Role: {data.get('text', '')}")
    sections.append(f"Company: {data.get('categories', {}).get('team', '')}")
    sections.append(f"Location: {data.get('categories', {}).get('location', '')}")
    sections.append(f"Commitment: {data.get('categories', {}).get('commitment', '')}")
    sections.append("")

    # Description HTML → text
    desc = data.get("descriptionPlain") or _html_to_text(data.get("description", ""))
    if desc:
        sections.append(desc)
        sections.append("")

    # Additional sections (Qualifications, Responsibilities, etc.)
    for item in data.get("lists", []):
        sections.append(f"--- {item.get('text', '')} ---")
        for li in item.get("content", "").split("<li>"):
            clean = _html_to_text(li).strip()
            if clean:
                sections.append(f"- {clean}")
        sections.append("")

    # Additional description
    additional = data.get("additionalPlain") or _html_to_text(data.get("additional", ""))
    if additional:
        sections.append(additional)

    return "\n".join(sections).strip()


def _scrape_greenhouse(url: str) -> str:
    """Greenhouse public API or board page scrape."""
    # URL formats:
    #   https://boards.greenhouse.io/{company}/jobs/{job_id}
    #   https://{company}.greenhouse.io/jobs/{job_id} (redirect)
    #   https://job-boards.greenhouse.io/company/jobs/{job_id}
    path = urlparse(url).path.strip("/")
    parts = path.split("/")

    # Try to extract company and job_id
    company = None
    job_id = None
    host = urlparse(url).hostname or ""

    if "boards.greenhouse.io" in host or "job-boards.greenhouse.io" in host:
        # /company/jobs/123
        if "jobs" in parts:
            jobs_idx = parts.index("jobs")
            company = parts[jobs_idx - 1] if jobs_idx > 0 else None
            job_id = parts[jobs_idx + 1] if jobs_idx + 1 < len(parts) else None
    elif ".greenhouse.io" in host:
        company = host.split(".")[0]
        if "jobs" in parts:
            jobs_idx = parts.index("jobs")
            job_id = parts[jobs_idx + 1] if jobs_idx + 1 < len(parts) else None

    if company and job_id:
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}"
        try:
            resp = httpx.get(api_url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            sections = []
            sections.append(f"Role: {data.get('title', '')}")
            loc = data.get("location", {})
            sections.append(f"Location: {loc.get('name', '')}")
            sections.append("")

            content = _html_to_text(data.get("content", ""))
            if content:
                sections.append(content)

            return "\n".join(sections).strip()
        except Exception as e:
            print(f"  Greenhouse API failed: {e}")

    # Fallback to HTML scrape
    return _scrape_with_httpx(url)


def _scrape_ashby(url: str, org_name: str | None = None, job_id: str | None = None) -> str:
    """Ashby — GraphQL API first, Playwright fallback."""
    # Extract org_name and job_id from URL if not provided
    if not org_name or not job_id:
        parsed = urlparse(url)
        if "ashbyhq.com" in (parsed.hostname or ""):
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 2:
                org_name = org_name or parts[0]
                job_id = job_id or parts[1]

    # Try GraphQL API first
    if org_name and job_id:
        api_url = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPostingWithBoard"
        payload = {
            "operationName": "ApiJobPostingWithBoard",
            "variables": {
                "organizationHostedJobsPageName": org_name,
                "jobPostingId": job_id,
            },
            "query": (
                "query ApiJobPostingWithBoard("
                "$organizationHostedJobsPageName: String!, "
                "$jobPostingId: String!) { "
                "jobPosting("
                "organizationHostedJobsPageName: $organizationHostedJobsPageName, "
                "jobPostingId: $jobPostingId) { "
                "id title descriptionHtml departmentName locationName } }"
            ),
        }
        try:
            resp = httpx.post(api_url, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            posting = (data.get("data") or {}).get("jobPosting")
            if posting:
                sections = []
                sections.append(f"Role: {posting.get('title', '')}")
                dept = posting.get("departmentName", "")
                if dept:
                    sections.append(f"Department: {dept}")
                loc = posting.get("locationName", "")
                if loc:
                    sections.append(f"Location: {loc}")
                sections.append("")

                desc = _html_to_text(posting.get("descriptionHtml", ""))
                if desc:
                    sections.append(desc)

                result = "\n".join(sections).strip()
                if len(result) >= 200:
                    return result
        except Exception as e:
            print(f"  Ashby GraphQL API failed: {e}")

    # Fallback to Playwright — use the ashbyhq URL if we have org+job info
    playwright_url = url
    if org_name and job_id:
        playwright_url = f"https://jobs.ashbyhq.com/{org_name}/{job_id}"
    return _scrape_with_playwright(playwright_url, selectors=[
        "[class*='ashby-job-posting-brief-description']",
        "[class*='jobPosting']",
        "[class*='job-posting']",
        "main",
        "body",
    ])


def _scrape_smartrecruiters(url: str) -> str:
    """SmartRecruiters public API."""
    # URL: https://jobs.smartrecruiters.com/{company}/{job_id}
    parts = urlparse(url).path.strip("/").split("/")
    if len(parts) < 2:
        return _scrape_with_httpx(url)

    company = parts[0]
    job_id = parts[-1]

    api_url = f"https://api.smartrecruiters.com/v1/companies/{company}/postings/{job_id}"
    try:
        resp = httpx.get(api_url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        sections = []
        sections.append(f"Role: {data.get('name', '')}")
        loc = data.get("location", {})
        sections.append(f"Location: {loc.get('city', '')}, {loc.get('region', '')}")
        sections.append(f"Department: {data.get('department', {}).get('label', '')}")
        sections.append("")

        # Job ad sections
        for section in data.get("jobAd", {}).get("sections", {}).values():
            title = section.get("title", "")
            text = _html_to_text(section.get("text", ""))
            if text:
                sections.append(f"--- {title} ---")
                sections.append(text)
                sections.append("")

        return "\n".join(sections).strip()
    except Exception as e:
        print(f"  SmartRecruiters API failed: {e}")
        return _scrape_with_httpx(url)


# ── Playwright-based scrapers (for JS-rendered pages) ────────────

def _scrape_with_playwright(url: str, selectors: list[str] | None = None) -> str:
    """Headless Chromium — handles JS-rendered pages."""
    if selectors is None:
        selectors = [
            "[data-testid='job-details']",
            ".posting-page",
            "#content",
            ".job-description",
            "[class*='jobDescription']",
            "[class*='job-detail']",
            "[class*='posting']",
            "main",
            "article",
            "body",
        ]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()
            page.route("**/*.{png,jpg,jpeg,gif,svg,webp,woff,woff2,ttf,mp4,webm}",
                       lambda route: route.abort())

            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)

            text = ""
            for selector in selectors:
                try:
                    el = page.query_selector(selector)
                    if el:
                        text = el.inner_text()
                        if len(text) > 200:
                            break
                except Exception:
                    continue

            if len(text) < 200:
                text = page.inner_text("body")

            browser.close()
            return text.strip()

    except PWTimeoutError:
        print(f"  WARNING: Playwright timeout for {url}")
        return ""
    except Exception as e:
        print(f"  WARNING: Playwright failed for {url}: {e}")
        return ""


def _scrape_meta(url: str) -> str:
    """Meta Careers — JS-rendered, specific selectors."""
    return _scrape_with_playwright(url, selectors=[
        "[data-testid='job-details']",
        "[class*='jobDetails']",
        "[class*='_job']",
        "main",
        "body",
    ])


def _scrape_workday(url: str) -> str:
    """Workday — heavily JS-rendered."""
    return _scrape_with_playwright(url, selectors=[
        "[data-automation-id='jobPostingDescription']",
        "[class*='jobDescription']",
        ".css-kyg8or",
        "main",
        "body",
    ])


def _scrape_google(url: str) -> str:
    """Google Careers — Playwright with specific content selectors."""
    return _scrape_with_playwright(url, selectors=[
        "[class*='gc-card__content']",
        "[class*='gc-job-detail']",
        "[data-id='job-detail']",
        ".content-card",
        "gc-job-detail",
        "main",
        "body",
    ])


def _scrape_amazon(url: str) -> str:
    """Amazon Jobs — heavy bot protection, use Playwright with stealth."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
                java_script_enabled=True,
            )
            # Remove webdriver flag
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => false});
            """)

            page = context.new_page()
            page.route("**/*.{png,jpg,jpeg,gif,svg,webp,woff,woff2,ttf,mp4,webm}",
                       lambda route: route.abort())

            page.goto(url, wait_until="domcontentloaded", timeout=45000)

            # Amazon Jobs loads content dynamically — wait for it
            try:
                page.wait_for_selector("#job-detail-body, .job-detail, [class*='jobDetail']",
                                       timeout=15000)
            except PWTimeoutError:
                pass

            page.wait_for_timeout(3000)

            text = ""
            for selector in [
                "#job-detail-body",
                ".job-detail",
                "[class*='jobDetail']",
                "[class*='job-description']",
                "main",
                "body",
            ]:
                try:
                    el = page.query_selector(selector)
                    if el:
                        text = el.inner_text()
                        if len(text) > 200:
                            break
                except Exception:
                    continue

            if len(text) < 200:
                text = page.inner_text("body")

            browser.close()
            return text.strip()

    except Exception as e:
        print(f"  WARNING: Amazon scraper failed: {e}")
        return ""


def _scrape_linkedin(url: str) -> str:
    """LinkedIn — try the public view first, fall back to Playwright."""
    return _scrape_with_playwright(url, selectors=[
        ".description__text",
        ".show-more-less-html__markup",
        "[class*='description']",
        "main",
        "body",
    ])


# ── Helpers ──────────────────────────────────────────────────────

def _html_to_text(html: str) -> str:
    """Strip HTML to readable text."""
    if not html:
        return ""
    content = html
    content = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL)
    content = re.sub(r"<style[^>]*>.*?</style>", "", content, flags=re.DOTALL)
    content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    content = re.sub(r"<(?:br|hr|p|div|li|tr|h[1-6])[^>]*>", "\n", content, flags=re.IGNORECASE)
    content = re.sub(r"</(?:p|div|li|tr|h[1-6])>", "\n", content, flags=re.IGNORECASE)
    content = re.sub(r"<[^>]+>", " ", content)
    content = content.replace("&amp;", "&")
    content = content.replace("&lt;", "<")
    content = content.replace("&gt;", ">")
    content = content.replace("&quot;", '"')
    content = content.replace("&#39;", "'")
    content = content.replace("&nbsp;", " ")
    content = content.replace("\u00a0", " ")
    content = re.sub(r"[ \t]+", " ", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()


def _scrape_with_httpx(url: str) -> str:
    """Simple HTTP fetch — works for static pages."""
    try:
        resp = httpx.get(
            url, follow_redirects=True, timeout=30,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        )
        resp.raise_for_status()
        return _html_to_text(resp.text)
    except Exception:
        return ""


# ── Main entry point ─────────────────────────────────────────────

# Platform → scraper function
_SCRAPERS = {
    "lever": _scrape_lever,
    "greenhouse": _scrape_greenhouse,
    "ashby": _scrape_ashby,
    "smartrecruiters": _scrape_smartrecruiters,
    "meta": _scrape_meta,
    "workday": _scrape_workday,
    "linkedin": _scrape_linkedin,
    "google": _scrape_google,
    "amazon": _scrape_amazon,
}


def scrape_jd(url: str) -> str:
    """Fetch a job posting URL and extract the JD text.

    Auto-detects the ATS platform and uses the best strategy:
      - API-based for Lever, Greenhouse, Ashby, SmartRecruiters (fast, reliable)
      - Playwright for Meta, Workday, LinkedIn (JS-rendered)
      - httpx → Playwright fallback for everything else
    """
    if not url:
        return ""

    platform = _detect_platform(url)
    print(f"  Scraping JD from {url} (platform: {platform})...")

    # Embedded Ashby — URL is not on ashbyhq.com but has ashby_jid param
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if platform == "ashby" and "ashbyhq.com" not in host:
        qs = parse_qs(parsed.query)
        ashby_jid = qs.get("ashby_jid", [None])[0]
        if ashby_jid:
            # Build candidate org names from the hostname
            # e.g. www.clay.com → ["clay", "claylabs", "clayhq"]
            domain_parts = host.split(".")
            # Remove www prefix and TLD
            core_parts = [p for p in domain_parts if p not in ("www",)]
            if len(core_parts) >= 2:
                core_parts = core_parts[:-1]  # drop TLD
            base_name = core_parts[0] if core_parts else ""

            candidates = []
            if base_name:
                candidates.append(base_name)
                candidates.append(f"{base_name}labs")
                candidates.append(f"{base_name}hq")
            # Also try the full domain minus TLD if multi-part (e.g. "claylabs")
            if len(core_parts) > 1:
                joined = "".join(core_parts)
                if joined not in candidates:
                    candidates.append(joined)

            for org_guess in candidates:
                print(f"  Trying embedded Ashby with org={org_guess}, jid={ashby_jid}...")
                text = _scrape_ashby(url, org_name=org_guess, job_id=ashby_jid)
                if len(text) >= 200:
                    print(f"  Scraped {len(text)} chars via embedded Ashby (org={org_guess})")
                    return text

            # All org guesses failed — fall through to generic fallback
            print(f"  Embedded Ashby org guesses exhausted — trying fallbacks...")

    # Use platform-specific scraper if available
    scraper = _SCRAPERS.get(platform)
    if scraper:
        text = scraper(url)
        if len(text) >= 200:
            print(f"  Scraped {len(text)} chars via {platform} scraper")
            return text
        print(f"  {platform} scraper got {len(text)} chars — trying fallbacks...")

    # Generic fallback: httpx first, then Playwright
    text = _scrape_with_httpx(url)
    if len(text) >= 300:
        print(f"  Scraped {len(text)} chars via httpx")
        return text

    print(f"  httpx got {len(text)} chars — trying Playwright...")
    text = _scrape_with_playwright(url)
    if text:
        print(f"  Scraped {len(text)} chars via Playwright")
    else:
        print(f"  WARNING: Could not scrape JD from {url}")

    return text
