# Monitoring Service

## Responsibility
Aggregate and display system health, service metrics, and event throughput for the entire RAG pipeline.

## Data Owned
- `/data/metrics/` — service metrics snapshots

## API Endpoints
| Method | Endpoint | Description | Returns |
|---------|-----------|--------------|----------|
| GET | `/metrics` | Return aggregated service metrics | 200 OK + JSON |
| GET | `/monitor` | Simple web UI showing status per service | 200 OK + HTML |
| GET | `/health` | Health check | 200 OK |

## Events
- **Consumes:** `AnswerGenerated`
- **Publishes:** *(none)*

## Talks To
- RabbitMQ (event broker)
- All other services (via /health and /metrics polling)
- Persistent volume (`/data`)