# Monitoring Service

## Responsibility
Aggregate and display system health, service metrics, and event throughput for the entire RAG pipeline.

## Data Owned
- `/data/metrics/events.log` — append-only event log capturing all consumed events for traceability
- `/data/metrics/counters.json` — aggregated service metrics (health_status{}, event_counts{}, avg_latency_ms{})

## API Endpoints
| Method | Endpoint | Description | Returns |
|---------|-----------|--------------|----------|
| GET | `/metrics` | Return aggregated service metrics | 200 OK + JSON |
| GET | `/monitor` | Simple web UI showing status per service | 200 OK + HTML |
| GET | `/health` | Health check | 200 OK |

## Events
- **Consumes:** `RetrievalCompleted` & `AnswerGenerated`
- **Publishes:** *(none)*

## Talks To
- RabbitMQ (event broker)
- All other services (via /health and /metrics polling)
- Persistent volume (`/data`)