"""
FastAPI app for the extraction service.

Responsibilities:
- Expose health and simple monitoring endpoints (/health, /status).
- Provide a manual trigger for extraction: POST /extract/{document_id}.
- Consume DocumentDiscovered events, run extraction, and publish DocumentExtracted.
"""

import os
import json
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict

from fastapi import FastAPI, HTTPException
from aio_pika.abc import AbstractIncomingMessage

from common.config import settings
from common.events import consume, new_event, publish_event, EventEnvelope
from .models import ExtractStatus, ExtractResponse, StatusList, TextRecord
from .extractor import extract_to_text

app = FastAPI(title="Extraction Service")
logger = logging.getLogger("extraction")

STATUS_PATH = os.path.join(settings.data_root, "text_status.jsonl")
META_PATH   = os.path.join(settings.data_root, "text_metadata.jsonl")

# -----------------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------------
@app.get("/health")
def health():
    """
    Lightweight readiness endpoint. Cheap and reliable for Docker health checks.
    """
    return {"status": "ok", "service": settings.service_name}

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _append_jsonl(path: str, obj: Dict) -> None:
    """
    Append one JSON object as a line to 'path'.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def _status_upsert(document_id: str, status: str, message: str = "") -> None:
    """
    Record one status line. LAST line for a document_id is the current status.
    """
    _append_jsonl(STATUS_PATH, {"document_id": document_id, "status": status, "message": message})

def now_iso() -> str:
    """Return current time in ISO-8601 with UTC timezone, e.g., 2025-10-29T19:45:12.123456+00:00"""
    return datetime.now(tz=timezone.utc).isoformat()

# -----------------------------------------------------------------------------
# Manual trigger API endpoint for extracting text from a document
# -----------------------------------------------------------------------------
@app.post("/extract/{document_id}", response_model=ExtractResponse, status_code=202)
async def extract(document_id: str):
    """
    Manual extraction trigger for develepment and demonstration.
    Returns HTTP 202 immediately, actual work runs in a background task.

    Correlation ID:
      - Manual triggers use a fresh UUIDv4 so monitoring can trace this run
        across services (Extraction → Indexing ...).
    """
    correlation_id = str(uuid.uuid4())
    asyncio.create_task(_do_extract(document_id, correlation_id=correlation_id))
    _status_upsert(document_id, "pending", "manual trigger accepted")
    return ExtractResponse()

# -----------------------------------------------------------------------------
# Status API endpoints
# -----------------------------------------------------------------------------
@app.get("/status/{document_id}", response_model=ExtractStatus)
def status(document_id: str):
    """
    Scan the append-only file & return the latest status for a specific document_id.
    """
    last = {"document_id": document_id, "status": "unknown"}
    if os.path.exists(STATUS_PATH):
        with open(STATUS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec.get("document_id") == document_id:
                    last = rec
    return ExtractStatus(**last)

@app.get("/status", response_model=StatusList)
def status_all():
    """
    Return the full status timeline (all lines) for simple audit/debugging.
    """
    status_history = []
    if os.path.exists(STATUS_PATH):
        with open(STATUS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                status_history.append(ExtractStatus(**json.loads(line)))
    return StatusList(status_history=status_history)

# -----------------------------------------------------------------------------
# Worker: actual extraction + metadata + event publish
# -----------------------------------------------------------------------------
async def _do_extract(document_id: str, correlation_id: str):
    """
    Performs the extraction workflow:
      1) Convert PDF -> text (extractor.py)
      2) Fetch title & URL from ingestion
      3) Append metadata JSONL (TextRecord)
      4) Write final "done" status
      5) Publish DocumentExtracted (for Indexing)

    On any exception:
      - Logs stacktrace
      - Writes "error" status (with message)
    """
    try:
        # 1) PDF -> text
        text_path, page_count, token_count = extract_to_text(document_id)

        # 2) Look up title & url from ingestion metadata if available
        ingestion_meta_path = os.path.join(settings.data_root, "pdf_metadata.jsonl")
        title = "Unknown Title"
        url = None
        if os.path.exists(ingestion_meta_path):
            with open(ingestion_meta_path, "r", encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    if rec.get("document_id") == document_id:
                        title = rec.get("title", title)
                        url = rec.get("url", url)
                        break

        # 3) Record metadata
        record = TextRecord(
            document_id=document_id,
            title= title,
            url= url,
            text_path=text_path,
            page_count=page_count,
            token_count=token_count,
            extracted_by= "pdfplumber",
            extracted_at= now_iso()
        )

        meta = record.model_dump(mode="json")
        _append_jsonl(META_PATH, meta)

        # 4) Record status
        _status_upsert(document_id, "done", "extraction completed")

        # 5) Publish DocumentExtracted
        evt = new_event(
            "DocumentExtracted",
            payload={
                "documentId": document_id,
                "title": title,
                "url": url,
                "textPath": text_path,
                "pageCount": page_count,
                "tokenCount": token_count,
                "extractedBy": "pdfplumber",
                "extractedAt": now_iso()
            },
            correlation_id=correlation_id, # inherited(event) or UUIDv4(manual)
        )
        await publish_event(evt)
        logger.info("Published DocumentExtracted for %s", document_id)

    except Exception as e:
        logger.exception("Extraction failed for %s", document_id)
        _status_upsert(document_id, "error", str(e))

# -----------------------------------------------------------------------------
# Event consumer: handle DocumentDiscovered and run extraction
# -----------------------------------------------------------------------------
async def handle_document_discovered(env: EventEnvelope, msg: AbstractIncomingMessage):
    """
    Consume one DocumentDiscovered event and run extraction.
    """
    try:
        payload = env.payload
        document_id = payload["documentId"]
        _status_upsert(document_id, "pending", "event accepted")
        await _do_extract(document_id, correlation_id=env.correlationId)
        await msg.ack() # success
    except Exception as e:
        logger.exception("Handler error for DocumentDiscovered")
        await msg.nack(requeue=True) # retry later

# -----------------------------------------------------------------------------
# Startup hook: begin consuming events in background
# -----------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    """
    Start the event consumer without blocking the HTTP server.
    """
    asyncio.create_task(consume("DocumentDiscovered", handle_document_discovered))