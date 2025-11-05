"""
Chat Service - FastAPI app implementing /chat to orchestrate RAG answers
that meet the MARP-Guide requirements while remaining terminal-friendly.

Key points:
- Talks to Retrieval Service over HTTP (/search?q=...&top_k=...)
- Calls OpenRouter's gpt-4o mini model for generation (plain HTTPX client)
- Emits AnswerGenerated events via shared event helpers
- Appends answer metadata to /data/answer_metadata.jsonl
- Health endpoint: /health
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

try:
    from common.config import settings  # type: ignore
except Exception:
    @dataclass(frozen=True)
    class _Settings:
        service_name: str = os.getenv("SERVICE_NAME", "chat")
        service_port: int = int(os.getenv("SERVICE_PORT", "5005"))
        rabbitmq_url: str = os.getenv("RABBITMQ_URL", "amqp://admin:admin@localhost:5672/")
        data_root: str = os.getenv("DATA_ROOT", "./data")
        log_level: str = os.getenv("LOG_LEVEL", "INFO")

    settings = _Settings()  # type: ignore

try:
    from common.events import new_event, publish_event, now_iso  # type: ignore
except Exception:
    import datetime as _dt
    from dataclasses import dataclass as _dataclass

    @_dataclass(frozen=True)
    class _FallbackEvent:
        eventType: str
        eventId: str
        timestamp: str
        correlationId: Optional[str]
        source: str
        version: str
        payload: Dict[str, Any]

    def now_iso() -> str:
        return _dt.datetime.now(tz=_dt.timezone.utc).isoformat()

    def new_event(
        event_type: str,
        payload: Dict[str, Any],
        correlation_id: str,
        *,
        version: str = "1.0",
        source: Optional[str] = None,
    ):
        return _FallbackEvent(
            eventType=event_type,
            eventId=str(uuid.uuid4()),
            timestamp=now_iso(),
            correlationId=correlation_id,
            source=source or getattr(settings, "service_name", "chat"),
            version=version,
            payload=payload,
        )

    async def publish_event(event: Any) -> None:
        logging.getLogger("chat-service").warning(
            "Event bus unavailable; dropped event %s", getattr(event, "eventType", "unknown")
        )


logging.basicConfig(
    level=getattr(logging, str(getattr(settings, "log_level", "INFO")).upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("chat-service")

# --- Config via env ----------------------------------------------------------
RETRIEVAL_URL = os.getenv("RETRIEVAL_URL", "http://retrieval:8000")
RETRIEVAL_MODE = os.getenv("RETRIEVAL_MODE", "semantic")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_BASE = os.getenv("OPENROUTER_BASE", "https://openrouter.ai/api/v1")

try:
    _cit_limit_env = int(os.getenv("CHAT_CITATION_LIMIT", "1"))
except ValueError:
    _cit_limit_env = 1
CITATION_LIMIT = max(1, _cit_limit_env)

# --- Data locations ----------------------------------------------------------
DATA_DIR = settings.data_root
ANSWER_META_PATH = os.path.join(DATA_DIR, "answer_metadata.jsonl")
os.makedirs(DATA_DIR, exist_ok=True)


# --- Pydantic schemas --------------------------------------------------------
class Citation(BaseModel):
    title: str
    page: Optional[int] = None
    url: Optional[str] = None


class RetrievedChunk(BaseModel):
    text: str
    title: Optional[str] = None
    page: Optional[int] = None
    url: Optional[str] = None
    score: Optional[float] = None


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=3)
    top_k: int = Field(5, ge=1, le=10)
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation]
    model: str
    tokens_used: Optional[int] = None
    latency_ms: int
    correlation_id: str


def _select_context(chunks: List[RetrievedChunk]) -> List[RetrievedChunk]:
    """
    Pick the subset of retrieved chunks that will be turned into citations.
    Default is a single chunk, matching the current assessment requirement.
    """
    return chunks[:CITATION_LIMIT] if chunks else []


# --- OpenRouter call ---------------------------------------------------------
async def _llm_answer(question: str, context_blocks: List[RetrievedChunk]) -> Dict[str, Any]:
    """
    Call OpenRouter's chat completions endpoint, returning the generated answer,
    token usage, model, and supporting citations.
    """
    selected = _select_context(context_blocks)
    if not selected:
        raise HTTPException(status_code=500, detail="No context available for generation")

    citations = [
        Citation(
            title=block.title or "MARP Source",
            page=block.page,
            url=block.url,
        )
        for block in selected
    ]

    if os.getenv("LLM_FAKE", "0") == "1":
        citation = citations[0]
        reference = citation.title
        if citation.page is not None:
            reference += f" p.{citation.page}"
        if citation.url:
            reference += f" ({citation.url})"
        text = (
            "[FAKE LLM] Local stub answer grounded on the provided source. "
            f"Reference: [1] {reference}."
        )
        return {
            "text": text,
            "tokens_used": 0,
            "model": "fake-llm",
            "citations": citations,
        }

    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY not configured")

    context_lines: List[str] = []
    for idx, block in enumerate(selected, start=1):
        details = []
        if block.title:
            details.append(block.title)
        if block.page is not None:
            details.append(f"p.{block.page}")
        suffix = f" ({', '.join(details)})" if details else ""
        context_lines.append(f"[{idx}] {block.text.strip()}{suffix}")
    context_text = "\n".join(context_lines)

    system_prompt = (
        "You are a MARP assistant answering questions for students and staff. "
        "Use only the supplied context snippets. "
        "Cite exactly one source as [1] in your answer. "
        'If the context is insufficient, reply with "I\'m not certain. Source: not available."'
    )

    user_prompt = (
        f"Question: {question.strip()}\n\n"
        f"Context:\n{context_text}\n\n"
        "Respond concisely, grounded entirely in the context. "
        "Include the citation marker [1] once, pointing to the most relevant context line."
    )

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("OPENROUTER_REFERRER", "http://localhost"),
        "X-Title": os.getenv("OPENROUTER_TITLE", "MARP-Guide Chat"),
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{OPENROUTER_BASE}/chat/completions", headers=headers, json=payload
        )
        if response.status_code >= 400:
            logger.error("OpenRouter error %s: %s", response.status_code, response.text)
            raise HTTPException(status_code=502, detail="LLM generation failed")
        data = response.json()

    choice = (data.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content", "")
    if not content:
        raise HTTPException(status_code=502, detail="LLM returned empty response")

    text = content.strip()
    if "[1]" not in text:
        text = f"{text} [1]".strip()

    usage = data.get("usage") or {}

    return {
        "text": text,
        "tokens_used": usage.get("total_tokens"),
        "model": data.get("model", OPENROUTER_MODEL),
        "citations": citations,
    }


# --- Retrieval call ----------------------------------------------------------
async def _retrieve(
    question: str,
    top_k: int,
    correlation_id: Optional[str],
) -> Tuple[List[RetrievedChunk], Dict[str, Any]]:
    """
    Call the Retrieval service to obtain MARP snippets.
    When RETRIEVAL_FAKE=1, return deterministic stubs so the chat service can
    run in isolation during early development.
    Returns both the normalised chunks and a metadata dict from the retrieval call.
    """
    limit = max(1, min(top_k, 10))
    if os.getenv("RETRIEVAL_FAKE", "0") == "1":
        fake_chunks = [
            RetrievedChunk(
                text="MARP consolidates Lancaster University's academic regulations for staff and students.",
                title="MARP Handbook",
                page=1,
                url="https://example.org/marp.pdf",
                score=0.99,
            ),
            RetrievedChunk(
                text="Appeals must normally be submitted within ten working days of the decision notification.",
                title="MARP Handbook",
                page=42,
                url="https://example.org/marp.pdf",
                score=0.95,
            ),
        ]
        selected = fake_chunks[:limit]
        meta = {
            "query_id": "fake-query",
            "mode": "offline",
            "duration_ms": 0,
            "result_count": len(selected),
            "results": [{"title": chunk.title, "page": chunk.page, "score": chunk.score} for chunk in selected],
        }
        return selected, meta

    url = f"{RETRIEVAL_URL.rstrip('/')}/search"
    params: Dict[str, Any] = {"q": question, "topK": limit, "mode": RETRIEVAL_MODE}
    if correlation_id:
        params["correlationId"] = correlation_id

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, params=params)
        if response.status_code >= 400:
            logger.error("Retrieval error %s: %s", response.status_code, response.text)
            raise HTTPException(status_code=502, detail="Retrieval failed")
        data = response.json()

    results = data.get("results") or []
    if not isinstance(results, list):
        raise HTTPException(status_code=502, detail="Retrieval payload malformed")

    chunks: List[RetrievedChunk] = []
    result_summaries: List[Dict[str, Any]] = []
    for raw in results:
        snippet = (raw.get("snippet") or "").strip()
        if not snippet:
            logger.debug("Skipping retrieval hit without snippet: %s", raw)
            continue

        scores = raw.get("scores") or {}
        score_val: Optional[float] = None
        if isinstance(scores, dict):
            for key in ("combined", "semantic", "bm25"):
                val = scores.get(key)
                if isinstance(val, (int, float)):
                    score_val = float(val)
                    break

        try:
            chunk = RetrievedChunk(
                text=snippet,
                title=raw.get("title"),
                page=raw.get("page"),
                url=raw.get("url"),
                score=score_val,
            )
        except Exception as exc:
            logger.warning("Skipping malformed chunk: %s (%s)", raw, exc)
            continue

        chunks.append(chunk)
        result_summaries.append(
            {
                "document_id": raw.get("documentId") or raw.get("document_id"),
                "chunk_id": raw.get("chunkId") or raw.get("chunk_id"),
                "score": score_val,
            }
        )

    if not chunks:
        raise HTTPException(status_code=404, detail="No supporting sources found")

    meta = {
        "query_id": data.get("queryId"),
        "mode": data.get("mode"),
        "duration_ms": data.get("durationMs"),
        "result_count": len(chunks),
        "results": result_summaries,
    }

    return chunks, meta


# --- Metadata persistence ----------------------------------------------------
def _append_answer_metadata(record: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(ANSWER_META_PATH), exist_ok=True)
    with open(ANSWER_META_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


# --- FastAPI app -------------------------------------------------------------
app = FastAPI(title="MARP-Guide Chat Service")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    start = time.perf_counter()
    correlation_id = str(uuid.uuid4())
    session_id = req.session_id or str(uuid.uuid4())

    # 1) Retrieve supporting chunks
    chunks, retrieval_meta = await _retrieve(req.question, req.top_k, correlation_id)
    context_blocks = _select_context(chunks)

    # 2) Generate grounded answer
    llm_result = await _llm_answer(req.question, context_blocks)
    latency_ms = int((time.perf_counter() - start) * 1000)

    response = ChatResponse(
        answer=llm_result["text"],
        citations=llm_result["citations"],
        model=llm_result["model"],
        tokens_used=llm_result.get("tokens_used"),
        latency_ms=latency_ms,
        correlation_id=correlation_id,
    )

    # 3) Persist metadata for auditability
    meta_record = {
        "timestamp": now_iso(),
        "session_id": session_id,
        "correlation_id": correlation_id,
        "question": req.question,
        "top_k": req.top_k,
        "model": response.model,
        "tokens_used": response.tokens_used,
        "latency_ms": response.latency_ms,
        "citations": [c.model_dump() for c in response.citations],
        "context_used": [block.model_dump() for block in context_blocks],
        "retrieval": retrieval_meta,
    }
    _append_answer_metadata(meta_record)

    # 4) Publish AnswerGenerated event for downstream consumers
    try:
        event = new_event(
            "AnswerGenerated",
            payload={
                "session_id": session_id,
                "question": req.question,
                "answer": response.answer,
                "citations": [c.model_dump() for c in response.citations],
                "model": response.model,
                "tokens_used": response.tokens_used,
                "latency_ms": response.latency_ms,
                "citation_limit": CITATION_LIMIT,
                "retrieval": {
                    "query_id": retrieval_meta.get("query_id"),
                    "duration_ms": retrieval_meta.get("duration_ms"),
                    "result_count": retrieval_meta.get("result_count"),
                },
            },
            correlation_id=correlation_id,
        )
        await publish_event(event)
    except Exception as exc:
        logger.warning("Failed to publish AnswerGenerated event: %s", exc)

    return response


# Uvicorn entrypoint for Docker
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
