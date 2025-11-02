"""
Responsibile for "extraction":
- Locate the input PDF (written by Ingestion) under {DATA_ROOT}/pdfs/{doc_id}.pdf
- Extract page text with pdfplumber
- Write a single UTF-8 .txt file with page markers under {DATA_ROOT}/text/{doc_id}.txt
- Count tokens using tiktoken ("cl100k_base") to match GPT-4/4o family models

We Keep this module I/O-only and stateless; orchestration & events live in main.py.
"""

import os
import logging
from typing import Tuple

import pdfplumber # Extract text from PDF pages
import tiktoken   # Model-aligned tokenizer for token counts

from common.config import settings

logger = logging.getLogger("extraction")

# Build tokenizer once per process. cl100k_base covers GPT-4/4o families.
_ENCODER = tiktoken.get_encoding("cl100k_base")
logger.info("tiktoken 'cl100k_base' loaded for token counting")

def _paths_for(doc_id: str) -> Tuple[str, str, str]:
    """
    Compute canonical file locations in /data.
    Returns:
      (pdf_path, text_dir, text_path)
    - pdf_path:  /data/pdfs/<doc_id>.pdf   (input from Ingestion)
    - text_path: /data/text/<doc_id>.txt   (output for Indexing)
    """
    root = settings.data_root
    pdf_path  = os.path.join(root, "pdfs", f"{doc_id}.pdf")
    text_dir  = os.path.join(root, "text")
    os.makedirs(text_dir, exist_ok=True)
    text_path = os.path.join(text_dir, f"{doc_id}.txt")
    return pdf_path, text_dir, text_path

def extract_to_text(doc_id: str) -> Tuple[str, int, int]:
    """
    Parse a PDF and write a single .txt file with page markers.
    Returns:
      (text_path, page_count, token_count)
    """
    pdf_path, _, text_path = _paths_for(doc_id)

    if not os.path.exists(pdf_path):
        # Upstream bug (ingestion not finished or path mismatch)
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    page_count = 0
    token_count = 0

    # Open both files safely. On any exception, callers handle error & status.
    with pdfplumber.open(pdf_path) as pdf, open(text_path, "w", encoding="utf-8") as out:
        page_count = len(pdf.pages)
        for i, page in enumerate(pdf.pages, start=1):
            txt = page.extract_text() or "" # Some pages may be images (no text)
            # Page delimiter aids debugging and downstream chunking
            out.write(f"--- page {i} ---\n{txt}\n")
            # Model-aligned token counting (GPT-4/4o family)
            token_count += len(_ENCODER.encode(txt))

    logger.info(
        "Extracted %s -> %s pages=%s tokens=%s",
        doc_id, text_path, page_count, token_count
    )
    return text_path, page_count, token_count