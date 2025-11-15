# =============================================================================
# Purpose:
#   Pure retrieval helpers for the retrieval service using ChromaDB.
#
# Responsibilities:
#   - Open a persistent Chroma collection.
#   - Run hybrid search.
#   - Normalize results into a stable, minimal dict shape consumed by the API.
# =============================================================================

import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import chromadb
from rank_bm25 import BM25Okapi

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

        # Hybrid weighting: alpha * semantic + (1 - alpha) * bm25
        try:
            self.hybrid_alpha = float(os.getenv("HYBRID_ALPHA", "0.6"))
        except ValueError:
            self.hybrid_alpha = 0.6
        # Clamp alpha to [0,1] just in case.
        self.hybrid_alpha = max(0.0, min(1.0, self.hybrid_alpha))

        log.info(
            "[retriever] dir=%s collection=%s model=%s hybrid_alpha=%.2f",
            self.chroma_dir,
            self.collection,
            self.embed_model,
            self.hybrid_alpha,
        )

        # Create/get the persistent collection.
        self._pc = chromadb.PersistentClient(path=self.chroma_dir)
        self._coll = self._pc.get_or_create_collection(
            self.collection, metadata={"hnsw:space": "cosine"}
        )

    # ---------------------------------------------------------------------
    # Health
    # ---------------------------------------------------------------------

    async def health(self) -> Dict[str, Any]:
        """
        Return extended health info for the retrieval service, covering:
        - Chroma collection reachability
        - Embedding model configuration and basic embedding test
        - BM25 / hybrid pipeline readiness (tokenisation + small query)
        """
        status = "ok"
        chroma_ok = True

        # --- Check 1: Chroma connectivity
        try:
            _ = self._coll.count()
        except Exception as e:
            chroma_ok = False
            log.exception("chroma count failed: %s", e)
            status = "down"

        # --- Embedding model info
        embedding_info = {
            "reachable": chroma_ok,
            "model": self.embed_model
        }

        # -- Check 2: Embedding basic query test
        embed_ok = False
        if chroma_ok:
            try:
                # Use a fixed test query to verify embedding and retrieval returns results
                test_query = "health check"
                raw = self._coll.query(
                    query_texts=[test_query],
                    n_results=1,
                    include=["documents"],
                )
                # If we got at least one document, consider embedding path OK
                if raw.get("documents", [[]])[0]:
                    embed_ok = True
                else:
                    log.warning("health: embedding test returned no documents")
            except Exception as e:
                log.exception("health: embedding test failed: %s", e)

        if not embed_ok:
            # degrade but keep chroma_ok state
            status = "degraded" if status != "down" else "down"

        # -- Check 3: BM25/hybrid pipeline basic test
        bm25_ok = False
        if chroma_ok:
            try:
                # small artificial corpus test snippet
                docs = ["this is a test snippet for retrieval health"]
                tokenised = [self._tokenize(d) for d in docs]
                bm25 = BM25Okapi(tokenised)
                scores = bm25.get_scores(self._tokenize("test snippet"))
                if len(scores) == len(docs):
                    bm25_ok = True
                else:
                    log.warning("health: bm25 scoring returned unexpected length")
            except Exception as e:
                log.exception("health: bm25 pipeline failed: %s", e)

        if not bm25_ok:
            status = "degraded" if status != "down" else "down"

        # -- Final status logic
        final_status = status

        return {
            "status": final_status,
            "chromaDir": self.chroma_dir,
            "embedding": embedding_info,
            "bm25_pipeline": {"ready": bm25_ok},
        }


    # ---------------------------------------------------------------------
    # Search
    # ---------------------------------------------------------------------
    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """
        Tokenizer used for BM25.

        For our purposes we just:
          - lowercase
          - split on whitespace
        """
        if not text:
            return []
        return text.lower().split()

    async def search(
        self,
        q: str,
        top_k: int = 5,
        mode: str = "semantic",
        document_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Execute a hybrid query and normalize results.

        In "semantic" mode, ranking is based purely on cosine similarity.

        In "hybrid" mode, we:
          - semantically choose candidates set (N > top_k),
          - score those candidates with BM25 over their snippets,
          - fuse semantic and BM25 into a combined score in [0,1],
          - rank by the combined score.
        """
        if not q or not q.strip():
            raise ValueError("Empty query")

        # Optional per-document filter.
        where = {"document_id": document_id} if document_id else None

        # Decide how many semantic candidates to pull from Chroma.
        if mode == "hybrid":
            candidate_k = max(top_k * 5, top_k)
        else:
            candidate_k = top_k

        t0 = time.time()
        raw = self._coll.query(
            query_texts=[q],
            n_results=max(1, int(candidate_k)),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        duration_ms = int((time.time() - t0) * 1000)

        docs = raw.get("documents", [[]])[0]
        metas = raw.get("metadatas", [[]])[0]
        dists = raw.get("distances", [[]])[0]

        # If we have no documents at all, short-circuit.
        if not docs:
            return [], {"duration_ms": duration_ms}

        # ---- Semantic scoring: distance (cosine) -> similarity in [0,1]
        # Chroma returns cosine distance roughly in [0,2].
        # Similarity mapping: sim = 1 - (dist / 2), clamped to [0,1].
        semantic_sims: List[Optional[float]] = []
        for i in range(len(docs)):
            sim = None
            if i < len(dists) and dists[i] is not None:
                d = float(dists[i])
                sim = 1.0 - (d / 2.0)
                sim = max(0.0, min(1.0, sim))
            semantic_sims.append(sim)

        # If we are in pure semantic mode, keep the existing behaviour.
        if mode == "semantic":
            rows: List[Dict[str, Any]] = []
            for i, doc in enumerate(docs):
                md = metas[i] or {}
                sim = semantic_sims[i]

                rows.append(
                    {
                        "document_id": md.get("document_id") or "unknown",
                        "chunk_id": md.get("chunk_id"),
                        "page": md.get("page"),
                        "title": md.get("title"),
                        "url": md.get("url"),
                        "snippet": doc,
                        "scores": {"semantic": sim, "bm25": None, "combined": sim},
                    }
                )

            # Truncate to the requested top_k in case candidate_k > top_k.
            rows = rows[:top_k]
            return rows, {"duration_ms": duration_ms}

        # For any other mode that we don't explicitly support, log and fall back to semantic.
        if mode not in ("hybrid",):
            log.warning("Unknown mode=%s requested; falling back to semantic", mode)
            mode = "hybrid"

        # ---------------------------------------------------------------------
        # Hybrid mode: BM25 rerank of semantic candidates.
        # ---------------------------------------------------------------------

        # Build a tiny BM25 corpus over the semantic candidates' snippets.
        # We only use this corpus for this query.
        tokenized_docs: List[List[str]] = [self._tokenize(doc) for doc in docs]
        try:
            bm25 = BM25Okapi(tokenized_docs)
            query_tokens = self._tokenize(q)
            bm25_scores_raw = bm25.get_scores(query_tokens)
        except Exception as e:
            # If BM25 fails for any reason, fall back to semantic-only ranking.
            log.exception("BM25 scoring failed, falling back to semantic-only: %s", e)
            rows: List[Dict[str, Any]] = []
            for i, doc in enumerate(docs):
                md = metas[i] or {}
                sim = semantic_sims[i]
                rows.append(
                    {
                        "document_id": md.get("document_id") or "unknown",
                        "chunk_id": md.get("chunk_id"),
                        "page": md.get("page"),
                        "title": md.get("title"),
                        "url": md.get("url"),
                        "snippet": doc,
                        "scores": {"semantic": sim, "bm25": None, "combined": sim},
                    }
                )
            rows = rows[:top_k]
            return rows, {"duration_ms": duration_ms}

        # Normalize BM25 scores into [0,1] over this candidate set.
        bm25_scores_raw = [float(s) for s in bm25_scores_raw]
        if bm25_scores_raw:
            min_bm = min(bm25_scores_raw)
            max_bm = max(bm25_scores_raw)
        else:
            min_bm = max_bm = 0.0

        def _norm_bm25(x: float) -> float:
            if max_bm == min_bm:
                return 0.0
            return (x - min_bm) / (max_bm - min_bm)

        # Fuse semantic + BM25 into combined score, clamp to [0,1].
        alpha = self.hybrid_alpha
        rows: List[Dict[str, Any]] = []
        for i, doc in enumerate(docs):
            md = metas[i] or {}
            sem = semantic_sims[i] if i < len(semantic_sims) else None
            bm_raw = bm25_scores_raw[i] if i < len(bm25_scores_raw) else 0.0
            bm = _norm_bm25(bm_raw)

            # If semantic is missing for some reason, treat as 0.
            sem_val = float(sem) if sem is not None else 0.0
            combined = alpha * sem_val + (1.0 - alpha) * bm
            combined = max(0.0, min(1.0, combined))

            rows.append(
                {
                    "document_id": md.get("document_id") or "unknown",
                    "chunk_id": md.get("chunk_id"),
                    "page": md.get("page"),
                    "title": md.get("title"),
                    "url": md.get("url"),
                    "snippet": doc,
                    "scores": {
                        "semantic": sem,
                        "bm25": bm,
                        "combined": combined,
                    },
                }
            )

        # Sort by combined score descending and truncate to top_k.
        rows.sort(
            key=lambda r: (r.get("scores") or {}).get("combined") or 0.0,
            reverse=True,
        )
        rows = rows[:top_k]

        return rows, {"duration_ms": duration_ms}