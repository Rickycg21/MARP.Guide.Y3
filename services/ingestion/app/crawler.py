"""
Responsible for "discovery": 
- Fetch the MARP landing page
- Parse PDF links
- Download each PDF (if not already present)
- Compute metadata, and yield a per-document dict that the API will publish as a DocumentDiscovered event.

We keep network/IO logic here (separate from FastAPI routes) for:
- testability: we can unit-test parsing and ID logic without HTTP server
- clarity: main.py focuses on API + events, while this module does discovery work
"""

import asyncio
import hashlib
import os
from datetime import datetime, timezone
from typing import AsyncIterator, Tuple, Dict, List

import httpx
from bs4 import BeautifulSoup
import pdfplumber

from common.config import settings

MARP_SOURCE_URL = os.getenv(
    "MARP_SOURCE_URL",
    "https://www.lancaster.ac.uk/academic-standards-and-quality/regulations-and-policies/manual-of-academic-regulations-and-procedures/"
)

def now_iso() -> str:
    """Return current time in ISO-8601 with UTC timezone, e.g., 2025-10-29T19:45:12.123456+00:00"""
    return datetime.now(tz=timezone.utc).isoformat()

def _doc_id_from_url(url: str) -> str:
    """
    Produce a stable, deterministic document ID from the URL.
    - Normalise case, hash it, and prefix with 'marp-'.
    - Titles can change; URLs rarely do. This makes reruns idempotent.
    """
    h = hashlib.sha1(url.strip().lower().encode("utf-8")).hexdigest()[:16]
    return f"marp-{h}"

async def fetch_html(client: httpx.AsyncClient, url: str) -> str:
    """
    Download the HTML for the given URL.
    AsyncClient because:
      - It's a reusable HTTP session that supports async I/O and connection pooling.
      - 'await' yields control to event loop while waiting on the network (non-blocking).
    follow_redirects=True handles 3xx redirects automatically.
    timeout=30 ensures we fail fast instead of hanging forever.
    """
    r = await client.get(url, follow_redirects=True, timeout=30)
    r.raise_for_status()  # raise if not 2xx
    return r.text  # decoded HTML as a Python string


def parse_pdf_links(html: str, base_url: str) -> List[Tuple[str, str]]:
    """
    Parse all <a href="*.pdf"> links from the HTML.
    Returns:
      List of (title, absolute_url)
    """
    soup = BeautifulSoup(html, "html.parser")
    links: List[Tuple[str, str]] = []

    # Find every <a> (hyperlink) that actually has an href attribute (leads somewhere).
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        # Keep only PDF links
        if not href.lower().endswith(".pdf"):
            continue
        # Human-friendly name from the link anchor text, fallback if blank
        title = (a.get_text(strip=True) or "MARP Document").strip()
        # Resolve relative URL to absolute URL using the base page URL
        #abs_url = httpx.URL(href, base=base_url).human_repr()
        abs_url = str(httpx.URL(base_url).join(href))

        links.append((title, abs_url))
    return links


async def download_pdf(client: httpx.AsyncClient, url: str, dest_path: str) -> None:
    """
    Stream the PDF from 'url' and write it to 'dest_path' in small chunks.
    Streaming beacuse it:
      - Avoids loading the whole file in memory.
      - Plays nicely with async: we 'await' between chunks, letting other tasks run.
    """
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    # Start an HTTP request in streaming mode (iterate over bytes as they arrive)
    async with client.stream("GET", url, follow_redirects=True, timeout=60) as r:
        r.raise_for_status()  # fail early if not 2xx
        # Open a local file in binary write mode
        with open(dest_path, "wb") as f:
            # For each arriving chunk, write to disk immediately
            async for chunk in r.aiter_bytes():
                f.write(chunk)


def count_pages(pdf_path: str) -> int:
    """
    Return the number of pages in the PDF at pdf_path.
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            return len(pdf.pages)
    except Exception:
        return 0


async def discover_and_download() -> AsyncIterator[Dict]:
    """
    Orchestrate the discovery flow and yield one metadata dict per document.

    Flow:
      1) Ensure /data/pdfs exists.
      2) Fetch landing page HTML.
      3) Parse all PDF links on that page (we now "know all documents").
      4) For each link, derive a stable document ID and output path.
      5) If file missing, stream-download it.
      6) Count pages.
      7) Yield a self-contained metadata dict for events and catalog.

    The ingestion service can publish one event as soon as each document is ready,
    without waiting for the entire page's set to finish.
    """
    data_root = settings.data_root
    pdf_dir = os.path.join(data_root, "pdfs")
    os.makedirs(pdf_dir, exist_ok=True)

    # Reuse a single HTTP client for efficiency (connection pooling).
    async with httpx.AsyncClient() as client:
        # Phase 1: discover all links
        html = await fetch_html(client, MARP_SOURCE_URL)
        links = parse_pdf_links(html, MARP_SOURCE_URL)

        # Phase 2: process each PDF sequentially
        for title, url in links:
            doc_id = _doc_id_from_url(url)
            pdf_path = os.path.join(pdf_dir, f"{doc_id}.pdf")

            # Download PDF if the file doesn't already exist
            if not os.path.exists(pdf_path):
                await download_pdf(client, url, pdf_path)

            # Page count for metadata/monitoring
            pages = count_pages(pdf_path)

            # Yield a self-contained dict — everything Extraction needs to start
            yield {
                "documentId": doc_id,
                "title": title,
                "url": url,
                "downloadPath": pdf_path,
                "pages": pages,
                "discoveredAt": now_iso(),  # when THIS doc finished discovery work
            }