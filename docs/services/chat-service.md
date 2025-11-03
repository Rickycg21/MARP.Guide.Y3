# Chat Service

## Responsibility
Provide conversational answers using retrieved chunks and LLM completions; orchestrates retrieval + prompting.

## Data Owned
- `/data/answer_metadata.jsonl` — answer metadata (session_id, query_id, answer, citations[], tokens_used, model, latency_ms)

## API Endpoints
| Method | Endpoint | Description | Returns |
|---------|-----------|--------------|----------|
| POST | `/chat` | Generate answer for user query | 200 OK + JSON (answer, citations) |
| GET | `/health` | Health check | 200 OK |

## Events
- **Consumes:**   *(none)*
- **Publishes:** `AnswerGenerated`

## Communicates With
- RabbitMQ (event broker)
- Local `data/` folder
- Retrieval Service (REST `/search`)
- OpenRouter LLM API (via service layer)