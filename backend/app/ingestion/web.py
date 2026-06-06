from __future__ import annotations

import re
from collections import deque
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse
from uuid import uuid4

import requests
from bs4 import BeautifulSoup

from app.ingestion.text import chunks_from_text
from app.models.schemas import IngestedChunk


USER_AGENT = "RAGX-WebIngest/1.0 (+local hackathon crawler)"
TIMEOUT = 12
SKIP_EXTENSIONS = (
    ".css", ".js", ".ico", ".woff", ".woff2", ".ttf", ".eot", ".png", ".jpg", ".jpeg",
    ".gif", ".webp", ".svg", ".mp4", ".webm", ".mp3", ".zip", ".rar", ".7z",
)
DOCUMENT_EXTENSIONS = (".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".csv", ".txt", ".md")


def _normalize_url(url: str) -> str:
    clean, _fragment = urldefrag(url.strip())
    parsed = urlparse(clean)
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return parsed._replace(path=path).geturl()


def _same_domain(url: str, domain: str) -> bool:
    return urlparse(url).netloc.lower() == domain.lower()


def _is_crawlable(url: str, domain: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if not _same_domain(url, domain):
        return False
    lower_path = parsed.path.lower()
    return not lower_path.endswith(SKIP_EXTENSIONS)


def _is_document(url: str) -> bool:
    return urlparse(url).path.lower().endswith(DOCUMENT_EXTENSIONS)


def _clean_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "canvas", "form"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _page_from_html(url: str, html: str, domain: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string.strip() if soup.title and soup.title.string else url)
    description_tag = soup.find("meta", attrs={"name": "description"})
    description = ""
    if description_tag and description_tag.get("content"):
        description = str(description_tag["content"]).strip()

    links: list[str] = []
    document_links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        absolute = _normalize_url(urljoin(url, href))
        if _is_document(absolute):
            document_links.append(absolute)
        elif _is_crawlable(absolute, domain):
            links.append(absolute)

    return {
        "url": url,
        "title": title,
        "description": description,
        "text": _clean_text(soup),
        "links": sorted(set(links)),
        "document_links": sorted(set(document_links)),
    }


def _fetch_requests(url: str, session: requests.Session) -> str:
    response = session.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type and content_type:
        return ""
    return response.text


def _fetch_playwright(url: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError("Playwright is not installed. Run `pip install playwright` and `playwright install chromium`.") from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto(url, wait_until="networkidle", timeout=TIMEOUT * 1000)
        html = page.content()
        browser.close()
        return html


def _fetch_page(url: str, domain: str, session: requests.Session, use_playwright: bool) -> dict[str, Any] | None:
    html = _fetch_playwright(url) if use_playwright else _fetch_requests(url, session)
    if not html:
        return None
    page = _page_from_html(url, html, domain)
    return page if page.get("text") else None


def _sitemap_urls(base_url: str, domain: str, session: requests.Session, max_pages: int) -> list[str]:
    parsed = urlparse(base_url)
    roots = [
        f"{parsed.scheme}://{domain}/sitemap.xml",
        f"{parsed.scheme}://{domain}/sitemap_index.xml",
    ]
    urls: list[str] = []
    for sitemap_url in roots:
        try:
            response = session.get(sitemap_url, timeout=TIMEOUT)
            if not response.ok:
                continue
            soup = BeautifulSoup(response.text, "xml")
            for loc in soup.find_all("loc"):
                candidate = _normalize_url(loc.get_text(strip=True))
                if _is_crawlable(candidate, domain) and not _is_document(candidate):
                    urls.append(candidate)
                if len(urls) >= max_pages:
                    return sorted(set(urls))[:max_pages]
        except Exception:
            continue
    return sorted(set(urls))[:max_pages]


def _crawl(url: str, max_pages: int, use_playwright: bool, max_depth: int = 3) -> list[dict[str, Any]]:
    parsed = urlparse(url)
    domain = parsed.netloc
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    start = _normalize_url(url)
    sitemap_candidates = _sitemap_urls(start, domain, session, max_pages)
    queue = deque([(start, 0)] + [(candidate, 1) for candidate in sitemap_candidates if candidate != start])
    seen: set[str] = set()
    pages: list[dict[str, Any]] = []

    while queue and len(pages) < max_pages:
        current, depth = queue.popleft()
        current = _normalize_url(current)
        if current in seen or depth > max_depth or not _is_crawlable(current, domain) or _is_document(current):
            continue
        seen.add(current)
        try:
            page = _fetch_page(current, domain, session, use_playwright)
        except Exception:
            continue
        if not page:
            continue
        pages.append(page)
        if len(pages) >= max_pages:
            break
        for link in page.get("links", []):
            if link not in seen:
                queue.append((link, depth + 1))
    return pages


def ingest_url(
    *,
    dataset_id: str,
    url: str,
    max_pages: int = 8,
    use_playwright: bool = False,
) -> tuple[dict[str, Any], list[IngestedChunk]]:
    parsed = urlparse(url)
    domain = parsed.netloc
    if not parsed.scheme or not domain:
        raise ValueError("URL must include http:// or https://")

    capped_pages = max(1, min(max_pages, 50))
    pages = _crawl(url, capped_pages, use_playwright=use_playwright, max_depth=3)

    input_id = str(uuid4())
    chunks: list[IngestedChunk] = []
    for page in pages:
        chunks.extend(
            chunks_from_text(
                dataset_id=dataset_id,
                input_id=input_id,
                text=page["text"],
                title=page.get("title") or page.get("url") or url,
                url=page.get("url") or url,
                metadata={
                    "kind": "website",
                    "description": page.get("description", ""),
                    "document_links": page.get("document_links", []),
                    "crawl_links": page.get("links", []),
                    "use_playwright": use_playwright,
                },
            )
        )

    record = {
        "id": input_id,
        "name": url,
        "kind": "website",
        "url": url,
        "pages": len(pages),
        "domain": domain,
        "recursive": capped_pages > 1,
        "use_playwright": use_playwright,
    }
    return record, chunks
