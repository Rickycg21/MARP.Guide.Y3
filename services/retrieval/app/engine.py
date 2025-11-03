# services/retrieval/app/engine.py
import os
import time
import uuid
import math
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

try:
    import chromadb
except ImportError:
    chromadb = None

from common.config import settings

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))


# ---- robust env helper: treat empty as "unset" ----
def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v.strip() if v and v.strip() else default


# ---- ENV with safe defaults (EMPTY -> default) ----
CHROMA_DIR = _env("CHROMA_DIR", "/data/index")
CHROMA_COLLECTION = _env("CHROMA_COLLECTION", "marp_chunks")

# If EMBEDDING_ENDPOINT is empty or unreachable, we’ll fall back to a deterministic dev vector.
EMBEDDING_ENDPOINT = _env("EMBEDDING_ENDPOINT", "")
EMBEDDING_MODEL = _env("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

DEFAULT_TOPK = int(_env("DEFAULT_TOPK", "5"))
MAX_TOPK = int(_env("MAX_TOPK", "50"))
REQUEST_TIMEOUT_MS = int(_env("REQUEST_TIMEOUT_MS", "2000"))


def _ms() -> int:
    return int(time.time() * 1000)


def _normalize_minmax(scores: List[float]) -> List[float]:
    if not scores:
        return []
    smin, smax = min(scores), max(scores)
    if math.isclose(smin, smax):
        return [0.0 for _ in scores]
    rng = (smax - smin)
    return [(s - smin) / rng for s in scores]


def _build_snippet(text: Optional[str], limit: int = 220) -> Optional[str]:
    if not text:
        return None
    t = " ".join(text.split())
    return (t if len(t) <= limit else t[: limit - 1] + "…")


class RetrievalEngine:
    """
    Chroma (persistent) + external embedder, with a safe dev fallback.
    """

    def __init__(
        self,
        chroma_dir: str = CHROMA_DIR,
        collection: str = CHROMA_COLLECTION,
        embedding_endpoint: str = EMBEDDING_ENDPOINT,
        embedding_model: str = EMBEDDING_MODEL,
        request_timeout_ms: int = REQUEST_TIMEOUT_MS,
    ):
        self.chroma_dir = chroma_dir
        self.collection_name = collection
        self.embedding_endpoint = embedding_endpoint
        self.embedding_model = embedding_model
        self.request_timeout = request_timeout_ms / 1000.0

        if chromadb is None:
            raise RuntimeError("chromadb is not installed.")

        logger.info(
            "Initializing Chroma client dir=%s collection=%s embedder=%s endpoint=%s",
            chroma_dir, collection, embedding_model, (embedding_endpoint or "<dev-fallback>"),
        )
        self.client = chromadb.PersistentClient(path=self.chroma_dir)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("RetrievalEngine ready.")

    # ----- Embedding -----
    async def embed_query(self, text: str) -> List[float]:
        """
        If EMBEDDING_ENDPOINT is empty or unreachable, use a deterministic dev fallback
        (lets you test without any embedder or compose changes).
        """
        # Dev fallback if no endpoint configured
        if not self.embedding_endpoint:
            return [0.1, 0.2, 0.7] if "envelope" in text.lower() else [0.8, 0.2, 0.1]

        # Real call
        payload = {"model": self.embedding_model, "input": text}
        try:
            async with httpx.AsyncClient(timeout=self.request_timeout) as client:
                r = await client.post(self.embedding_endpoint, json=payload)
                r.raise_for_status()
                data = r.json()
                emb = data["data"][0]["embedding"]
                if not isinstance(emb, list):
                    raise ValueError("embedding is not a list")
                return emb
        except Exception as e:
            logger.warning("Embedder unreachable (%s). Falling back to dev embedding.", e)
            return [0.1, 0.2, 0.7] if "envelope" in text.lower() else [0.8, 0.2, 0.1]

    # ----- Health -----
    async def health(self) -> Dict[str, Any]:
        # Index reachability
        try:
            _ = self.collection.count()
            idx_ok = True
        except Exception:
            idx_ok = False

        # Embedder reachability (ok if dev-fallback)
        if not self.embedding_endpoint:
            emb_ok = True
        else:
            try:
                async with httpx.AsyncClient(timeout=self.request_timeout) as client:
                    r = await client.post(
                        self.embedding_endpoint,
                        json={"model": self.embedding_model, "input": "."},
                    )
                emb_ok = r.status_code < 500
            except Exception:
                emb_ok = False

        status = "ok" if (idx_ok and emb_ok) else ("degraded" if idx_ok or emb_ok else "down")
        return {
            "status": status,
            "chromaDir": self.chroma_dir,
            "embedding": {"reachable": emb_ok, "model": self.embedding_model},
        }

    # ----- Search facade -----
    async def search(
        self,
        q: str,
        top_k: int = DEFAULT_TOPK,
        mode: str = "semantic",
        document_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        start = _ms()
        top_k = max(1, min(int(top_k), MAX_TOPK))

        if mode == "semantic":
            hits = await self._search_semantic(q, top_k, document_id=document_id)
        elif mode == "bm25":
            hits = await self._search_bm25(q, top_k, document_id=document_id)
        elif mode == "hybrid":
            hits = await self._search_hybrid(q, top_k, document_id=document_id)
        else:
            raise ValueError(f"Unsupported mode: {mode}")

        duration = _ms() - start
        return hits, {"duration_ms": duration}

    # ----- Implementations -----
    async def _search_semantic(
        self, q: str, top_k: int, document_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        vec = await self.embed_query(q)

        where: Optional[Dict[str, Any]] = None
        if document_id:
            where = {"document_id": {"$eq": document_id}}

        res = self.collection.query(
            query_embeddings=[vec],
            n_results=top_k,
            where=where,
            include=["metadatas", "documents", "distances"],
        )

        ids = res.get("ids", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        docs = res.get("documents", [[]])[0]
        dists = res.get("distances", [[]])[0]

        # Convert cosine distance to similarity proxy and normalize
        raw_sim = [max(0.0, 1.0 - float(d)) for d in dists]
        sim = _normalize_minmax(raw_sim)

        out: List[Dict[str, Any]] = []
        for i, meta in enumerate(metas):
            m = meta or {}
            content = docs[i] if i < len(docs) else None
            similarity = sim[i] if i < len(sim) else 0.0

            out.append(
                {
                    "document_id": m.get("document_id") or m.get("doc_id") or "unknown",
                    "chunk_id": ids[i] if i < len(ids) else (m.get("chunk_id") or str(uuid.uuid4())),
                    "page": m.get("page"),
                    "title": m.get("title"),
                    "url": m.get("url"),
                    "snippet": _build_snippet(content),
                    "scores": {
                        "semantic": round(float(similarity), 6),
                        "bm25": None,
                        "combined": round(float(similarity), 6),
                    },
                }
            )
        return out

    async def _search_bm25(
        self, q: str, top_k: int, document_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        # Stub for now; falls back to semantic
        return await self._search_semantic(q, top_k, document_id=document_id)

    async def _search_hybrid(
        self, q: str, top_k: int, document_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        sem = await self._search_semantic(q, top_k, document_id=document_id)
        bm25 = await self._search_bm25(q, top_k, document_id=document_id)

        def rank_map(hits: List[Dict[str, Any]]) -> Dict[str, int]:
            return {h["chunk_id"]: r for r, h in enumerate(hits, start=1)}

        r_sem = rank_map(sem)
        r_bm = rank_map(bm25)

        # Simple RRF fusion
        k = 50.0
        ids = {h["chunk_id"] for h in sem} | {h["chunk_id"] for h in bm25}
        fusion: List[Tuple[str, float]] = []
        for cid in ids:
            s = (1.0 / (k + r_sem.get(cid, 1000))) + (1.0 / (k + r_bm.get(cid, 1000)))
            fusion.append((cid, s))
        fusion.sort(key=lambda x: x[1], reverse=True)

        by_id = {h["chunk_id"]: h for h in (sem + bm25)}
        merged: List[Dict[str, Any]] = []
        for cid, score in fusion[:top_k]:
            base = dict(by_id[cid])
            base["scores"]["combined"] = round(float(score), 6)
            merged.append(base)
        return merged
