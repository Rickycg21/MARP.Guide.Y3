# Extraction Service

## Responsibility
Convert downloaded PDFs into structured text and metadata.  
Publishes extraction results to indexing service.

## Data Owned
- `/data/text/` — extracted plain text per PDF
- `text_metadata.jsonl` — extraction metadata

## API Endpoints
| Method | Endpoint | Description | Returns |
|---------|-----------|--------------|----------|
| POST | `/extract/{document_id}` | Run extraction on a specific document | 202 Accepted |
| GET | `/status/{document_id}` | Check extraction status | 200 OK + JSON |
| GET | `/health` | Health check | 200 OK |

## Events
- **Consumes:** `DocumentDiscovered`
- **Publishes:** `DocumentExtracted`

## Talks To
- RabbitMQ (event broker)
- Persistent volume (`/data`)
- Ingestion Service (for PDF metadata)
