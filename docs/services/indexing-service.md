# Indexing Service

## Responsibility
Transform extracted text into vector embeddings and store searchable chunks in the vector index.

## Data Owned
- `/data/index/` — vector embeddings and chunk metadata
- `index.db` — mapping (doc_id → embedding_ids)

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