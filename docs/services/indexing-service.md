# Indexing Service

## Responsibility
Transform extracted text into vector embeddings and store searchable chunks in the vector index.

## Data Owned
- `/data/index/` — vector index storage referenced by *ChunksIndexed.data.index_path*
- `/data/index.db` — lightweight mapping (document_id -> embedding_ids) for maintenance and rebuilds
- `index_metadata.jsonl` — per-document indexing metadata (document_id, chunk_count, embedding_model, vector_db)

## API Endpoints
| Method | Endpoint | Description | Returns |
|---------|-----------|--------------|----------|
| POST | `/index/{document_id}` | Index a document | 202 Accepted |
| GET | `/index/stats` | Retrieve index statistics | 200 OK + JSON |
| GET | `/health` | Health check | 200 OK |

## Events
- **Consumes:** `DocumentExtracted`
- **Publishes:** `ChunksIndexed`

## Talks To
- RabbitMQ (event broker)
- Persistent volume (`/data`)
- Embedding model

## Design Decisions

- The chosen chunk size (≈450 tokens) is a design baseline derived from the embedding model’s technical limit (512 tokens per input) and the expected structure of MARP documents, which are dense, academic-style regulations.  

- Such texts benefit from paragraph-level context rather than short sentence fragments.  

- This range (≈350–550 tokens) is also consistent with common RAG benchmarks for legal or policy data, balancing semantic completeness with retrieval precision.  
The value will be empirically refined once real document statistics become available.

### Chunking Strategy

The Indexing Service divides extracted MARP document text into semantically coherent chunks before generating embeddings.

| Parameter | Decision | Rationale |
|------------|-----------|------------|
| **Chunk size** | **≈ 450 tokens (~2,000–2,500 characters)** | Keeps each chunk below the 512-token limit of the embedding model (*all-MiniLM-L6-v2*) while maintaining full-paragraph context from academic/legal MARP texts. Balances semantic completeness with retrieval granularity. |
| **Overlap** | **≈ 50 tokens (≈ 10–15 %)** | Ensures continuity between chunks so that phrases spanning chunk boundaries are preserved in at least one embedding, preventing context loss during retrieval. |
| **Split logic** | **Prefer paragraph / newline boundaries, fallback to token count** | MARP PDFs are structurally formatted; preserving paragraph divisions yields more natural semantic boundaries than hard character counts. |
| **Average chunk volume per document** | *100–250 chunks* for MARP PDFs (40–80 pages) | Provides manageable vector counts (~40k vectors for full MARP corpus) for efficient retrieval latency within ChromaDB. |


#### Implementation Notes
Chunking is implemented in `pipeline.py`.  
Each chunk stores metadata such as:

```json
{
  "chunkId": "marp-2025-policy-v3-0042",
  "tokens": 438,
  "page": 16,
  "text": "...",
  "metadata": {
    "documentId": "marp-2025-policy-v3",
    "title": "Assessment Regulations 2025",
    "url": "https://www.lancaster.ac.uk/.../Assessment_Regulations.pdf"
  }
}
