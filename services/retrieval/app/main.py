# =============================================================================
# File: main.py
# Purpose:
#   FastAPI surface for the retrieval service.
#
# Responsibilities:
#   - Expose /search and /health.
#   - Publish RetrievalCompleted events.
#   - Append compact telemetry lines to /data/query_metadata.jsonl.
# =============================================================================

import os, uuid, json, time, logging, datetime as dt
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.retriever import Retriever
from app.models import HealthResponse, SearchResponse, SearchResult, Scores, RetrievalResult, RetrievalPayload, RetrievalCompletedEvent

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
    """
    Publish a RetrievalCompleted event with a minimal payload that downstream
    consumers can rely on. 
    """
    if not PUBLISH_EVENTS:
        return

    global _publish
    try:
        if _publish is None:
            from common import events as ev
            _publish = getattr(ev, "publish_event_async", None) or getattr(ev, "publish_event", None)
        if _publish is None:
            log.warning("No publish function found, skipping event.")
            return

        # Compute top score if present.
        top_score: Optional[float] = None
        for r in results or []:
            s = (r.get("scores") or {}).get("combined")
            if s is not None:
                top_score = s if top_score is None else max(top_score, s)

        # Map results
        payload_results: List[RetrievalResult] = []
        for r in results or []:
            scores_dict = (r.get("scores") or {})  # semantic/bm25/combined from retriever
            payload_results.append(
                RetrievalResult(
                    docId=r.get("document_id"),
                    chunkId=r.get("chunk_id"),
                    page=r.get("page"),
                    title=r.get("title"),
                    url=r.get("url"),
                    score=scores_dict.get("combined"), # Top Score
                    scores={                           # Full score breakdown.
                        "semantic": scores_dict.get("semantic"),
                        "bm25": scores_dict.get("bm25"),
                        "combined": scores_dict.get("combined"),
                    },
                )
            )

        event = RetrievalCompletedEvent(
            eventType="RetrievalCompleted",
            eventId=str(uuid.uuid4()),
            timestamp=dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            correlationId=correlation_id or str(uuid.uuid4()),
            source=SERVICE_NAME,
            version="1.0",
            payload=RetrievalPayload(
                queryId=query_id,
                query=query_text,
                resultsCount=len(payload_results),
                topScore=top_score,
                latencyMs=int(duration_ms or 0),
                results=payload_results,
            ),
        )

        maybe = _publish(event)
        if hasattr(maybe, "__await__"):  # supports async or sync implementations
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
    """
    Health check summarizing:
    - Chroma connectivity.
    - Basic embedding test.
    - BM25 / hybrid pipeline readiness
    """
    assert retriever
    h = await retriever.health()
    return JSONResponse(HealthResponse(
        status=h.get("status","down"),
        chroma_dir=h.get("chromaDir"),
        embedding=h.get("embedding", {"reachable": False, "model": None}),
        bm25_pipeline=h.get("bm25_pipeline")
    ).model_dump(by_alias=True))

@app.get("/search")
async def search(
    q: str = Query(..., min_length=1, description="User query text"),
    topK: int = Query(5, ge=1, le=int(os.getenv("MAX_TOPK", "50")), description="Number of results"),
    mode: str = Query("hybrid", pattern="^(semantic|bm25|hybrid)$"),
    documentId: Optional[str] = Query(None, description="Restrict to a single document"),
    correlationId: Optional[str] = Query(None, description="Trace id for events/logs"),
) -> JSONResponse:
    """
    Run retrieval and return normalized results.
    - Publishes RetrievalCompleted.
    - Logs a compact line to /data/query_metadata.jsonl.
    """
    assert retriever

    if mode == "bm25":
        raise HTTPException(
            status_code=400,
            detail="BM25 alone mode is not implemented, use 'semantic' or 'hybrid'.",
        )

    try:
        t0 = time.monotonic_ns()
        rows, _stats = await retriever.search(q=q, top_k=topK, mode=mode, document_id=documentId)
        elapsed_ms = int((time.monotonic_ns() - t0) / 1e6)
    except ValueError as ve:
        raise HTTPException(400, str(ve))
    except Exception as e:
        log.exception("search failed: %s", e)
        raise HTTPException(500, "Search failed")

    # Shape rows -> response models (keeps field aliases for API)
    results = [SearchResult(
        document_id=r.get("document_id","unknown"),
        chunk_id=r.get("chunk_id"),
        page=r.get("page"),
        title=r.get("title"),
        url=r.get("url"),
        snippet=r.get("snippet"),
        scores=Scores(**(r.get("scores") or {})),
    ) for r in rows]

    query_id = str(uuid.uuid4())
    resp = SearchResponse(
        query_id=query_id, query=q, top_k=topK, mode=mode,
        duration_ms=elapsed_ms,
        results=results,
    )

    await publish_retrieval_completed(
        correlation_id=correlationId, query_id=query_id, query_text=q,
        mode=mode, top_k=topK, duration_ms=elapsed_ms, results=rows
    )

    _log_query_jsonl(
        query_id=query_id,
        query_text=q,
        mode=mode,
        top_k=topK,
        retrieval_time_ms=elapsed_ms,
        results=results,
    )

    return JSONResponse(resp.model_dump(by_alias=True))

# -----------------------------------------------------------------------------
# Compact JSONL log for telemetry/debugging
# -----------------------------------------------------------------------------
def _log_query_jsonl(
    query_id: str,
    query_text: str,
    mode: str,
    top_k: int,
    retrieval_time_ms: int,
    results: List[SearchResult],
) -> None:
    """
    Append a compact JSONL line for quick debugging/telemetry at /data/query_metadata.jsonl.
    """
    try:
        out_results: List[Dict[str, Any]] = []
        for r in results:
            out_results.append({
                "document_id": r.document_id,
                "chunk_id": r.chunk_id,
                "page": r.page,
                "title": r.title,
                "url": r.url,
                "scores": {
                    "semantic": r.scores.semantic if r.scores else None,
                    "bm25": r.scores.bm25 if r.scores else None,
                    "combined": r.scores.combined if r.scores else None,
                },
            })

        line = {
            "query_id": query_id,
            "query_text": query_text,
            "mode": mode,
            "top_k": top_k,
            "retrieval_time_ms": int(retrieval_time_ms or 0),
            "results": out_results,
        }
        with open("/data/query_metadata.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        log.exception("failed to append /data/query_metadata.jsonl")

# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0",
                port=int(getattr(settings, "service_port", 5004)))
