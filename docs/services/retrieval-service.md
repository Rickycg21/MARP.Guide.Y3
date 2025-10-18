# Retrieval Service

## Responsibility
Perform semantic and keyword searches over the indexed content, returning ranked chunks for question answering.

## Data Owned
- `/data/queries/` — cached queries and results

## API Endpoints
| Method | Endpoint | Description | Returns |
|---------|-----------|--------------|----------|
| GET | `/search?q={query}&top_k={n}` | Retrieve top n chunks for a query | 200 OK + JSON |
| GET | `/health` | Health check | 200 OK |

## Events
- **Consumes:** `ChunksIndexed`
- **Publishes:** `RetrievalCompleted`

## Talks To
- RabbitMQ (event broker)
- Indexing Service (vector store)
- Hybrid search engine (Tier-2 feature)