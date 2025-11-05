# =============================================================================
# Purpose: Pure retrieval helpers (Chroma + embedding)
# =============================================================================

import os
import logging
from typing import Any, Dict, List, Optional, Tuple

import chromadb
import httpx 

log = logging.getLogger(__name__)


class Retriever:
    """
    Thin wrapper around:
      - Chroma persistent collection
      - Query embedding via Chroma (query_texts) to match index dims
      - Search -> normalized result rows (dicts)
    """

    def __init__(
        self,
        chroma_dir: Optional[str] = None,
        collection: Optional[str] = None,
        embedding_endpoint: Optional[str] = None,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    ) -> None:
        self.chroma_dir = chroma_dir or os.getenv("CHROMA_DIR") or "/data/index"
        self.collection = collection or os.getenv("CHROMA_COLLECTION") or "marp_docs"
        self.embed_ep   = embedding_endpoint or os.getenv("EMBEDDING_ENDPOINT") or ""
        self.embed_model = embedding_model

        log.info(
            "[retriever] dir=%s collection=%s model=%s endpoint=%s",
            self.chroma_dir, self.collection, self.embed_model, self.embed_ep or "<dev-fallback>"
        )

        self._pc   = chromadb.PersistentClient(path=self.chroma_dir)
        self._coll = self._pc.get_or_create_collection(
            self.collection, metadata={"hnsw:space": "cosine"}
        )

    # ---------------------------------------------------------------------
    # Health
    # ---------------------------------------------------------------------
    async def health(self) -> Dict[str, Any]:
        """Return minimal health info for Chroma + embedder."""
        chroma_ok = True
        try:
            _ = self._coll.count()
        except Exception as e:
            chroma_ok = False
            log.exception("chroma count failed: %s", e)

        embed_ok = True
        if self.embed_ep:
            try:
                async with httpx.AsyncClient(timeout=2.0) as c:
                    r = await c.post(self.embed_ep, json={"input": ""})
                    embed_ok = (r.status_code == 200)
            except Exception:
                embed_ok = False

        status = "ok" if (chroma_ok and embed_ok) else ("degraded" if chroma_ok else "down")
        return {
            "status": status,
            "chromaDir": self.chroma_dir,
            "embedding": {"reachable": embed_ok, "model": self.embed_model},
        }

    # ---------------------------------------------------------------------
    # Search
    # ---------------------------------------------------------------------
    async def search(
        self, q: str, top_k: int = 5, mode: str = "semantic", document_id: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Embed the query using Chroma's built-in text embedding (query_texts) so the
        query dim matches the collection. For cosine distance (0..2), convert to a
        [0..1] similarity with sim = 1 - (dist / 2).
        Returns: (rows, stats) where rows is a list of dicts:
        {document_id, chunk_id, page, title, url, snippet, scores={semantic,bm25,combined}}
        """
        if not q or not q.strip():
            raise ValueError("Empty query")

        where = {"document_id": document_id} if document_id else None

        raw = self._coll.query(
            query_texts=[q],
            n_results=max(1, int(top_k)),
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        docs  = raw.get("documents", [[]])[0]
        metas = raw.get("metadatas", [[]])[0]
        dists = raw.get("distances", [[]])[0]

        rows: List[Dict[str, Any]] = []
        for i, doc in enumerate(docs):
            md = metas[i] or {}

            if i < len(dists) and dists[i] is not None:
                dist = float(dists[i])
                sim = 1.0 - (dist / 2.0)
                sim = max(0.0, min(1.0, sim))
            else:
                sim = None

            rows.append({
                "document_id": md.get("document_id") or "unknown",
                "chunk_id":    md.get("chunk_id") or "",
                "page":        md.get("page"),
                "title":       md.get("title"),
                "url":         md.get("url"),
                "snippet":     doc,
                "scores":      {"semantic": sim, "bm25": None, "combined": sim},
            })

        return rows, {"duration_ms": 0}
