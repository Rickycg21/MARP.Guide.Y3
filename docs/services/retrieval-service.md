# Retrieval Service

## Responsibility
Perform semantic and keyword searches over the indexed content, returning ranked chunks for question answering.

## Data Owned
- `/data/query_metadata.jsonl` — query metadata (query_id, query_text, top_k, results[document id, page, title, score], retrieval_time_ms)

## API Endpoints
| Method | Endpoint | Description | Returns |
|---------|-----------|--------------|----------|
| GET | `/search?q={query}&top_k={n}` | Retrieve top-k chunks for a query  | 200 OK + JSON |
| GET | `/health` | Health check | 200 OK |

## Events
- **Consumes:** `ChunksIndexed`
- **Publishes:** `RetrievalCompleted`

## Communicates With
- RabbitMQ (event broker)
- Local `data/` folder
- Vector database (under `data/index/`)