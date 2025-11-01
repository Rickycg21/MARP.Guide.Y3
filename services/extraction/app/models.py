"""
Pydantic data models for the extraction service.

- Request/Response models used by the HTTP API.
- Broker envelope models used to validate inbound events from RabbitMQ.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


# -------- API response models --------
class ExtractAccepted(BaseModel):
    accepted: bool
    documentId: str


class StatusResponse(BaseModel):
    status: str
    documentId: str
    pageCount: Optional[int] = None
    charCount: Optional[int] = None
    artifacts: Dict[str, Optional[str]]


# -------- Inbound event  --------
class DocumentDiscoveredData(BaseModel):
    id: str
    title: Optional[str] = ""
    download_path: Optional[str] = None
    stored_path: Optional[str] = None
    path: Optional[str] = None
    size_bytes: Optional[int] = None


class DocumentDiscoveredEnvelope(BaseModel):
    event_type: str = Field(..., description="e.g. 'DocumentDiscovered'")
    timestamp: str
    correlation_id: Optional[str] = None
    source_service: Optional[str] = None
    data: DocumentDiscoveredData


# -------- Outbound event --------
class ExtractedMetadata(BaseModel):
    title: str
    extractedBy: str
    extractedAt: str


class DocumentExtractedPayload(BaseModel):
    documentId: str
    textPath: str
    pageCount: Optional[int]
    tokenCount: Optional[int]
    metadata: ExtractedMetadata


class DocumentExtractedEvent(BaseModel):
    eventType: str = "DocumentExtracted"
    eventId: str
    timestamp: str
    correlationId: Optional[str] = None
    source: str
    version: str = "1.0"
    payload: DocumentExtractedPayload






