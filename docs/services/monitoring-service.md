# Monitoring Service

## Responsibility
Provide a Basic Monitoring Dashboard (Tier 1 Feature) that aggregates service health, pipeline event statistics, indexing progress, and request counts.
It consumes all events produced by the RAG pipeline and exposes a small dashboard showing live system metrics.

## Data Owned
- `/data/metrics/events.log` — append-only event log
- `/data/metrics/counters.json` — aggregated service metrics (health_status{}, event_counts{}, avg_latency_ms{})

## API Endpoints
| Method | Endpoint | Description | Returns |
|---------|-----------|--------------|----------|
| GET | `/metrics` | Return aggregated service metrics | 200 OK + JSON |
| GET | `/monitor` | Simple web UI showing status per service | 200 OK + HTML |
| GET | `/health` | Health check | 200 OK |

## Events
- **Consumes:** `DocumentDiscovered`, `DocumentExtracted`, `ChunksIndexed`, `RetrievalCompleted`, `AnswerGenerated`
- **Publishes:** *(none)*

## Communicates With
- RabbitMQ (event broker)
- Local `data/` folder