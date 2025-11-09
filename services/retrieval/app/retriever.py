# =============================================================================
# Purpose:
#   Pure retrieval helpers for the retrieval service using ChromaDB.
#
# Responsibilities:
#   - Open a persistent Chroma collection.
#   - Run semantic search via Chroma's built-in embedding.
#   - Normalize results into a stable, minimal dict shape consumed by the API.
# =============================================================================

import os
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

import chromadb
from chromadb.utils import embedding_functions

log = logging.getLogger(__name__)


class Retriever:
    """
    Thin wrapper around:
      - Chroma persistent collection
      - Search -> normalized result rows
    """

    def __init__(
        self,
        chroma_dir: Optional[str] = None,
        collection: Optional[str] = None,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    ) -> None:
        """
        Initialize a Chroma persistent client and get/create the target collection.
        """
        # Resolve configuration from args or environment.
        self.chroma_dir = chroma_dir or os.getenv("CHROMA_DIR") or "/data/index"
        self.collection = collection or os.getenv("CHROMA_COLLECTION") or "marp_docs"
        self.embed_model = embedding_model

        log.info(
            "[retriever] dir=%s collection=%s model=%s",
            self.chroma_dir, self.collection, self.embed_model
        )

        # Create/get the persistent collection.
        self._pc = chromadb.PersistentClient(path=self.chroma_dir)
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=self.embed_model
        )
        self._coll = self._pc.get_or_create_collection(
            self.collection,
            metadata={"hnsw:space": "cosine"},
            embedding_function=ef
        )
        
    

    # ---------------------------------------------------------------------
    # Health
    # ---------------------------------------------------------------------
    async def health(self) -> Dict[str, Any]:
        """
        Return minimal health info for Chroma.
        """
        chroma_ok = True
        try:
            _ = self._coll.count()
        except Exception as e:
            chroma_ok = False
            log.exception("chroma count failed: %s", e)

        status = "ok" if chroma_ok else "down"
        return {
            "status": status,
            "chromaDir": self.chroma_dir,
            "embedding": {"reachable": chroma_ok, "model": self.embed_model},
        }

    # ---------------------------------------------------------------------
    # Search
    # ---------------------------------------------------------------------
    async def search(
        self, q: str, top_k: int = 5, mode: str = "semantic", document_id: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Execute a semantic query using Chroma's internal embedding and normalize results.
        """
        if not q or not q.strip():
            raise ValueError("Empty query")

        # Optional per-document filter.
        where = {"document_id": document_id} if document_id else None

        # Use the same embedding model as indexing on query.
        t0 = time.time()
        raw = self._coll.query(
            query_texts=[q],
            n_results=max(1, int(top_k)),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        duration_ms = int((time.time() - t0) * 1000)

        docs = raw.get("documents", [[]])[0]
        metas = raw.get("metadatas", [[]])[0]
        dists = raw.get("distances", [[]])[0]

        rows: List[Dict[str, Any]] = []
        for i, doc in enumerate(docs):
            md = metas[i] or {}

            # ---- distance (cosine) -> similarity in [0,1]
            # Chroma returns cosine distance roughly in [0,2].
            # Similarity mapping: sim = 1 - (dist / 2), clamped to [0,1].
            sim = None
            if i < len(dists) and dists[i] is not None:
                d = float(dists[i])
                sim = 1.0 - (d / 2.0)
                sim = max(0.0, min(1.0, sim))

            rows.append({
                "document_id": md.get("document_id") or "unknown",
                "page":        md.get("page"),
                "title":       md.get("title"),
                "url":         md.get("url"),
                "snippet":     doc,
                "scores":      {"semantic": sim, "bm25": None, "combined": sim},
            })

        return rows, {"duration_ms": duration_ms}