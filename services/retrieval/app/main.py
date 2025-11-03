# services/retrieval/app/main.py
import os
import uuid
import logging
from typing import Any, Dict, Optional, List

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

# Local imports
from app.engine import RetrievalEngine
from app.models import (
    SearchResponse,
    SearchResult,
    Scores,
    HealthResponse,
)
from common.config import settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))


# Pydantic v2-friendly dump
def _to_json(model) -> Dict[str, Any]:
    try:
        return model.model_dump(by_alias=True)  # v2
    except AttributeError:
        return model.dict(by_alias=True)        # v1


# Optional event publishing
RETRIEVAL_PUBLISH_EVENTS = os.getenv("RETRIEVAL_PUBLISH_EVENTS", "false").lower() == "true"
EVENT_EXCHANGE = os.getenv("EVENT_EXCHANGE", "events")
_publish_impl = None


async def _maybe_publish_retrieval_completed(
    correlation_id: Optional[str],
    query_id: str,
    query_text: str,
    mode: str,
    top_k: int,
    duration_ms: int,
    results: List[dict],
) -> None:
    if not RETRIEVAL_PUBLISH_EVENTS:
        return
    global _publish_impl
    try:
        if _publish_impl is None:
            from common import events as events_mod  # lazy import
            _publish_impl = getattr(events_mod, "publish_event_async", None) or getattr(events_mod, "publish_event", None)
        if _publish_impl is None:
            logger.warning("Events module present but no publish function; skipping publish.")
            return

        payload = {
            "queryId": query_id,
            "queryText": query_text,
            "topK": top_k,
            "mode": mode,
            "retrievalTimeMs": duration_ms,
            "hitCount": len(results),
            "results": [
                {
                    "documentId": r.get("document_id"),
                    "page": r.get("page"),
                    "chunkId": r.get("chunk_id"),
                    "score": (r.get("scores") or {}).get("combined") or (r.get("scores") or {}).get("semantic"),
                }
                for r in results
            ],
        }

        envelope = {
            "eventType": "RetrievalCompleted",
            "payload": payload,
            "correlationId": correlation_id or str(uuid.uuid4()),
        }

        maybe_coro = _publish_impl(envelope, exchange=EVENT_EXCHANGE)
        if hasattr(maybe_coro, "__await__"):
            await maybe_coro
    except Exception as e:
        logger.exception("Failed to publish RetrievalCompleted: %s", e)


# ------------------------------------------------------------------------------
# FastAPI app
# ------------------------------------------------------------------------------
app = FastAPI(title="retrieval-service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

engine: Optional[RetrievalEngine] = None


@app.on_event("startup")
async def on_startup():
    global engine
    engine = RetrievalEngine()


@app.on_event("shutdown")
async def on_shutdown():
    pass


@app.get("/health")
async def health() -> JSONResponse:
    assert engine is not None
    h = await engine.health()
    resp = HealthResponse(
        status=h.get("status", "down"),
        chroma_dir=h.get("chromaDir"),
        embedding=h.get("embedding", {"reachable": False, "model": None}),
    )
    return JSONResponse(_to_json(resp))


@app.get("/search")
async def search(
    q: str = Query(..., min_length=1, description="User query text"),
    topK: int = Query(5, ge=1, le=int(os.getenv("MAX_TOPK", "50")), description="Number of results to return"),
    mode: str = Query("semantic", regex="^(semantic|bm25|hybrid)$"),
    documentId: Optional[str] = Query(None, description="Restrict to a single document"),
    correlationId: Optional[str] = Query(None, description="Trace correlation id"),
) -> JSONResponse:
    assert engine is not None

    try:
        results_raw, stats = await engine.search(
            q=q, top_k=topK, mode=mode, document_id=documentId
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception("Search failed: %s", e)
        raise HTTPException(status_code=500, detail="Search failed")

    # Cast to Pydantic models for consistent shape
    results: List[SearchResult] = []
    for r in results_raw:
        scores = r.get("scores") or {}
        sr = SearchResult(
            document_id=r.get("document_id", "unknown"),
            chunk_id=r.get("chunk_id", str(uuid.uuid4())),
            page=r.get("page"),
            title=r.get("title"),
            url=r.get("url"),
            snippet=r.get("snippet"),
            scores=Scores(
                semantic=scores.get("semantic"),
                bm25=scores.get("bm25"),
                combined=scores.get("combined"),
            ),
        )
        results.append(sr)

    query_id = str(uuid.uuid4())
    resp = SearchResponse(
        query_id=query_id,
        query=q,
        top_k=topK,
        mode=mode,  # type: ignore
        duration_ms=int(stats.get("duration_ms", 0)),
        results=results,
    )

    # Best-effort event emission
    await _maybe_publish_retrieval_completed(
        correlation_id=correlationId,
        query_id=query_id,
        query_text=q,
        mode=mode,
        top_k=topK,
        duration_ms=int(stats.get("duration_ms", 0)),
        results=results_raw,
    )

    # ---- JSONL query log  ----
    try:
        import json, time
        log_line = {
            "ts": int(time.time() * 1000),
            "queryId": query_id,
            "query": q,
            "mode": mode,
            "topK": topK,
            "durationMs": int(stats.get("duration_ms", 0)),
            "hitCount": len(results),
            "hits": [r.chunk_id for r in results],  # pydantic object → string ids
            "correlationId": correlationId,
        }
        with open("/data/query_metadata.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(log_line, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("failed to append /data/query_metadata.jsonl")

    return JSONResponse(_to_json(resp))


if __name__ == "__main__":
    import uvicorn
    port = int(getattr(settings, "service_port", 5004))
    uvicorn.run(app, host="0.0.0.0", port=port)
