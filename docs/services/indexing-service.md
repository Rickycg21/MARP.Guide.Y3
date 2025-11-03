# Indexing Service

## Responsibility
Transform extracted text into vector embeddings and store searchable chunks in the vector index.

## Data Owned
- `/data/index/` — vector index storage referenced by *ChunksIndexed.payload.indexPath*
- `index_metadata.jsonl` — per-document indexing metadata (document_id, index_path, chunk_count, embedding_model, vector_db, vector_dimention, indexed_at)

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