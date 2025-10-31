import os, httpx, io, asyncio
from fastapi import FastAPI, BackgroundTasks, HTTPException
from datetime import datetime, timezone
from typing import Dict, List
from .models import Document
from .discovery import discover_pdfs
from .storage import save_bytes
from .rabbit import publish_event
from .events import ROUTING_READY
from pypdf import PdfReader
from dataclasses import asdict
from common.events import new_event

app = FastAPI(title="Ingestion Service", version="0.1.0")

# naive in-memory store (swap to DB later)
CATALOG: Dict[str, Document] = {}

@app.get("/health")
def health():
    return {"status": "ok"}
'''
@app.post("/documents/discover", status_code=202)
async def discover_route(bg: BackgroundTasks):
    async def job():
        docs = await discover_pdfs()
        for d in docs:
            CATALOG[d.id] = Document(**d.model_dump())

    bg.add_task(job)
    return {"status": "accepted", "message": "Discovery started"}
'''
@app.get("/documents", response_model=List[Document])
def list_documents():
    return list(CATALOG.values())

@app.get("/documents/{doc_id}", response_model=Document)
def get_document(doc_id: str):
    doc = CATALOG.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return doc

@app.post("/documents/{doc_id}/fetch")
async def fetch_document(doc_id: str):
    doc = CATALOG.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(str(doc.url))
        r.raise_for_status()
        filename = str(doc.url).split("/")[-1] or f"{doc_id}.pdf"
        stored_path, size = save_bytes(doc_id, filename, r.content)

        # Try to compute page count if content is a valid PDF
        page_count = None
        try:
            reader = PdfReader(io.BytesIO(r.content))
            # Some PDFs may not expose pages cleanly until accessed
            page_count = len(reader.pages)
        except Exception:
            # Leave page_count as None if parsing fails
            pass

    doc.stored_path = stored_path
    doc.size_bytes = size
    doc.fetched_at = datetime.utcnow()
    doc.page_count = page_count
    CATALOG[doc_id] = doc

    payload = {
        "documentId": doc.id,
        "title": doc.title,
        "url": str(doc.url),
        "downloadPath": stored_path,
        "pages": page_count,
        "discoveredAt": (doc.discovered_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")
                          if doc.discovered_at.tzinfo else doc.discovered_at.replace(microsecond=0).isoformat() + "Z"),
        "fileSize": size,
    }
    envelope = new_event(
        "DocumentReady",
        payload,
        correlation_id=doc.id,
        source=os.getenv("SERVICE_NAME", "ingestion-service"),
    )
    publish_event(ROUTING_READY, asdict(envelope))

    return {"status": "ok", "id": doc_id, "stored_path": stored_path}


def _iso_z(dt: datetime) -> str:
    # Normalize to ISO8601 with trailing 'Z' and no microseconds
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

 

async def _fetch_and_store(client: httpx.AsyncClient, d) -> Document:
    r = await client.get(str(d.url))
    r.raise_for_status()
    filename = str(d.url).split("/")[-1] or f"{d.id}.pdf"
    stored_path, size = save_bytes(d.id, filename, r.content)

    page_count = None
    try:
        reader = PdfReader(io.BytesIO(r.content))
        page_count = len(reader.pages)
    except Exception:
        pass

    doc = Document(
        id=d.id,
        title=d.title,
        url=d.url,
        discovered_at=d.discovered_at,
        fetched_at=datetime.utcnow(),
        stored_path=stored_path,
        size_bytes=size,
        page_count=page_count,
    )
    CATALOG[d.id] = doc

    # Publish DocumentReady using the common envelope builder
    payload = {
        "documentId": doc.id,
        "title": doc.title,
        "url": str(doc.url),
        "downloadPath": doc.stored_path,
        "pages": doc.page_count,
        "discoveredAt": (doc.discovered_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")
                          if doc.discovered_at.tzinfo else doc.discovered_at.replace(microsecond=0).isoformat() + "Z"),
        "fileSize": doc.size_bytes,
    }
    envelope = new_event(
        "DocumentReady",
        payload,
        correlation_id=doc.id,
        source=os.getenv("SERVICE_NAME", "ingestion-service"),
    )
    publish_event(ROUTING_READY, asdict(envelope))
    return doc


@app.post("/discover", status_code=202)
async def discover_and_fetch_route(bg: BackgroundTasks):
    async def job():
        docs = await discover_pdfs()
        async with httpx.AsyncClient(timeout=60) as client:
            await asyncio.gather(*[_fetch_and_store(client, d) for d in docs])

    bg.add_task(job)
    return {"status": "accepted", "message": "Discovery and fetching started"}
