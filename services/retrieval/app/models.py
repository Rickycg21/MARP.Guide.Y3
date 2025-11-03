# services/retrieval/app/models.py
from typing import List, Optional, Literal, Any, Dict
from pydantic import BaseModel, Field

RetrievalMode = Literal["semantic", "bm25", "hybrid"]


class Scores(BaseModel):
    semantic: Optional[float] = Field(None, ge=0.0, le=1.0)
    bm25: Optional[float] = Field(None, ge=0.0, le=1.0)
    combined: Optional[float] = Field(None, ge=0.0, le=1.0)

    model_config = {"populate_by_name": True}


class SearchResult(BaseModel):
    document_id: str = Field(..., alias="documentId")
    chunk_id: str = Field(..., alias="chunkId")
    page: Optional[int] = None
    title: Optional[str] = None
    url: Optional[str] = None
    snippet: Optional[str] = None
    scores: Scores

    model_config = {"populate_by_name": True}


class SearchResponse(BaseModel):
    query_id: str = Field(..., alias="queryId")
    query: str
    top_k: int = Field(..., alias="topK", ge=1, le=50)
    mode: RetrievalMode
    duration_ms: int = Field(..., alias="durationMs", ge=0)
    results: List[SearchResult]

    model_config = {"populate_by_name": True}


class HealthEmbedding(BaseModel):
    reachable: bool
    model: Optional[str] = None

    model_config = {"populate_by_name": True}


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    chroma_dir: Optional[str] = Field(None, alias="chromaDir")
    embedding: HealthEmbedding

    model_config = {"populate_by_name": True}
