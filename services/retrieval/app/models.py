# =============================================================================
# Purpose: Minimal Pydantic v2 models for HTTP responses
# =============================================================================

from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field

Mode = Literal["semantic", "bm25", "hybrid"]

class Scores(BaseModel):
    """Per-result scoring. Keep values in [0,1] for easy UI use."""
    semantic: Optional[float] = Field(None, ge=0, le=1)
    bm25: Optional[float]     = Field(None, ge=0, le=1)
    combined: Optional[float] = Field(None, ge=0, le=1)

    model_config = {"populate_by_name": True}

class SearchResult(BaseModel):
    """Single hit returned from the vector DB."""
    document_id: str = Field(..., alias="documentId")
    page: Optional[int] = None
    title: Optional[str] = None
    url:   Optional[str] = None
    snippet: Optional[str] = None
    scores: Scores

    model_config = {"populate_by_name": True}

class SearchResponse(BaseModel):
    """Top-level response for /search and /dev/consumeChunksIndexed."""
    query_id: str = Field(..., alias="queryId")
    query:    str
    top_k:    int = Field(..., alias="topK", ge=1, le=50)
    mode:     Mode
    duration_ms: int = Field(..., alias="durationMs", ge=0)
    results: List[SearchResult]

    model_config = {"populate_by_name": True}

class HealthResponse(BaseModel):
    """Health summary used by /health."""
    status: Literal["ok", "degraded", "down"]
    chroma_dir: Optional[str] = Field(None, alias="chromaDir")
    embedding: Dict[str, Any]

    model_config = {"populate_by_name": True}
