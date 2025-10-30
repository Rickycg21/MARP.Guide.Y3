# services/extraction/main.py
import os, json
from typing import Optional
from datetime import datetime, timezone

import aio_pika
from aio_pika import ExchangeType, DeliveryMode
from fastapi import FastAPI
import pdfplumber


from config import settings
from events import ROUTING_FETCHED, ROUTING_EXTRACTED, new_event

app = FastAPI(title="Extraction Service", version="0.1.0")

COUNTERS_PATH = os.path.join(settings.metrics_dir, "counters.json")

def _load_counters():
    try:
        with open(COUNTERS_PATH, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"events_consumed": 0, "docs_extracted": 0, "errors": 0}

def _bump(**delta):
    data = _load_counters()
    for k, v in delta.items():
        data[k] = data.get(k, 0) + v
    os.makedirs(settings.metrics_dir, exist_ok=True)
    with open(COUNTERS_PATH, "w") as f:
        json.dump(data, f)

@app.get("/health")
def health():
    return {"status": "ok", "service": settings.service_name}

@app.get("/metrics")
def metrics():
    return _load_counters()

# --- RabbitMQ state (set on startup) ---
class MQ:
    conn: Optional[aio_pika.RobustConnection] = None
    ch: Optional[aio_pika.abc.AbstractChannel] = None
    ex: Optional[aio_pika.abc.AbstractExchange] = None
    q: Optional[aio_pika.abc.AbstractQueue] = None

mq = MQ()

@app.on_event("startup")
async def on_startup():
    mq.conn = await aio_pika.connect_robust(settings.rabbitmq_url)
    mq.ch = await mq.conn.channel()
    await mq.ch.set_qos(prefetch_count=8)
    mq.ex = await mq.ch.declare_exchange(settings.event_exchange, ExchangeType.TOPIC, durable=True)
    mq.q = await mq.ch.declare_queue(settings.queue_name, durable=True)
    await mq.q.bind(mq.ex, ROUTING_FETCHED)
    await mq.q.consume(handle_doc_fetched, no_ack=False)

@app.on_event("shutdown")
async def on_shutdown():
    try:
        if mq.ch: await mq.ch.close()
        if mq.conn: await mq.conn.close()
    except Exception:
        pass

# --- Core extraction ---
def _extract_pdf_to_jsonl(pdf_path: str, out_path: str) -> dict:
    page_count, chars_out = 0, 0
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

async def handle_doc_fetched(msg: aio_pika.IncomingMessage):
    _bump(events_consumed=1)
    async with msg.process(requeue=True):  # requeue on exception
        try:
            envelope = json.loads(msg.body.decode("utf-8"))
            payload = envelope.get("payload", {})
            corr = envelope.get("correlationId")

            doc_id   = payload["id"]
            title    = payload.get("title", "")
            pdf_path = payload["stored_path"]
            bytes_in = payload.get("size_bytes")

            # Output path
            out_path = os.path.join(settings.text_dir, f"{doc_id}.jsonl")

            # Idempotency, skip if already extracted
            if os.path.exists(out_path) and not settings.force_reextract:
                evt = new_event(
                    "DocumentExtracted",
                    {
                        "id": doc_id, "title": title, "text_path": out_path,
                        "page_count": None, "bytes_in": bytes_in,
                        "bytes_out": os.path.getsize(out_path),
                        "extracted_at": datetime.now(timezone.utc).isoformat(),
                        "skipped": True,
                    },
                    source=settings.service_name, correlation_id=corr
                )
                await mq.ex.publish(
                    aio_pika.Message(
                        body=json.dumps(evt).encode("utf-8"),
                        delivery_mode=DeliveryMode.PERSISTENT,
                        content_type="application/json",
                    ),
                    routing_key=ROUTING_EXTRACTED,
                )
                return

            # Extract
            stats = _extract_pdf_to_jsonl(pdf_path, out_path)

            # Publish doc.extracted
            evt = new_event(
                "DocumentExtracted",
                {
                    "id": doc_id, "title": title, "text_path": out_path,
                    "page_count": stats["page_count"], "bytes_in": bytes_in,
                    "bytes_out": stats["bytes_out"],
                    "extracted_at": datetime.now(timezone.utc).isoformat(),
                    "skipped": False,
                },
                source=settings.service_name, correlation_id=corr
            )
            await mq.ex.publish(
                aio_pika.Message(
                    body=json.dumps(evt).encode("utf-8"),
                    delivery_mode=DeliveryMode.PERSISTENT,
                    content_type="application/json",
                ),
                routing_key=ROUTING_EXTRACTED,
            )
            _bump(docs_extracted=1)

        except Exception:
            _bump(errors=1)
            raise  # triggers NACK+requeue via msg.process(requeue=True)
