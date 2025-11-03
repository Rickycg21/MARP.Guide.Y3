import pytest
from fastapi.testclient import TestClient
from app.main import app
from pathlib import Path
from common.config import settings 

"""
Two DeprecationWarnings appear during tests because FastAPI's 'on_event' is deprecated.
They do not affect functionality and can be safely ignored.
"""

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_test_text_file(tmp_path_factory):
    """
    Create a test text file for the endpoint /index/{document_id}.
    """
    data_root = Path(settings.data_Root) / "text"  
    data_root.mkdir(parents=True, exist_ok=True)
    test_file = data_root / "test_doc_endpoint.txt"
    test_file.write_text("This is a document used for endpoint testing.", encoding="utf-8")

    yield str(test_file)

    # Delete test file after tests
    if test_file.exists():
        test_file.unlink()

def test_health_endpoint():
    """
    Verify that the /health endpoint returns status ok.
    """
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    print("[TEST] /health passed ✅")

def test_index_document_endpoint():
    """
    Test the POST /index/{document_id} endpoint with a real file.
    """
    response = client.post("/index/test_doc_endpoint")
    assert response.status_code == 202
    data = response.json()
    assert "correlationId" in data
    assert "message" in data
    print(f"[TEST] /index/test_doc_endpoint passed ✅ - correlationId: {data['correlationId']}")

def test_index_stats_endpoint():
    """
    Verify that the /index/stats endpoint returns index statistics.
    """
    response = client.get("/index/stats")
    assert response.status_code == 200
    data = response.json()

    assert "status" in data and data["status"] == "ok"
    assert "documentsIndexed" in data
    assert "chunksStored" in data
    assert "vectorDb" in data
    print(f"[TEST] /index/stats passed ✅ - docs: {data['documentsIndexed']}, chunks: {data['chunksStored']}")