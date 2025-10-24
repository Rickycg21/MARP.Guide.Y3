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