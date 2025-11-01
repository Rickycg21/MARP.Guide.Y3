"""
What this file is for:
- All domain logic: reading PDFs, writing JSONL per page, computing stats/tokens.
- Building the DocumentExtracted event (matching events.md).
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional, Tuple

import pdfplumber

from common.config import settings
from .models import DocumentExtractedEvent, DocumentExtractedPayload, ExtractedMetadata


# ---------- directory fallbacks derived from DATA_ROOT ----------
_DATA_ROOT   = getattr(settings, "data_root", "/data")
PDF_DIR      = getattr(settings, "pdf_dir",  os.path.join(_DATA_ROOT, "pdfs"))
TEXT_DIR     = getattr(settings, "text_dir", os.path.join(_DATA_ROOT, "text"))
METRICS_DIR  = getattr(settings, "metrics_dir", os.path.join(_DATA_ROOT, "metrics"))


METADATA_LOG = os.path.join(_DATA_ROOT, "text_metadata.jsonl")

# ---------- simple counters ----------
COUNTERS_PATH = os.path.join(METRICS_DIR, "counters.json")
_DEFAULT_COUNTERS = {"events_consumed": 0, "docs_extracted": 0, "errors": 0}


def load_counters() -> dict:
    try:
        with open(COUNTERS_PATH, "r") as f:
            raw = f.read().strip()
            if not raw:
                return _DEFAULT_COUNTERS.copy()
            return json.loads(raw)
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return _DEFAULT_COUNTERS.copy()


def bump_counters(**delta) -> None:
    data = load_counters()
    for k, v in delta.items():
        data[k] = data.get(k, 0) + v
    os.makedirs(METRICS_DIR, exist_ok=True)
    tmp_path = COUNTERS_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp_path, COUNTERS_PATH)


# ---------- utility helpers ----------
def estimate_tokens_from_chars(n_chars: int) -> int:
    return max(1, round(n_chars / 4))


def jsonl_stats(path: str) -> Tuple[int, int]:
    """
    Iterate a JSONL of {"page": int, "text": str, "chars": int}
    and return (page_count, total_chars).
    """
    pages = 0
    total_chars = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                pages += 1
                try:
                    rec = json.loads(line)
                    total_chars += int(rec.get("chars", 0))
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    return pages, total_chars


def coalesce_pdf_path(data: dict) -> str:
    """
    Resolve the path field from data with tolerance for earlier names.
    """
    return data.get("download_path") or data.get("stored_path") or data.get("path") or ""


def extract_pdf_to_jsonl(pdf_path: str, out_path: str) -> dict:
    """
    Save one JSON object per page: {"page": i, "text": "...", "chars": N}
    Returns a small stats dict.
    """
    page_count, chars_out = 0, 0
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with pdfplumber.open(pdf_path) as pdf, open(out_path, "w", encoding="utf-8") as out:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            page_count += 1
            chars_out += len(text)
            out.write(json.dumps({"page": i, "text": text, "chars": len(text)}, ensure_ascii=False) + "\n")
    return {
        "page_count": page_count,
        "bytes_out": os.path.getsize(out_path),
        "chars_out": chars_out,
    }


def build_extracted_event(
    *,
    doc_id: str,
    title: str,
    text_path: str,
    page_count: Optional[int],
    token_count: Optional[int],
    correlation_id: Optional[str]
) -> DocumentExtractedEvent:
    """
    Build a Pydantic-validated outbound DocumentExtracted event.
    """
    now = datetime.now(timezone.utc).isoformat()
    payload = DocumentExtractedPayload(
        documentId=doc_id,
        textPath=text_path,
        pageCount=page_count,
        tokenCount=token_count,
        metadata=ExtractedMetadata(
            title=title or "",
            extractedBy="pdfplumber",
            extractedAt=now,
        ),
    )
    # eventId left to main.py to generate (so tests can stub)
    return DocumentExtractedEvent(
        eventId="__to_be_filled__",
        timestamp=now,
        correlationId=correlation_id,
        source=settings.service_name,
        payload=payload,
    )


def append_metadata_line(evt: DocumentExtractedEvent) -> None:
    """
    Append a compact record derived from the outbound event to text_metadata.jsonl.
    """
    rec = {
        "documentId": evt.payload.documentId,
        "textPath":   evt.payload.textPath,
        "pageCount":  evt.payload.pageCount,
        "tokenCount": evt.payload.tokenCount,
        "metadata":   evt.payload.metadata.model_dump(),
        "correlationId": evt.correlationId,
        "eventId":       evt.eventId,
        "source":        evt.source,
        "writtenAt":     datetime.now(timezone.utc).isoformat(),
    }
    os.makedirs(os.path.dirname(METADATA_LOG), exist_ok=True)
    with open(METADATA_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
