from common.events import EventEnvelope
try:
    from aio_pika.abc import AbstractIncomingMessage
except ImportError:
    # Fallback only for local testing without RabbitMQ
    class AbstractIncomingMessage:
        pass
from pathlib import Path
import aiofiles
from sentence_transformers import SentenceTransformer
import re
import chromadb
from common.events import publish_event, new_event
import datetime, uuid

model = SentenceTransformer("all-MiniLM-L6-v2")

async def handle_document(env: EventEnvelope, msg: AbstractIncomingMessage):
    
    try:
        payload = env.payload
        correlation_id = env.correlationId
        doc_id = payload["documentId"]
        text_path = payload["textPath"]

        print(f"[Indexing]Received DocumentExtracted for: {doc_id}")
        print(f"Text path: {text_path}")

        text = await read_text_file(text_path)
        print(f"[Indexing] Text length: {len(text)} chars")

        chunks = chunk_text_semantic(text, doc_id)

        chunks = generate_embeddings(chunks)

        store_embeddings(doc_id, chunks)

        await publish_chunks_indexed(doc_id, len(chunks), correlation_id)

        await msg.ack()
        print(f"[Indexing]Acked message for {doc_id}")

    except Exception as e:
        print(f"[Indexing] Error handling DocumentExtracted: {e}")
        await msg.nack(requeue=True)

async def read_text_file(text_path: str) -> str:
    """
    Reads the extracted MARP document text file asynchronously.

    Args:
        text_path (str): Absolute path to the extracted .txt file.

    Returns:
        str: Full text content of the document.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the file is empty.
    """
    path = Path(text_path)

    if not path.exists():
        raise FileNotFoundError(f"Text file not found at {text_path}")

    # Leer el texto de forma asíncrona
    async with aiofiles.open(path, "r", encoding="utf-8") as f:
        text = await f.read()

    if not text.strip():
        raise ValueError(f"Text file at {text_path} is empty")

    print(f"[Indexing] Loaded text file ({len(text)} chars) from {text_path}")
    return text

def chunk_text_semantic(text: str, doc_id: str):
    """
    Simple text splitter that breaks the text into chunks of ~450 characters
    using sentence boundaries when possible.
    """
    # Dividir por puntos, signos de interrogación o exclamación.
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())

    chunks = []
    current_chunk = ""
    chunk_size = 450
    counter = 1

    for sentence in sentences:
        if len(current_chunk) + len(sentence) < chunk_size:
            current_chunk += " " + sentence
        else:
            chunks.append({
                "chunkId": f"{doc_id}-{counter:04}",
                "text": current_chunk.strip()
            })
            counter += 1
            current_chunk = sentence

    if current_chunk.strip():
        chunks.append({
            "chunkId": f"{doc_id}-{counter:04}",
            "text": current_chunk.strip()
        })

    print(f"[Indexing] Created {len(chunks)} semantic chunks")
    return chunks

def generate_embeddings(chunks):
    texts = [chunk["text"] for chunk in chunks]
    vectors = model.encode(texts, convert_to_numpy=True, show_progress_bar=True)

    for i, emb in enumerate(vectors):
        chunks[i]["embedding"] = emb.tolist()

    print(f"[Indexing] Generated {len(chunks)} embeddings")
    return chunks

client = chromadb.Client()
collection = client.get_or_create_collection("marp_docs")

def store_embeddings(document_id: str, chunks):
    ids = [chunk["chunkId"] for chunk in chunks]
    embeddings = [chunk["embedding"] for chunk in chunks]
    texts = [chunk["text"] for chunk in chunks]
    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=[{"document_id": document_id}] * len(chunks)
    )
    print(f"[Indexing] Stored {len(chunks)} chunks in ChromaDB")

async def publish_chunks_indexed(doc_id: str, chunk_count: int, correlation_id: str):
    """
    Publishes a ChunksIndexed event following the standard MARP schema.
    """
    payload = {
        "documentId": doc_id,
        "chunkCount": chunk_count,
        "embeddingModel": "all-MiniLM-L6-v2",
        "vectorDb": "ChromaDB",
        "vectorDimension": 384,
        "indexPath": "/data/index/index.db"
    }

    # Create event envelope
    event = new_event(
        event_type="ChunksIndexed",
        payload=payload,
        correlation_id=correlation_id,
        source="indexing-service"
    )

    try:
        await publish_event(event)
        print(f"[Indexing] Published ChunksIndexed for {doc_id}")
    except AttributeError as e:
        # Local testing without RabbitMQ
        print(f"[Indexing] Skipping RabbitMQ publish in local mode ({e})")
    except Exception as e:
        print(f"[Indexing] Failed to publish ChunksIndexed: {e}")

async def manual_index_document(document_id: str, text_path: str, correlation_id: str):
    """
    Manual re-indexing of an existing document.
    Removes old embeddings before re-indexing.
    Used by POST /index/{document_id} endpoint.
    """
    try:
        print(f"[Manual Index] Re-indexing {document_id}...")

        # Delete old embeddings
        try:
            deleted = collection.delete(where={"document_id": document_id})
            print(f"[Manual Index] Old embeddings deleted for {document_id}")
        except Exception as e:
            print(f"[Manual Index] No previous embeddings to remove ({e})")

        # Read original text
        text = await read_text_file(text_path)

        # Generate new embeddings
        chunks = chunk_text_semantic(text, document_id)
        chunks = generate_embeddings(chunks)

        # Store in ChromaDB
        store_embeddings(document_id, chunks)

        # Publish updated event
        await publish_chunks_indexed(document_id, len(chunks), correlation_id)

        print(f"[Manual Index] Re-index completed for {document_id}")

    except Exception as e:
        print(f"[Manual Index] Error re-indexing {document_id}: {e}")
        raise