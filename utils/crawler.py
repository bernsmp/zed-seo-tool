"""
Site crawler — sitemap discovery + page content extraction via trafilatura.
"""

import json
import time
from typing import Optional

import trafilatura
from usp.tree import sitemap_tree_for_homepage


def discover_urls(domain: str, max_urls: int = 100) -> list[str]:
    """Discover URLs from a domain via sitemap.

    Tries sitemap_tree_for_homepage which handles:
    - /sitemap.xml
    - /robots.txt sitemap references
    - Nested / index sitemaps

    Returns up to max_urls URLs sorted alphabetically.
    """
    if not domain.startswith("http"):
        domain = f"https://{domain}"
    domain = domain.rstrip("/")

    urls = []
    try:
        tree = sitemap_tree_for_homepage(domain)
        for page in tree.all_pages():
            urls.append(page.url)
            if len(urls) >= max_urls:
                break
    except Exception:
        pass

    return sorted(urls)[:max_urls]


def extract_page(url: str) -> Optional[dict]:
    """Extract content from a single URL using trafilatura.

    Returns dict with url, title, content, description — or None on failure.
    """
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None

        # Extract main text content
        content = trafilatura.extract(downloaded) or ""

        # Extract metadata
        metadata = trafilatura.extract(
            downloaded,
            output_format="json",
            with_metadata=True,
        )
        meta = {}
        if metadata:
            try:
                meta = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                pass

        return {
            "url": url,
            "title": meta.get("title", ""),
            "description": meta.get("description", ""),
            "content": content[:2000],  # Cap content length
        }
    except Exception:
        return None


def crawl_site(
    domain: str,
    max_pages: int = 50,
    delay: float = 1.0,
    progress_callback=None,
) -> list[dict]:
    """Crawl a site: discover URLs then extract content from each.

    Args:
        domain: Domain to crawl (e.g. 'example.com').
        max_pages: Maximum pages to extract content from.
        delay: Seconds between requests (respectful crawling).
        progress_callback: Optional callable(current, total) for progress updates.

    Returns:
        List of page dicts with url, title, description, content.
    """
    urls = discover_urls(domain, max_urls=max_pages)
    if not urls:
        return []

    pages = []
    for i, url in enumerate(urls):
        if progress_callback:
            progress_callback(i, len(urls))

        page = extract_page(url)
        if page:
            pages.append(page)

        if i < len(urls) - 1:
            time.sleep(delay)

    if progress_callback:
        progress_callback(len(urls), len(urls))

    return pages
