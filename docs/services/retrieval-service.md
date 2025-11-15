# Retrieval Service

## Responsibility

Perform semantic-BM25 hybrid searches over the indexed content, returning ranked chunks for question answering.
Publish a RetrievalCompleted event with a compact summary of the results.
Append a query metadata to `/data/query_metadata.jsonl` for analytics/debugging.

## Data Owned

- `/data/query_metadata.jsonl` — query metadata (query_id, query_text, mode, top_k, retrieval_time_ms, results[document_id, chunk_id, page, title, url, scores{semantic, bm25, combined}])

## API Endpoints

| Method | Endpoint  | Description                        | Returns       |
| ------ | --------- | ---------------------------------- | ------------- |
| GET    | `/search` | Retrieve ranked chunks for a query | 200 OK + JSON |
| GET    | `/health` | Health check                       | 200 OK        |

## Events

- **Consumes:** _(none)_
- **Publishes:** `RetrievalCompleted`

## Communicates With

- RabbitMQ (event broker)
- Local filesystem — appends query logs to /data/query_metadata.jsonl
- ChromaDB (Vector DB) — on-disk store at /data/index/
