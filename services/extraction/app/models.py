# Pydantic data models (schemas) for the extraction service.

from typing import Optional, List, Dict
from pydantic import BaseModel, AnyHttpUrl

# -----------------------------------------------------------------------------
# REST response models
# -----------------------------------------------------------------------------

class ExtractResponse(BaseModel):
    """
    Response shape for POST /extract/{document_id}.
    We return 202 Accepted + { "accepted": true } because the job
    runs asynchronously in the background.
    """
    accepted: bool = True

class ExtractStatus(BaseModel):
    """
    Response shape for GET /status/{document_id}.
    One status snapshot for a document.
    message: Human-friendly context ("manual trigger accepted", error text, etc.)
    """
    document_id: str
    status: str  # "pending" | "done" | "error"
    message: Optional[str] = None # context ("manual trigger accepted", error text, etc.)

class StatusList(BaseModel):
    """
    Response shape for GET /status.
    """
    status_history: List[ExtractStatus]

# -----------------------------------------------------------------------------
# Internal record written to append-only JSONL for metadata
# -----------------------------------------------------------------------------

class TextRecord(BaseModel):
    """
    One line in data/text_metadata.jsonl after a successful extraction.
    Fields mirror what downstream services need (and what's emitted in the
    DocumentExtracted event payload).
    """
    document_id: str   # Stable doc ID (same as ingestion)
    title: str # Human-readable label extracted from the <a> tag (hyperlink) text 
    url: AnyHttpUrl # Canonical absolute URL to the PDF (validated as HTTP/HTTPS)
    text_path: str     # Local path to the extracted text under DATA_ROOT/text/
    page_count: int    # Number of pages in the PDF
    token_count: int   # Number of tokens in extracted text (tiktoken for GPT-4/4o)
    extracted_by: str  # Extraction tool
    extracted_at: str  # Timestamp (UTC ISO-8601) when this record was produced