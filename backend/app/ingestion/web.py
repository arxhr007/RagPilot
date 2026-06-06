from __future__ import annotations

import importlib.util
import io
from contextlib import redirect_stdout
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from app.config import PROJECT_ROOT
from app.ingestion.text import chunks_from_text
from app.models.schemas import IngestedChunk


def _load_legacy_scraper():
    scraper_path = PROJECT_ROOT / "scraper.py"
    spec = importlib.util.spec_from_file_location("ragx_legacy_scraper", scraper_path)
    if not spec or not spec.loader:
        raise ImportError(f"Could not load scraper from {scraper_path}")
    scraper = importlib.util.module_from_spec(spec)
    with redirect_stdout(io.StringIO()):
        spec.loader.exec_module(scraper)

    scraper.rate_limiter = scraper.RateLimiter(scraper.REQUEST_DELAY)
    scraper.visited = set()
    scraper.collected_pages = []
    return scraper


def ingest_url(
    *,
    dataset_id: str,
    url: str,
    max_pages: int = 8,
    use_playwright: bool = False,
) -> tuple[dict[str, Any], list[IngestedChunk]]:
    legacy = _load_legacy_scraper()
    legacy.MAX_PAGES = max(1, min(max_pages, 50))
    legacy.REQUEST_DELAY = 0.2
    legacy.rate_limiter = legacy.RateLimiter(legacy.REQUEST_DELAY)

    parsed = urlparse(url)
    domain = parsed.netloc
    if not parsed.scheme or not domain:
        raise ValueError("URL must include http:// or https://")

    if max_pages == 1:
        page = legacy.fetch_single_page(url, use_playwright=use_playwright)
        pages = [page] if page else []
    else:
        pages = legacy.crawl_with_discovery_multithreaded(
            url,
            domain,
            use_playwright=use_playwright,
            num_threads=4,
        )

    input_id = str(uuid4())
    chunks: list[IngestedChunk] = []
    for page in pages:
        if not page or not page.get("text"):
            continue
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
    }
    return record, chunks
