from datetime import datetime, timezone
import uuid

ROUTING_FETCHED   = "doc.fetched"
ROUTING_EXTRACTED = "doc.extracted"

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def new_event(event_type: str, payload: dict, *, source: str, correlation_id: str | None = None) -> dict:
    return {
        "eventType": event_type,
        "eventId": str(uuid.uuid4()),
        "timestamp": now_iso(),
        "correlationId": correlation_id,
        "source": source,
        "version": "1.0",
        "payload": payload,
    }

