# app/models.py
from typing import Optional
from pydantic import BaseModel

class IndexResponse(BaseModel):
    """
    Response for POST /index/{document_id}.
    """
    message: str
    correlationId: str

class IndexStats(BaseModel):
    """
    Response for GET /index/stats.
    """
    status: str
    documentsIndexed: int
    chunksStored: int
    vectorDb: str
    embeddingModel: str
