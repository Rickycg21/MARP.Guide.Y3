# =============================================================================
# Purpose:
#   Minimal Pydantic v2 response models used by the retrieval service HTTP API.
#
# Responsibilities:
#   - Define the wire format for /search and /health responses.
#   - Keep field names stable via aliases to match the documented API.
#   - Keep score values normalized to [0,1] for simple UI rendering.
# =============================================================================

from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from dataclasses import dataclass

# Supported retrieval modes.
# - "semantic": vector-only retrieval via Chroma
# - "bm25": lexical-only retrieval (not yet implemented)
# - "hybrid": semantic + bm25 with a fused combined score
Mode = Literal["semantic", "bm25", "hybrid"]


class Scores(BaseModel):
    """
    Per-result scoring container.

    All values are optional and clamped to [0,1] where applicable.

    In semantic-only mode, typically only `semantic` and `combined` are set.
    In hybrid mode, both `semantic` and `bm25` may be populated, and `combined`
    represents the fused score used for ranking.
    """
    semantic: Optional[float] = Field(None, ge=0, le=1)
    bm25: Optional[float] = Field(None, ge=0, le=1)
    combined: Optional[float] = Field(None, ge=0, le=1)

    # Ensure alias names are respected when serializing.
    model_config = {"populate_by_name": True}


class SearchResult(BaseModel):
    """
    Single retrieval hit.

    The minimal metadata we currently expose per hit.
    """
    document_id: str = Field(..., alias="documentId")
    chunk_id: Optional[str] = Field(None, alias="chunkId")
    page: Optional[int] = None
    title: Optional[str] = None
    url: Optional[str] = None
    snippet: Optional[str] = None
    scores: Scores

    model_config = {"populate_by_name": True}


class SearchResponse(BaseModel):
    """
    Top-level response for /search.

    Contains the echo of the query parameters plus a list of ranked results. The
    duration is measured server-side for rough latency telemetry.
    """
    query_id: str = Field(..., alias="queryId")
    query: str
    top_k: int = Field(..., alias="topK", ge=1, le=50)
    mode: Mode
    duration_ms: int = Field(..., alias="durationMs", ge=0)
    results: List[SearchResult]

    model_config = {"populate_by_name": True}


@dataclass
class RetrievalResult:
    """
    Represents a single retrieval hit in the event payload.
    """
    docId: str
    chunkId: Optional[str]
    page: Optional[int]
    title: Optional[str]
    url: Optional[str]
    score: Optional[float]
    scores: Optional[Dict[str, Optional[float]]]


@dataclass
class RetrievalPayload:
    """
    Encapsulates the retrieval results for a single query.
    """
    queryId: str
    query: str
    resultsCount: int
    topScore: Optional[float]
    latencyMs: int
    results: List[RetrievalResult]


@dataclass
class RetrievalCompletedEvent:
    """
    Event message signalling retrieval is complete.
    """
    eventType: str
    eventId: str
    timestamp: str
    correlationId: str
    source: str
    version: str
    payload: RetrievalPayload


class HealthResponse(BaseModel):
    """
    Health summary used by /health.
    """
    status: Literal["ok", "degraded", "down"]
    chroma_dir: Optional[str] = Field(None, alias="chromaDir")
    embedding: Dict[str, Any]
    bm25_pipeline: Optional[Dict[str, bool]] = Field(None, alias="bm25_pipeline")

    model_config = {"populate_by_name": True}