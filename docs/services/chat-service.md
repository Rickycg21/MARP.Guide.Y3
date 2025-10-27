# Chat Service

## Responsibility
Provide conversational interface that answers user questions using retrieved chunks and LLM completions.

## Data Owned
- `/data/answer_metadata.jsonl` — answer metadata (session_id, query_id, answer, citations[], tokens_used, model, latency_ms)

## API Endpoints
| Method | Endpoint | Description | Returns |
|---------|-----------|--------------|----------|
| POST | `/chat` | Generate answer for user query | 200 OK + JSON (answer, citations) |
| GET | `/health` | Health check | 200 OK |

## Events
- **Consumes:** `RetrievalCompleted`
- **Publishes:** `AnswerGenerated`

## Talks To
- RabbitMQ (event broker)
- Persistent volume (`/data`)
- Retrieval Service (GET /search)
- OpenRouter LLM API (via service layer)
