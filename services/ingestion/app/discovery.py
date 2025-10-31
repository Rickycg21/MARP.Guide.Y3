import httpx, hashlib, os
from bs4 import BeautifulSoup
from datetime import datetime
from .models import Document

BASE_URL = os.getenv("BASE_URL")

def _id_for(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]

async def discover_pdfs():
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(BASE_URL)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        links = []
        for a in soup.find_all("a"):
            href = (a.get("href") or "").strip()
            if href.lower().endswith(".pdf"):
                title = (a.text or "Untitled PDF").strip()
                if not href.startswith("http"):
                    # handle relative links
                    href = httpx.URL(BASE_URL).join(href)
                doc = Document(
                    id=_id_for(str(href)),
                    title=title,
                    url=str(href),
                    discovered_at=datetime.utcnow(),
                )
                links.append(doc)
        return links
