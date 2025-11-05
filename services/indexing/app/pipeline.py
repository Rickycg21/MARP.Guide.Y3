# --- Imports and setup for the indexing pipeline ---

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
import datetime
import json
import tiktoken

# Load the embedding model used for document chunk encoding
model = SentenceTransformer("all-MiniLM-L6-v2")
# Setup directory where ChromaDB will store the vector index
INDEX_DIR = "/data/index"


# --- Main event handler: triggered when a DocumentExtracted event is received ---
# It reads the text file, chunks it, generates embeddings, stores them, 
# logs metadata, and publishes a ChunksIndexed event.
async def handle_document(env: EventEnvelope, msg: AbstractIncomingMessage):
    
    try:
        # Extract data from the event
        payload = env.payload
        correlation_id = env.correlationId
        doc_id = payload["documentId"]
        text_path = payload["textPath"]
        title = payload.get("title")
        url = payload.get("url")

        print(f"[Indexing]Received DocumentExtracted for: {doc_id}")
        print(f"Text path: {text_path}")

        # Read the extracted text content
        text = await read_text_file(text_path)
        print(f"[Indexing] Text length: {len(text)} chars")

        # Split text into semantic chunks
        chunks = chunk_text_semantic(text, doc_id, title=title, url=url)

        # Generate embeddings for each chunk
        chunks = generate_embeddings(chunks)

        # Store embeddings and metadata in ChromaDB
        store_embeddings(doc_id, chunks)

        # Log metadata about this indexing process
        log_index_metadata(doc_id, len(chunks))

        # Publish "ChunksIndexed" event to notify other services
        await publish_chunks_indexed(doc_id, len(chunks), correlation_id)

        # Acknowledge the RabbitMQ message (mark as processed)
        await msg.ack()
        print(f"[Indexing]Acked message for {doc_id}")

    except Exception as e:
        # On failure, requeue the message so it can be retried
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

    # Raise an error if the text file doesn't exist
    if not path.exists():
        raise FileNotFoundError(f"Text file not found at {text_path}")

    #Read text file asynchronously
    async with aiofiles.open(path, "r", encoding="utf-8") as f:
        text = await f.read()

        # Validate that the file is not empty
    if not text.strip():
        raise ValueError(f"Text file at {text_path} is empty")

    print(f"[Indexing] Loaded text file ({len(text)} chars) from {text_path}")
    return text

def chunk_text_semantic(
    text: str,
    doc_id: str,
    title: str | None = None,
    url: str | None = None,
    max_tokens: int = 450,
    overlap_tokens: int = 50
):
    """
    Split the extracted MARP document text into semantically coherent chunks.
    - Honors page delimiters ("--- page N ---") as strong boundaries.
    - Uses paragraph and sentence structure within pages when possible.
    - Creates chunks of ≈450 tokens with ≈50-token overlap between ALL consecutive chunks.
    """

    # Load tokenizer used to measure token lengths
    enc = tiktoken.get_encoding("cl100k_base")

    def tok_count(s: str) -> int:
        """Helper: counts tokens in a string."""
        return len(enc.encode(s))

    # Split document by page markers (if any)
    parts = re.split(r"--- page (\d+) ---", text)
    
    # Each page will be stored as (page_number, page_text)
    pages = []
    if parts:
        # Handle case where document doesn't start with a page delimiter
        i = 0
        if parts[0].strip():
            # We don't know the page, assume 1
            pages.append((1, parts[0]))
        i = 1
        while i + 1 < len(parts):
            try:
                page_num = int(parts[i])

#################### Error handling for page number parsing is here, this happens everytime ####################

            except:
                # If parsing fails, assume sequential numbering
                page_num = (pages[-1][0] + 1) if pages else 1
            page_text = parts[i + 1]
            pages.append((page_num, page_text))
            i += 2

############################################################################################################################


    # Prepare for chunk generation
    chunks = []
    counter = 1

    # Token buffer used to handle overlapping between chunks
    next_chunk_prefix_ids = []

    #State for current chunk being built
    current_chunk = ""
    current_tokens = 0
    current_page = None

    def start_chunk_with_overlap_if_needed():
        """If overlap prefix is pending, prepends it to current chunk."""
        nonlocal current_chunk, current_tokens, next_chunk_prefix_ids
        if current_tokens == 0 and next_chunk_prefix_ids:
            prefix_text = enc.decode(next_chunk_prefix_ids)
            current_chunk = prefix_text
            current_tokens = len(next_chunk_prefix_ids)
            next_chunk_prefix_ids = []  

    # Function to finalize the current chunk and prepare overlap tokens
    def flush_chunk():
        """Emits the current chunk and prepares overlap for next chunk."""
        nonlocal counter, current_chunk, current_tokens, next_chunk_prefix_ids, current_page
        text_out = current_chunk.strip()
        if not text_out:
            return
        
        # Save chunk info and metadata
        chunks.append({
            "chunkId": f"{doc_id}-{counter:04}",
            "text": text_out,
            "document_id": doc_id,
            "title": title,
            "url": url,
            "page": current_page if current_page is not None else 1
        })

        counter += 1
        # Prepare overlap for next chunk
        token_ids = enc.encode(text_out)
        next_chunk_prefix_ids = token_ids[-overlap_tokens:] if len(token_ids) > overlap_tokens else token_ids

        # Reset chunk buffers
        current_chunk = ""
        current_tokens = 0

    # --- Main loop through all pages ---
    for page_num, page_content in pages:
        current_page = page_num

        # Split text by paragraphs
        paragraphs = re.split(r"\n\s*\n+", page_content)
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            ptok = tok_count(para)

            # If paragraph fits inside the current chunk
            if current_tokens + ptok <= max_tokens:
                start_chunk_with_overlap_if_needed()
                current_chunk += ("\n\n" if current_chunk else "") + para
                current_tokens += ptok
                continue

            # If it doesn't fit, split by sentences
            sentences = re.split(r'(?<=[.!?])\s+', para)
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                stok = tok_count(sent)

                # If sentence fits, add it
                if current_tokens + stok <= max_tokens:
                    start_chunk_with_overlap_if_needed()
                    current_chunk += (" " if current_chunk else "") + sent
                    current_tokens += stok
                else:
                    # If too large, start a new chunk
                    if stok <= max_tokens:
                        flush_chunk()
                        start_chunk_with_overlap_if_needed()
                        current_chunk = sent
                        current_tokens = stok
                    else:
                        # If sentence is longer than allowed, split by tokens (Strange case)

                        # Convert the sentence into a list of token IDs
                        sent_ids = enc.encode(sent)
                        i = 0
                        # Iterate through tokens until the whole sentence is processed
                        while i < len(sent_ids):
                            start_chunk_with_overlap_if_needed()
                            # Calculate how many tokens can still fit into this chunk
                            room = max_tokens - current_tokens

                            # If there's no room left, flush (save) the current chunk and start a new one
                            if room <= 0:
                                flush_chunk()
                                continue

                            # Take as many tokens as possible (without exceeding chunk size)
                            take = min(room, len(sent_ids) - i)
                            piece = enc.decode(sent_ids[i:i+take]).strip()
                            current_chunk += (" " if current_chunk else "") + piece

                            # Update counters for how many tokens we’ve used
                            current_tokens += take
                            i += take

                            # If chunk is full, emit it (prepares overlap)
                            if current_tokens >= max_tokens:
                                flush_chunk()

        # Ensure we flush remaining text at the end of each page
        flush_chunk()

    # --- Summary output for debugging ---
    total_tokens = sum(len(enc.encode(c["text"])) for c in chunks)
    avg_tokens = total_tokens / len(chunks) if chunks else 0
    print(
        f"[Indexing] Created {len(chunks)} semantic chunks "
        f"(~{max_tokens}t each, overlap ~{overlap_tokens}t, "
        f"total {total_tokens} tokens, avg {avg_tokens:.1f}t/chunk)"
    )

    print(f"[DEBUG] Ejemplo de metadatos: {chunks[0]}")
    return chunks

def generate_embeddings(chunks):

    """Generate embeddings for each chunk using the SentenceTransformer model. 
   Converts text chunks into numerical vectors that represent semantic meaning.
   These embeddings are what allow semantic search later on."""
    
    # Extract all chunk texts
    texts = [chunk["text"] for chunk in chunks]

    # Encode texts into numerical vectors using the preloaded transformer model
    vectors = model.encode(texts, convert_to_numpy=True)

    # Attach the embedding vector to each corresponding chunk
    for i, emb in enumerate(vectors):
        chunks[i]["embedding"] = emb.tolist()

    print(f"[Indexing] Generated {len(chunks)} embeddings")
    return chunks

# ChromaDB setup 
client = chromadb.PersistentClient(path=INDEX_DIR)
collection = client.get_or_create_collection("marp_docs")

def store_embeddings(document_id: str, chunks):

    """Store the generated embeddings and their metadata into ChromaDB."""

    # Prepare all lists needed by ChromaDB
    ids = [chunk["chunkId"] for chunk in chunks]
    embeddings = [chunk["embedding"] for chunk in chunks]
    texts = [chunk["text"] for chunk in chunks]

    metadatas = []
    for c in chunks:
        page_value = c.get("page", 1)
        try:
            # Ensure page number is an integer (avoid errors from None or strings)
            page_value = int(page_value)
        except Exception:
            page_value = 1  

        # Metadata attached to each chunk for search and traceability
        metadatas.append({
            "document_id": c.get("document_id", document_id),
            "chunk_id": c["chunkId"],
            "title": c.get("title"),
            "url": c.get("url"),
            "page": page_value
        })

    # Add everything to the ChromaDB collection
    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas
    )

    print(f"[Indexing] Stored {len(chunks)} chunks in ChromaDB with metadata (title, url, page)")

def log_index_metadata(document_id: str, chunk_count: int):
    """
    Appends per-document indexing metadata into ./data/index_metadata.jsonl
    according to the MARP Indexing specification.
    (Saved inside the container at /data/index_metadata.jsonl)
    """
    #Path to metadata file
    metadata_path = Path("/data/index_metadata.jsonl")

    # Create one JSON record for this document
    record = {
        "document_id": document_id,
        "index_path": INDEX_DIR,
        "chunk_count": chunk_count,
        "embedding_model": "all-MiniLM-L6-v2",
        "vector_db": "ChromaDB",
        "vector_dimension": 384,
        "indexed_at": datetime.datetime.utcnow().isoformat() + "Z"  
    }

    #Write record as JSON line
    with open(metadata_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    print(f"[Indexing] Logged metadata for {document_id}")

async def publish_chunks_indexed(doc_id: str, chunk_count: int, correlation_id: str):
    """
    Publishes a ChunksIndexed event following the standard MARP schema.
    """

    # Prepare event payload
    payload = {
        "documentId": doc_id,
        "chunkCount": chunk_count,
        "embeddingModel": "all-MiniLM-L6-v2",
        "vectorDb": "ChromaDB",
        "vectorDimension": 384,
        "indexPath": INDEX_DIR
    }

    # Create event envelope
    event = new_event(
        event_type="ChunksIndexed",
        payload=payload,
        correlation_id=correlation_id,
        source="indexing-service"
    )

    try:
        # Try to publish the event to RabbitMQ
        await publish_event(event)
        print(f"[Indexing] Published ChunksIndexed for {doc_id}")
    except AttributeError as e:
        # Local testing without RabbitMQ
        print(f"[Indexing] Skipping RabbitMQ publish in local mode ({e})")
    except Exception as e:
        # Catch-all for any other publishing issue
        print(f"[Indexing] Failed to publish ChunksIndexed: {e}")

def _lookup_title_url_from_text_metadata(document_id: str):
    """
    Searches for title and url in /data/text_metadata.jsonl (written by Extraction).
    """
    meta_path = Path("/data/text_metadata.jsonl")
    title, url = None, None

    # Check if the metadata file exists
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    # Match the metadata entry with the given document ID
                    if rec.get("document_id") == document_id:
                        title = rec.get("title")
                        url = rec.get("url")
                        break
                except Exception:
                    continue

    # Return both values (could be None if not found)
    return title, url

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
            collection.delete(where={"document_id": document_id})
            print(f"[Manual Index] Old embeddings deleted for {document_id}")
        except Exception as e:
            print(f"[Manual Index] No previous embeddings to remove ({e})")

        # Read original text
        text = await read_text_file(text_path)

        # Lookup title and url from text metadata
        title, url = _lookup_title_url_from_text_metadata(document_id)

        # Generate new embeddings
        chunks = chunk_text_semantic(text, document_id, title=title, url=url)
        chunks = generate_embeddings(chunks)

        # Store in ChromaDB
        store_embeddings(document_id, chunks)

        # Log metadata
        log_index_metadata(document_id, len(chunks))

        # Publish updated event
        await publish_chunks_indexed(document_id, len(chunks), correlation_id)

        print(f"[Manual Index] Re-index completed for {document_id}")

    except Exception as e:
        print(f"[Manual Index] Error re-indexing {document_id}: {e}")
        raise