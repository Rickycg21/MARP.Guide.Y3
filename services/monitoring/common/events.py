import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from common.config import settings

# Dedicated logger for this module; inherits level/format from root (configured in config.py)
logger = logging.getLogger("events")

# =============================================================================
# 1) Event Envelope
# =============================================================================
@dataclass
class EventEnvelope:
    """
    The standard event envelope used across all services.
    """
    eventType: str
    eventId: str
    timestamp: str
    correlationId: Optional[str]
    source: str
    version: str
    payload: Dict[str, Any]


def now_iso() -> str:
    """
    Return a timezone-aware ISO-8601 UTC timestamp string, e.g.:
    "2025-10-26T20:15:23.742123+00:00"
    """
    return datetime.now(tz=timezone.utc).isoformat()


def new_event(
    event_type: str,
    payload: Dict[str, Any],
    correlation_id: str,
    *,
    version: str = "1.0",
    source: Optional[str] = None,
) -> EventEnvelope:
    """
    Factory to build an EventEnvelope.
    Parameters before '*' are positional.
    Parameters after '*' must be passed by name.
    """
    return EventEnvelope(
        eventType=event_type,
        eventId=str(uuid.uuid4()),
        timestamp=now_iso(),
        correlationId=correlation_id,
        source=source or settings.service_name, # default to current service
        version=version,
        payload=payload,
    )

# =============================================================================
# 2) AMQP (RabbitMQ) connection/channel management
# =============================================================================
# A single robust connection and channel is maintained per process.
# asyncio.Lock is used to ensure only one coroutine initialises the connection
# concurrently. Everyone else reuses the same channel afterwards.
_amqp_lock = asyncio.Lock()
_amqp_connection: Optional[aio_pika.RobustConnection] = None
_amqp_channel: Optional[aio_pika.abc.AbstractChannel] = None

async def _ensure_channel() -> aio_pika.abc.AbstractChannel:
    """
    Create or reuse a single robust connection + channel.

    - 'await' is used because connecting/opening channels is network I/O.
      While waiting, the event loop can run other tasks (no blocking).
    - RobustConnection auto-reconnects if the broker restarts.
    """
    global _amqp_connection, _amqp_channel

    # Only one coroutine should connect at a time.
    async with _amqp_lock:
        # Fast path: if both connection and channel are alive, reuse them.
        if _amqp_connection and not _amqp_connection.is_closed:
            if _amqp_channel and not _amqp_channel.is_closed:
                return _amqp_channel

        # Slow path: connect to RabbitMQ
        logger.info("Connecting to RabbitMQ at %s", settings.rabbitmq_url)
        _amqp_connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        _amqp_channel = await _amqp_connection.channel()

        return _amqp_channel

# =============================================================================
# 3) Publishing
# =============================================================================
async def publish_event(event: EventEnvelope) -> None:
    """
    Serialise an EventEnvelope to JSON and publish it to a durable queue named
    exactly after its eventType.

    Reliability:
      - Durable queue + persistent messages -> survive broker restarts
      - At-least-once delivery (consumers must ack; handlers should be idempotent)
    """
    channel = await _ensure_channel()  # may connect; non-blocking for others

    # declare_queue is idempotent: 
    # if the queue already exists , nothing happens; if not, it’s created.
    queue = await channel.declare_queue(event.eventType, durable=True)

    # Convert dataclass -> dict -> JSON string -> UTF-8 bytes.
    body = json.dumps(asdict(event), ensure_ascii=False).encode("utf-8")

    # Build the AMQP message with metadata for traceability and durability.
    # - delivery_mode=PERSISTENT asks RabbitMQ to store the message on disk.
    # - message_id, timestamp, correlation_id, and headers help with debugging,
    #   monitoring, and cross-service tracing.
    message = aio_pika.Message(
        body=body,
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        message_id=event.eventId,
        timestamp=datetime.fromisoformat(event.timestamp.replace("Z", "+00:00")),
        correlation_id=event.correlationId,
        headers={"eventType": event.eventType, "version": event.version},
    )

    # Publish via the default exchange ("") which routes by exact queue name:
    # routing_key == queue.name -> deliver directly to that queue.
    await channel.default_exchange.publish(message, routing_key=queue.name)

    logger.info("Published %s id=%s corr=%s", event.eventType, event.eventId, event.correlationId)

# =============================================================================
# 4) Consuming
# =============================================================================
# A handler is an ASYNC function implemented per event type. It receives:
#   - envelope: the decoded EventEnvelope (Python object)
#   - message:  the raw AMQP message
# It must return an awaitable (i.e., be defined with `async def`).
Handler = Callable[[EventEnvelope, AbstractIncomingMessage], Awaitable[None]]


async def consume(event_type: str, handler: Handler) -> None:
    """
    Subscribe to a queue for the given event_type and process messages forever.

    The handler is responsible for deciding when to ack()/nack():
      - await message.ack()            -> success, delete from queue
      - await message.nack(True)       -> failure, requeue

    Safety net:
      If the handler raises an exception (bug/unhandled error), it is caught here
      and nack(requeue=True) so the message isn't lost.
    """
    channel = await _ensure_channel()
    queue = await channel.declare_queue(event_type, durable=True)

    # Create an async iterator over incoming messages. This loop yields one
    # message at a time as RabbitMQ delivers them. While awaiting (e.g., waiting
    # for the next message or for handler I/O), the event loop can run other
    # tasks (e.g., HTTP requests, other consumers).
    async with queue.iterator() as qiter:
        async for message in qiter:
            try:
                envelope = _decode_envelope(message)
                await handler(envelope, message)
            except Exception as e:
                logger.exception("Handler error for %s: %s — nacking", event_type, e)
                await message.nack(requeue=True)

# =============================================================================
# 5) Decoding helper
# =============================================================================
def _decode_envelope(message: AbstractIncomingMessage) -> EventEnvelope:
    """
    Reverse of publish-time serialisation:
    bytes (UTF-8 JSON) -> str -> dict -> EventEnvelope dataclass
    """
    data = json.loads(message.body.decode("utf-8"))
    return EventEnvelope(**data)


# =============================================================================
# 6) Example usage
# =============================================================================
# In a producer (e.g., Ingestion service):
#
#   from common.events import new_event, publish_event
#
#   payload = {"documentId": "doc_123", "downloadPath": "/data/pdfs/doc_123.pdf"}
#   evt = new_event("DocumentDiscovered", payload, correlation_id="job-abc-123")
#   await publish_event(evt)
#
# In a consumer (e.g., Extraction service):
#
#   from common.events import consume, EventEnvelope
#   from aio_pika.abc import AbstractIncomingMessage
#
#   async def handle_document_discovered(env: EventEnvelope, msg: AbstractIncomingMessage):
#       try:
#            ... extraction logic using env.payload ...
#           await msg.ack()  # success: tell RabbitMQ to delete the message
#       except Error:
#           await msg.nack(requeue=True)   # retry later
#
#   @app.on_event("startup")
#   async def startup():
#       asyncio.create_task(consume("DocumentDiscovered", handle_document_discovered))
