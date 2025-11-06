# Indexing Service

## Responsibility
Transform extracted text into vector embeddings and store searchable chunks in the vector index.

## Data Owned
- `/data/index/` — vector index storage referenced by *ChunksIndexed.payload.indexPath*
- `index_metadata.jsonl` — per-document indexing metadata (document_id, index_path, chunk_count, embedding_model, vector_db, vector_dimension, indexed_at)

## API Endpoints
| Method | Endpoint | Description | Returns |
|---------|-----------|--------------|----------|
| POST | `/index/{document_id}` | Index a document | 202 Accepted |
| GET | `/index/stats` | Retrieve index statistics | 200 OK + JSON |
| GET | `/health` | Health check | 200 OK |

## Events
- **Consumes:** `DocumentExtracted`
- **Publishes:** `ChunksIndexed`

## Communicates With
- RabbitMQ (event broker)
- Local `data/` folder
- Embedding model

## Design Decisions

- The chosen chunk size (≈450 tokens) is a design baseline derived from the embedding model’s technical limit (512 tokens per input) and the expected structure of MARP documents academic-style regulations.  

- Such texts benefit from paragraph-level context rather than short sentence fragments.  

### Chunking Strategy

The Indexing Service divides extracted MARP document text into semantically coherent chunks before generating embeddings.

| Parameter | Decision | Rationale |
|------------|-----------|------------|
| **Chunk size** | **≈ 450 tokens (~2,000–2,500 characters)** | Keeps each chunk below the 512-token limit of the embedding model (*all-MiniLM-L6-v2*) while maintaining full-paragraph context from academic/legal MARP texts. Balances semantic completeness with retrieval granularity. |
| **Overlap** | **≈ 50 tokens (≈ 10–15 %)** | Ensures continuity between chunks so that phrases spanning chunk boundaries are preserved in at least one embedding, preventing context loss during retrieval. |
| **Split logic** | **Prefer paragraph / newline boundaries, fallback to token count** | MARP PDFs are structurally formatted; preserving paragraph divisions yields more natural semantic boundaries than hard character counts. |
| **Average chunk volume per document** | *100–250 chunks* for MARP PDFs (40–80 pages) | Provides manageable vector counts (~40k vectors for full MARP corpus) for efficient retrieval latency within ChromaDB. |


#### Test Coverage
Automated tests validate the behavior and reliability of the Indexing Service endpoints and their integration with the local vector store (ChromaDB).

| Test | Endpoint / Component | Purpose | Expected Result |
|------|----------------------|----------|-----------------|
| **Health Check** | `GET /health` | Ensures the service is running and responsive. | Returns `200 OK` with `{"status": "ok"}`. |
| **Manual Indexing** | `POST /index/{document_id}` | Simulates a manual re-indexing operation for an existing document. Verifies that the text file is found, embeddings are generated, and a `ChunksIndexed` event is produced. | Returns `202 Accepted` with a `correlationId`. |
| **Index Statistics** | `GET /index/stats` | Retrieves real-time statistics from ChromaDB, counting indexed documents and total chunks stored. | Returns `200 OK` with JSON summary of index statistics. |

### 🧪 Local Python Tests

>bash
# Navigate to the indexing service
cd services/indexing

# Run all test suites
pytest -v

# Run a specific test file
pytest tests/test_endpoints.py -v

# Clean previous test cache
pytest --cache-clear

### Dependencies

- **Python 3.13+**
- **FastAPI** — REST API framework  
- **ChromaDB** — Local vector database  
- **SentenceTransformers (all-MiniLM-L6-v2)** — Embedding model  
- **RabbitMQ** — Event broker  
- **pytest** — Automated testing

#### Implementation Notes

- Tests are located in tests/test_endpoints.py and executed using pytest and FastAPI TestClient.

- A temporary .txt file is created before execution and automatically deleted afterwards to avoid residual data.

- Each test runs independently, and the ChromaDB collection is cleaned between executions to maintain deterministic results.

- Two DeprecationWarnings appear during test execution due to FastAPI’s on_event being deprecated. These warnings are harmless and safely ignored during testing.
