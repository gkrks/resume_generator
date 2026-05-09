"""JD Scraper — fetches job description text from a URL.

Uses Playwright (headless Chromium) to render JS-heavy ATS pages
(Lever, Greenhouse, Workday, Meta Careers, etc.).
Falls back to httpx for simple pages.
"""

import re
import httpx
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError


def _extract_text_from_html(html: str) -> str:
    """Strip HTML to readable text."""
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
    """Simple HTTP fetch — works for static pages (Lever, Greenhouse)."""
    try:
        resp = httpx.get(
            url,
            follow_redirects=True,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36"
            },
        )
        resp.raise_for_status()
        return _extract_text_from_html(resp.text)
    except Exception:
        return ""


def _scrape_with_playwright(url: str) -> str:
    """Headless Chromium — handles JS-rendered pages (Meta, Workday, etc.)."""
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

            # Block images/media/fonts to speed up loading
            page.route("**/*.{png,jpg,jpeg,gif,svg,webp,woff,woff2,ttf,mp4,webm}",
                       lambda route: route.abort())

            page.goto(url, wait_until="networkidle", timeout=30000)

            # Wait a bit for any lazy-loaded content
            page.wait_for_timeout(2000)

            # Try to find the main job description content
            # Common selectors across ATS platforms
            selectors = [
                "[data-testid='job-details']",       # Meta
                ".posting-page",                      # Lever
                "#content",                           # Greenhouse
                ".job-description",                   # Generic
                "[class*='jobDescription']",          # Workday
                "[class*='job-detail']",              # Generic
                "[class*='posting']",                 # Generic
                "main",                               # Fallback
                "article",                            # Fallback
                "body",                               # Last resort
            ]

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

            # If selectors didn't work, get full page text
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


def scrape_jd(url: str) -> str:
    """Fetch a job posting URL and extract the JD text.

    Strategy:
      1. Try simple httpx fetch first (fast, works for Lever/Greenhouse)
      2. If result is too short (<300 chars), fall back to Playwright
    """
    if not url:
        return ""

    print(f"  Scraping JD from {url}...")

    # Try httpx first (fast)
    text = _scrape_with_httpx(url)
    if len(text) >= 300:
        print(f"  Scraped {len(text)} chars via httpx")
        return text

    # Fall back to Playwright for JS-rendered pages
    print(f"  httpx got {len(text)} chars — trying Playwright (headless browser)...")
    text = _scrape_with_playwright(url)
    if text:
        print(f"  Scraped {len(text)} chars via Playwright")
    else:
        print(f"  WARNING: Could not scrape JD from {url}")

    return text
