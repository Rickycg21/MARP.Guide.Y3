import pytest
import asyncio
import os
from pathlib import Path
from app.pipeline import manual_index_document, collection

@pytest.mark.asyncio
async def test_manual_index_document(tmp_path):
    """
    Simulates a full document indexing event locally.
    """
    # 1 Test .txt file creation
    doc_id = "test_doc_001"
    test_text = "This is a simple test document.\nIt contains two sentences."
    text_file = tmp_path / f"{doc_id}.txt"
    text_file.write_text(test_text, encoding="utf-8")

    # 2. Run the manual_index_document function
    correlation_id = "manual-test-123"
    await manual_index_document(doc_id, str(text_file), correlation_id)

    # 3. Verify that the embeddings were saved
    results = collection.get(where={"document_id": doc_id})

    assert results is not None
    assert len(results["ids"]) > 0
    assert all("test_doc_001" in cid for cid in results["ids"])
    print(f"\n[TEST] Indexed {len(results['ids'])} chunks successfully.")

    # 4. Cleanup after test
    collection.delete(where={"document_id": doc_id})

