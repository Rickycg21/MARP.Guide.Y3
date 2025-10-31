import os
import json
from typing import Optional
from datetime import datetime, timezone
from uuid import uuid4

import aio_pika
from aio_pika import ExchangeType, DeliveryMode
from fastapi import FastAPI
import pdfplumber

from common.config import settings
import common.events as ev

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

# ---------- directory fallbacks derived from DATA_ROOT ----------
_DATA_ROOT   = getattr(settings, "data_root", "/data")
_PDF_DIR     = getattr(settings, "pdf_dir",  os.path.join(_DATA_ROOT, "pdfs"))
_TEXT_DIR    = getattr(settings, "text_dir", os.path.join(_DATA_ROOT, "text"))
_METRICS_DIR = getattr(settings, "metrics_dir", os.path.join(_DATA_ROOT, "metrics"))

# ---------- FastAPI app + simple counters ----------
app = FastAPI(title="Extraction Service", version="0.2.0")

COUNTERS_PATH = os.path.join(_METRICS_DIR, "counters.json")
_DEFAULT_COUNTERS = {"events_consumed": 0, "docs_extracted": 0, "errors": 0}

def _load_counters():
    try:
        with open(COUNTERS_PATH, "r") as f:
            raw = f.read().strip()
            if not raw:
                return _DEFAULT_COUNTERS.copy()
            return json.loads(raw)
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return _DEFAULT_COUNTERS.copy()

def _bump(**delta):
    data = _load_counters()
    for k, v in delta.items():
        data[k] = data.get(k, 0) + v
    os.makedirs(_METRICS_DIR, exist_ok=True)
    tmp_path = COUNTERS_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp_path, COUNTERS_PATH)

@app.get("/health")
def health():
    return {"status": "ok", "service": settings.service_name}

@app.get("/metrics")
def metrics():
    return _load_counters()

# ---------- RabbitMQ state ----------
class MQ:
    conn: Optional[aio_pika.RobustConnection] = None
    ch: Optional[aio_pika.abc.AbstractChannel] = None
    ex: Optional[aio_pika.abc.AbstractExchange] = None
    q:  Optional[aio_pika.abc.AbstractQueue] = None

mq = MQ()

@app.on_event("startup")
async def on_startup():
    # Connect + topology
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

# ---------- helpers ----------
def _estimate_tokens_from_chars(n_chars: int) -> int:
    return max(1, round(n_chars / 4))

def _jsonl_stats(path: str) -> tuple[int, int]:
    """
    For JSONL format: {"page": int, "text": str, "chars": int}
    Returns (page_count, total_chars)
    """
    pages = 0
    total_chars = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                pages += 1
                try:
                    rec = json.loads(line)
                    total_chars += int(rec.get("chars", 0))
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    return pages, total_chars

def _build_extracted_event(
    *, doc_id: str, title: str, text_path: str, page_count: Optional[int],
    token_count: Optional[int], correlation_id: Optional[str]
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "eventType": "DocumentExtracted",
        "eventId": str(uuid4()),
        "timestamp": now,
        "correlationId": correlation_id,
        "source": settings.service_name,  
        "version": "1.0",
        "payload": {
            "documentId": doc_id,
            "textPath": text_path,
            "pageCount": page_count,
            "tokenCount": token_count,
            "metadata": {
                "title": title,
                "extractedBy": "pdfplumber",
                "extractedAt": now,
            },
        },
    }

def _extract_pdf_to_jsonl(pdf_path: str, out_path: str) -> dict:
    page_count, chars_out = 0, 0
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with pdfplumber.open(pdf_path) as pdf, open(out_path, "w", encoding="utf-8") as out:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            page_count += 1
            chars_out += len(text)
            out.write(json.dumps({"page": i, "text": text, "chars": len(text)}, ensure_ascii=False) + "\n")
    return {
        "page_count": page_count,
        "bytes_out": os.path.getsize(out_path),
        "chars_out": chars_out,
    }

def _coalesce_path(data: dict) -> str:
    """
    Accept canonical field name per spec, be tolerant to earlier names.
    Priority: download_path (spec) -> stored_path -> path
    """
    return data.get("download_path") or data.get("stored_path") or data.get("path") or ""

# ---------- consumer ----------
async def handle_document_discovered(msg: aio_pika.IncomingMessage):
    _bump(events_consumed=1)
    async with msg.process(requeue=True):
        try:
            envelope = json.loads(msg.body.decode("utf-8"))
            data     = envelope.get("data", {}) or {}
            corr     = envelope.get("correlation_id") or envelope.get("correlationId")

            doc_id   = data["id"]
            title    = data.get("title", "")
            pdf_path = _coalesce_path(data)
            bytes_in = data.get("size_bytes")

            if not pdf_path:
                raise ValueError("Missing document path (expected 'download_path' in event.data)")

            out_path = os.path.join(_TEXT_DIR, f"{doc_id}.jsonl")
            os.makedirs(_TEXT_DIR, exist_ok=True)

            # Idempotency: don't re-extract if output already exists
            if os.path.exists(out_path):
                page_count, total_chars = _jsonl_stats(out_path)
                evt = _build_extracted_event(
                    doc_id=doc_id,
                    title=title,
                    text_path=out_path,
                    page_count=page_count if page_count > 0 else None,
                    token_count=_estimate_tokens_from_chars(total_chars) if total_chars > 0 else None,
                    correlation_id=corr,
                )
                await mq.ex.publish(
                    aio_pika.Message(
                        body=json.dumps(evt).encode("utf-8"),
                        delivery_mode=DeliveryMode.PERSISTENT,
                        content_type="application/json",
                    ),
                    routing_key=ROUTING_OUT,
                )
                return

            # Fresh extraction
            stats = _extract_pdf_to_jsonl(pdf_path, out_path)

            # Publish DocumentExtracted (events.md schema)
            evt = _build_extracted_event(
                doc_id=doc_id,
                title=title,
                text_path=out_path,
                page_count=stats["page_count"],
                token_count=_estimate_tokens_from_chars(stats["chars_out"]),
                correlation_id=corr,
            )
            await mq.ex.publish(
                aio_pika.Message(
                    body=json.dumps(evt).encode("utf-8"),
                    delivery_mode=DeliveryMode.PERSISTENT,
                    content_type="application/json",
                ),
                routing_key=ROUTING_OUT,
            )
            _bump(docs_extracted=1)

        except Exception:
            _bump(errors=1)
            raise  # triggers NACK+requeue via msg.process(requeue=True)