"""
Site crawler — sitemap discovery + page content extraction via trafilatura.
Uses a lightweight sitemap parser (requests + xml.etree) instead of
ultimate-sitemap-parser to avoid file-descriptor exhaustion on Streamlit Cloud.
"""

import json
import time
import xml.etree.ElementTree as ET
from typing import Optional

import requests
import trafilatura

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
_HEADERS = {"User-Agent": "TM-Studio-Crawler/1.0"}
_TIMEOUT = 15


def _fetch_xml(url: str) -> Optional[ET.Element]:
    """Fetch and parse an XML sitemap. Returns root element or None."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        return ET.fromstring(resp.content)
    except Exception:
        return None


def _extract_urls_from_sitemap(url: str, max_urls: int) -> list[str]:
    """Recursively extract URLs from a sitemap (handles sitemap indexes)."""
    root = _fetch_xml(url)
    if root is None:
        return []

    urls: list[str] = []

    # Check if this is a sitemap index (contains <sitemap> entries)
    sitemaps = root.findall(".//sm:sitemap/sm:loc", _SITEMAP_NS)
    if not sitemaps:
        # Try without namespace (some sitemaps omit it)
        sitemaps = root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap/{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
    if not sitemaps:
        sitemaps = [el for el in root.iter() if el.tag.endswith("}loc") and el.getparent().tag.endswith("}sitemap")] if hasattr(ET.Element, "getparent") else []

    if sitemaps:
        # It's a sitemap index — recurse into each child sitemap
        for sitemap_loc in sitemaps:
            if len(urls) >= max_urls:
                break
            child_urls = _extract_urls_from_sitemap(
                sitemap_loc.text.strip(), max_urls - len(urls)
            )
            urls.extend(child_urls)
        return urls[:max_urls]

    # Regular sitemap — extract <url><loc> entries
    locs = root.findall(".//sm:url/sm:loc", _SITEMAP_NS)
    if not locs:
        # Fallback: find any element ending in "loc" inside "url"
        for el in root.iter():
            tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if tag == "loc" and el.text:
                urls.append(el.text.strip())
                if len(urls) >= max_urls:
                    break
    else:
        for loc in locs:
            if loc.text:
                urls.append(loc.text.strip())
                if len(urls) >= max_urls:
                    break

    return urls[:max_urls]


def discover_urls(domain: str, max_urls: int = 100) -> list[str]:
    """Discover URLs from a domain via sitemap.

    Tries these locations in order:
    - /sitemap.xml
    - /sitemap_index.xml
    - Sitemap URL from /robots.txt

    Returns up to max_urls URLs sorted alphabetically.
    """
    if not domain.startswith("http"):
        domain = f"https://{domain}"
    domain = domain.rstrip("/")

    urls: list[str] = []

    # Try common sitemap locations
    for path in ["/sitemap.xml", "/sitemap_index.xml"]:
        urls = _extract_urls_from_sitemap(f"{domain}{path}", max_urls)
        if urls:
            return sorted(urls)[:max_urls]

    # Try robots.txt for sitemap references
    try:
        resp = requests.get(
            f"{domain}/robots.txt", headers=_HEADERS, timeout=_TIMEOUT
        )
        if resp.ok:
            for line in resp.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    sitemap_url = line.split(":", 1)[1].strip()
                    urls = _extract_urls_from_sitemap(sitemap_url, max_urls)
                    if urls:
                        return sorted(urls)[:max_urls]
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
