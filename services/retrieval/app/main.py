# =============================================================================
# Purpose: FastAPI endpoints + event publishing + JSONL query logging.
# Notes:
#   - /search: standard retrieval endpoint
#   - /health: service health
#   - /dev/consumeChunksIndexed: DEV-only endpoint that simulates "indexer
#     emitted ChunksIndexed" → run retrieval → optionally publish RetrievalCompleted.
# =============================================================================

import os, uuid, json, time, logging, datetime as dt
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Query, HTTPException, Body
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.retriever import Retriever
from app.models import HealthResponse, SearchResponse, SearchResult, Scores
from common.config import settings

# -----------------------------------------------------------------------------
# Logging & globals
# -----------------------------------------------------------------------------
log = logging.getLogger(__name__)
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

PUBLISH_EVENTS = os.getenv("RETRIEVAL_PUBLISH_EVENTS", "false").lower() == "true"
EVENT_EXCHANGE = os.getenv("EVENT_EXCHANGE", "events")
SERVICE_NAME = os.getenv("SERVICE_NAME", "retrieval-service")
_publish = None

# -----------------------------------------------------------------------------
# Event publishing
# -----------------------------------------------------------------------------
async def publish_retrieval_completed(
    correlation_id: Optional[str],
    query_id: str,
    query_text: str,
    mode: str,
    top_k: int,
    duration_ms: int,
    results: List[dict],
) -> None:
    if not PUBLISH_EVENTS:
        return

    global _publish
    try:
        if _publish is None:
            from common import events as ev
            _publish = getattr(ev, "publish_event_async", None) or getattr(ev, "publish_event", None)
        if _publish is None:
            log.warning("No publish function found; skipping event.")
            return

        # Compute top score if present
        top_score = None
        for r in results or []:
            s = (r.get("scores") or {}).get("combined")
            if s is not None:
                top_score = s if top_score is None else max(top_score, s)

        # Map results to the required minimal shape
        payload_results = []
        for r in results or []:
            payload_results.append({
                "docId": r.get("document_id"),
                "page": r.get("page"),
                "title": r.get("title"),
                "score": (r.get("scores") or {}).get("combined"),
            })

        envelope = {
            "eventType": "RetrievalCompleted",
            "eventId": str(uuid.uuid4()),
            "timestamp": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "correlationId": correlation_id or str(uuid.uuid4()),
            "source": SERVICE_NAME,
            "version": "1.0",
            "payload": {
                "queryId": query_id,
                "query": query_text,
                "resultsCount": len(payload_results),
                "topScore": top_score,
                "latencyMs": int(duration_ms or 0),
                "results": payload_results,
            },
        }

        maybe = _publish(envelope, exchange=EVENT_EXCHANGE)
        if hasattr(maybe, "__await__"):  # support async or sync publisher
            await maybe

    except Exception as e:
        log.exception("publish failed: %s", e)

# -----------------------------------------------------------------------------
# App setup
# -----------------------------------------------------------------------------
app = FastAPI(title="retrieval-service", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

retriever: Optional[Retriever] = None

@app.on_event("startup")
async def startup():
    """Create the Retriever using env defaults."""
    global retriever
    retriever = Retriever()

# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@app.get("/health")
async def health() -> JSONResponse:
    """Service health summary (Chroma + embedder)."""
    assert retriever
    h = await retriever.health()
    return JSONResponse(HealthResponse(
        status=h.get("status","down"),
        chroma_dir=h.get("chromaDir"),
        embedding=h.get("embedding", {"reachable": False, "model": None})
    ).model_dump(by_alias=True))

@app.get("/search")
async def search(
    q: str = Query(..., min_length=1, description="User query text"),
    topK: int = Query(5, ge=1, le=int(os.getenv("MAX_TOPK", "50")), description="Number of results"),
    mode: str = Query("semantic", pattern="^(semantic|bm25|hybrid)$"),
    documentId: Optional[str] = Query(None, description="Restrict to a single document"),
    correlationId: Optional[str] = Query(None, description="Trace id for events/logs"),
) -> JSONResponse:
    """Run retrieval and return normalized results. Optionally publish an event."""
    assert retriever
    try:
        rows, stats = await retriever.search(q=q, top_k=topK, mode=mode, document_id=documentId)
    except ValueError as ve:
        raise HTTPException(400, str(ve))
    except Exception as e:
        log.exception("search failed: %s", e)
        raise HTTPException(500, "Search failed")

    # Shape rows → response models
    results = [SearchResult(
        document_id=r.get("document_id","unknown"),
        chunk_id=r.get("chunk_id",""),
        page=r.get("page"),
        title=r.get("title"),
        url=r.get("url"),
        snippet=r.get("snippet"),
        scores=Scores(**(r.get("scores") or {})),
    ) for r in rows]

    query_id = str(uuid.uuid4())
    resp = SearchResponse(
        query_id=query_id, query=q, top_k=topK, mode=mode,
        duration_ms=int((stats or {}).get("duration_ms", 0)),
        results=results,
    )

    await publish_retrieval_completed(
        correlation_id=correlationId, query_id=query_id, query_text=q,
        mode=mode, top_k=topK, duration_ms=int((stats or {}).get("duration_ms", 0)), results=rows
    )
    _log_query_jsonl(query_id, q, mode, topK, results, correlationId, source="http")

    return JSONResponse(resp.model_dump(by_alias=True))

# ---- ChunksIndexed manual trigger -----------------------------
# Simulates indexer → ChunksIndexed event: runs retrieval and (optionally) publishes.
@app.post("/dev/consumeChunksIndexed")
async def dev_consume_chunks_indexed(event: Dict[str, Any] = Body(...)) -> JSONResponse:
    """DEV-only entrypoint to mimic the event-driven path locally."""
    assert retriever
    payload = (event or {}).get("payload") or {}
    q = payload.get("query")
    if not q:
        raise HTTPException(400, "payload.query is required")

    rows, stats = await retriever.search(
        q=q,
        top_k=int(payload.get("topK", 5)),
        mode=payload.get("mode", "semantic"),
        document_id=payload.get("documentId"),
    )

    results = [SearchResult(
        document_id=r.get("document_id","unknown"),
        chunk_id=r.get("chunk_id",""),
        page=r.get("page"),
        title=r.get("title"),
        url=r.get("url"),
        snippet=r.get("snippet"),
        scores=Scores(**(r.get("scores") or {})),
    ) for r in rows]

    query_id = str(uuid.uuid4())
    resp = SearchResponse(
        query_id=query_id, query=q,
        top_k=int(payload.get("topK",5)),
        mode=payload.get("mode","semantic"), 
        duration_ms=int((stats or {}).get("duration_ms", 0)),
        results=results,
    )

    await publish_retrieval_completed(
        correlation_id=(event or {}).get("correlationId"),
        query_id=query_id, query_text=q,
        mode=payload.get("mode","semantic"),
        top_k=int(payload.get("topK",5)),
        duration_ms=int((stats or {}).get("duration_ms", 0)),
        results=rows,
    )
    _log_query_jsonl(query_id, q, payload.get("mode","semantic"),
                     int(payload.get("topK",5)), results, (event or {}).get("correlationId"),
                     source="ChunksIndexed")
    return JSONResponse(resp.model_dump(by_alias=True))

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _log_query_jsonl(
    query_id: str, q: str, mode: str, top_k: int,
    results: List[SearchResult], correlation_id: Optional[str],
    source: str = "http"
) -> None:
    """Append a compact JSONL line for quick debugging/telemetry."""
    try:
        line = {
            "ts": int(time.time() * 1000),
            "queryId": query_id,
            "query": q,
            "mode": mode,
            "topK": top_k,
            "durationMs": None,
            "hitCount": len(results),
            "hits": [r.chunk_id for r in results],
            "correlationId": correlation_id,
            "source": source,
        }
        with open("/data/query_metadata.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        log.exception("failed to append /data/query_metadata.jsonl")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0",
                port=int(getattr(settings, "service_port", 5004)))
