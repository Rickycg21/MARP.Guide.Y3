# Chat Service

## Responsibility
Provide conversational interface that answers user questions using retrieved chunks and LLM completions.

## Data Owned
*(none)*

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
- Retrieval Service
- OpenAI LLM API (via service layer)
