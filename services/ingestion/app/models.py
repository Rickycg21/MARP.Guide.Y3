# Pydantic data models (schemas) for the ingestion service.

from typing import Optional, List, Dict
from pydantic import BaseModel, AnyHttpUrl

class DiscoverResponse(BaseModel):
    """
    Response shape for POST /discover.
    """
    discovered_count: int # Number of processed/downloaded PDFs

class DocumentRecord(BaseModel):
    """
    One line in the append-only JSONL catalog file (/data/pdf_metadata.jsonl).
    """
    document_id: str # Stable ID derived from the PDF URL (URL-hash). Idempotency key
    title: str # Human-readable label extracted from the <a> tag (hyperlink) text 
    url: AnyHttpUrl # Canonical absolute URL to the PDF (validated as HTTP/HTTPS)
    download_path: str # Local path to the saved PDF under DATA_ROOT/pdfs/
    pages: Optional[int] = None # Page count
    discovered_at: str # Timestamp (UTC ISO-8601) when this record was produced

class DocumentsList(BaseModel):
    """
    Response shape for GET /documents.
    """
    documents: List[DocumentRecord]