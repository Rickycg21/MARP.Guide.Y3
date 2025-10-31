"""
FastAPI app for the ingestion service.

Responsibilities:
- Expose health and simple browsing endpoints (/health, /documents).
- On POST /discover:
    * Crawl the MARP page via crawler.py
    * Ensure local catalog (JSONL) is updated (append-only)
    * Publish one DocumentDiscovered event PER document with a correlation ID
"""

import asyncio
import json
import os
import logging
import uuid
from typing import List

from fastapi import FastAPI

from common.config import settings
from common.events import new_event, publish_event
from .crawler import discover_and_download
from .models import DiscoverResponse, DocumentRecord, DocumentsList

app = FastAPI(title="Ingestion Service")
logger = logging.getLogger("ingestion")

# Append-only catalog for discovered PDFs.
CATALOG_PATH = os.path.join(settings.data_root, "pdf_metadata.jsonl")

@app.get("/health")
def health():
    """
    Lightweight readiness endpoint.
    Cheap (no external calls) so Docker health checks are reliable.
    """
    return {"status": "ok", "service": settings.service_name}

def _append_catalog(record: DocumentRecord) -> None:
    """
    Append one DocumentRecord JSON line to the catalog file.
    """
    os.makedirs(os.path.dirname(CATALOG_PATH), exist_ok=True)
    with open(CATALOG_PATH, "a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")

def _load_catalog() -> List[DocumentRecord]:
    """
    Load the entire catalog file into memory.
    """
    if not os.path.exists(CATALOG_PATH):
        return []
    docs: List[DocumentRecord] = []
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            # Parse JSON string into a DocumentRecord with validation
            # of data types against the Pydantic model
            docs.append(DocumentRecord.model_validate_json(line))
    return docs

@app.get("/documents", response_model=DocumentsList)
def documents():
    """
    Return the current catalog to see what has been discovered.
    """
    return DocumentsList(documents=_load_catalog())

@app.post("/discover", response_model=DiscoverResponse, status_code=202)
async def discover():
    """
    Kick off discovery for the MARP landing page and publish events.

    HTTP 202 Accepted because:
      - The request triggers asynchronous downstream work (via events).
      - 202 communicates "accepted for processing", which matches EDA semantics.

    For each discovered PDF:
      - ensure we have a catalog record (dedupe by document_id)
      - publish a DocumentDiscovered event with a correlationId
    """
    # Correlation ID helps Monitoring trace related events across services
    job_id = f"job:{uuid.uuid4()}"
    discovered_count = 0

    # The crawler yields one metadata dict per document as it finishes processing it.
    async for meta in discover_and_download():
        record = DocumentRecord(
            document_id=meta["documentId"],
            title=meta["title"],
            url=meta["url"],
            download_path=meta["downloadPath"],
            pages=meta["pages"],
            discovered_at=meta["discoveredAt"],
        )

        # Idempotency: don't duplicate catalog entries across reruns
        already = any(d.document_id == record.document_id for d in _load_catalog())
        if not already:
            _append_catalog(record)

        # Create the event envelope and publish it to RabbitMQ
        evt = new_event(
            "DocumentDiscovered",
            payload={
                "documentId": record.document_id,
                "title": record.title,
                "url": str(record.url),
                "downloadPath": record.download_path,
                "pages": record.pages,
                "discoveredAt": record.discovered_at,
            },
            correlation_id=job_id,
        )
        await publish_event(evt)
        discovered_count += 1
        logger.info("Published DocumentDiscovered id=%s url=%s", record.document_id, record.url)

    return DiscoverResponse(discovered_count=discovered_count)