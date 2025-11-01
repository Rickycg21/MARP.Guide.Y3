"""
What this file is for:
- FastAPI app + RabbitMQ consumer for the Extraction service.
- Consume DocumentDiscovered events from RabbitMQ
- Extract PDF pages to JSONL under /data/text/{document_id}.jsonl
- Publish DocumentExtracted events (events.md schema)
- Append per-document metadata to /data/text_metadata.jsonl
- Update counters in /data/metrics/counters.json
- Expose /health, /metrics, /status/{id}, /extract/{id}
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import aio_pika
from aio_pika import ExchangeType, DeliveryMode
from fastapi import FastAPI, HTTPException

from common.config import settings
import common.events as ev

from .models import (
    ExtractAccepted,
    StatusResponse,
    DocumentDiscoveredEnvelope,
    DocumentExtractedEvent,
)
from .extractor import (
    PDF_DIR, TEXT_DIR, METRICS_DIR,
    load_counters, bump_counters,
    estimate_tokens_from_chars, jsonl_stats,
    coalesce_pdf_path, extract_pdf_to_jsonl,
    build_extracted_event, append_metadata_line,
)

# ---------- Routing Keys ----------
ROUTING_IN = getattr(
    ev, "ROUTING_DOCUMENT_DISCOVERED",
    getattr(ev, "ROUTING_DISCOVERED",
            getattr(ev, "ROUTING_FETCHED", "document.discovered"))
)
ROUTING_OUT = getattr(
    ev, "ROUTING_DOCUMENT_EXTRACTED",
    getattr(ev, "ROUTING_EXTRACTED", "document.extracted")
)

# ---------- FastAPI app ----------
app = FastAPI(title="Extraction Service", version="0.3.0")

@app.get("/health")
def health():
    return {"status": "ok", "service": settings.service_name}

@app.get("/metrics")
def metrics():
    return load_counters()

# ---------- RabbitMQ state ----------
class MQ:
    conn: Optional[aio_pika.RobustConnection] = None
    ch: Optional[aio_pika.abc.AbstractChannel] = None
    ex: Optional[aio_pika.abc.AbstractExchange] = None
    q:  Optional[aio_pika.abc.AbstractQueue] = None

mq = MQ()

# ---------- Endpoints ----------
@app.post("/extract/{document_id}", response_model=ExtractAccepted, status_code=202)
async def trigger_extraction(document_id: str):
    """
    Manually trigger extraction by publishing the same event ingestion sends.
    """
    if mq.ex is None:
        raise HTTPException(status_code=503, detail="Message broker not ready, try again in a moment.")

    pdf_path = os.path.join(PDF_DIR, f"{document_id}.pdf")
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail=f"PDF not found at {PDF_DIR}/{document_id}.pdf")

    size_bytes = os.path.getsize(pdf_path)
    envelope = {
        "event_type": "DocumentDiscovered",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": str(uuid4()),
        "source_service": settings.service_name,
        "data": {
            "id": document_id,
            "title": "",
            "download_path": pdf_path,
            "size_bytes": size_bytes,
        },
    }

    # Validate the envelope before publishing (helps catch mistakes locally)
    DocumentDiscoveredEnvelope.model_validate(envelope)

    await mq.ex.publish(
        aio_pika.Message(
            body=json.dumps(envelope).encode("utf-8"),
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
        ),
        routing_key=ROUTING_IN,
    )
    return ExtractAccepted(accepted=True, documentId=document_id)

@app.get("/status/{document_id}", response_model=StatusResponse)
def get_status(document_id: str):
    """
    Best-effort status by checking for produced artifacts in /data/text.
    """
    jsonl_path = os.path.join(TEXT_DIR, f"{document_id}.jsonl")
    txt_path   = os.path.join(TEXT_DIR, f"{document_id}.txt")

    if os.path.exists(txt_path) or os.path.exists(jsonl_path):
        pages, chars = jsonl_stats(jsonl_path) if os.path.exists(jsonl_path) else (None, None)
        return StatusResponse(
            status="done",
            documentId=document_id,
            artifacts={
                "jsonl": jsonl_path if os.path.exists(jsonl_path) else None,
                "txt":   txt_path   if os.path.exists(txt_path)   else None,
            },
            pageCount=pages,
            charCount=chars,
        )
    return StatusResponse(status="pending", documentId=document_id, artifacts={"jsonl": None, "txt": None})

# ---------- Startup / Shutdown ----------
@app.on_event("startup")
async def on_startup():
    mq.conn = await aio_pika.connect_robust(settings.rabbitmq_url)
    mq.ch = await mq.conn.channel()
    await mq.ch.set_qos(prefetch_count=8)

    exchange_name = getattr(settings, "event_exchange", "events")
    mq.ex = await mq.ch.declare_exchange(exchange_name, ExchangeType.TOPIC, durable=True)

    queue_name = getattr(settings, "queue_name", "extraction.document_discovered")
    mq.q = await mq.ch.declare_queue(queue_name, durable=True)

    await mq.q.bind(mq.ex, ROUTING_IN)
    await mq.q.consume(handle_document_discovered, no_ack=False)

@app.on_event("shutdown")
async def on_shutdown():
    try:
        if mq.ch:
            await mq.ch.close()
        if mq.conn:
            await mq.conn.close()
    except Exception:
        pass

# ---------- Consumer ----------
async def handle_document_discovered(msg: aio_pika.IncomingMessage):
    bump_counters(events_consumed=1)
    async with msg.process(requeue=True):
        try:
            # Validate inbound envelope using Pydantic
            envelope = DocumentDiscoveredEnvelope.model_validate_json(msg.body.decode("utf-8"))
            data = envelope.data

            doc_id   = data.id
            title    = data.title or ""
            pdf_path = coalesce_pdf_path(data.model_dump())

            if not pdf_path:
                raise ValueError("Missing document path (expected 'download_path' in event.data)")

            out_path = os.path.join(TEXT_DIR, f"{doc_id}.jsonl")
            os.makedirs(TEXT_DIR, exist_ok=True)

            # If file exists don't re-extract but still publish the event
            if os.path.exists(out_path):
                page_count, total_chars = jsonl_stats(out_path)
                evt = build_extracted_event(
                    doc_id=doc_id,
                    title=title,
                    text_path=out_path,
                    page_count=page_count if page_count > 0 else None,
                    token_count=estimate_tokens_from_chars(total_chars) if total_chars > 0 else None,
                    correlation_id=envelope.correlation_id,
                )
                evt.eventId = str(uuid4())

                await mq.ex.publish(
                    aio_pika.Message(
                        body=evt.model_dump_json(by_alias=False).encode("utf-8"),
                        delivery_mode=DeliveryMode.PERSISTENT,
                        content_type="application/json",
                    ),
                    routing_key=ROUTING_OUT,
                )
                return

            # Fresh extraction
            stats = extract_pdf_to_jsonl(pdf_path, out_path)

            evt = build_extracted_event(
                doc_id=doc_id,
                title=title,
                text_path=out_path,
                page_count=stats["page_count"],
                token_count=estimate_tokens_from_chars(stats["chars_out"]),
                correlation_id=envelope.correlation_id,
            )

            evt.eventId = str(uuid4())

            append_metadata_line(evt)

            await mq.ex.publish(
                aio_pika.Message(
                    body=evt.model_dump_json(by_alias=False).encode("utf-8"),
                    delivery_mode=DeliveryMode.PERSISTENT,
                    content_type="application/json",
                ),
                routing_key=ROUTING_OUT,
            )
            bump_counters(docs_extracted=1)

        except Exception:
            bump_counters(errors=1)
            raise