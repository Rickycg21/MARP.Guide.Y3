# Indexing Service

## Responsibility
Transform extracted text into vector embeddings and store searchable chunks in the vector index.

## Data Owned
- `/data/index/` — vector index storage referenced by *ChunksIndexed.payload.indexPath*
- `/data/index.db` — lightweight mapping (document_id -> embedding_ids)
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

## Communicates With
- RabbitMQ (event broker)
- Local `data/` folder
- Embedding model