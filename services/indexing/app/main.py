from common.config import settings
import asyncio
from fastapi import FastAPI, BackgroundTasks, HTTPException
from common.events import consume
from app.pipeline import handle_document, manual_index_document
from uuid import uuid4
from pathlib import Path

app = FastAPI(title="Indexing Service")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(consume("DocumentExtracted", handle_document))
    print("Indexing Service started and listening for DocumentExtracted events.")

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/index/{document_id}", status_code=202)
async def index_document(document_id: str, background_tasks: BackgroundTasks):

    text_path = Path(settings.data_root) / "text" / f"{document_id}.txt"  
    if not text_path.exists():
        raise HTTPException(status_code=404, detail=f"Text file for document '{document_id}' not found at: {text_path}")
    
    correlation_id = f"manual-{uuid4()}"
    background_tasks.add_task(manual_index_document, document_id, str(text_path), correlation_id)

    return {
    "message": f"Indexing accepted for {document_id}",
    "correlationId": correlation_id
}

