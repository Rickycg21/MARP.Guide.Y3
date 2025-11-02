# Extraction Service

## Responsibility
Convert downloaded PDFs into structured text and metadata, then publish extraction results to indexing.

## Data Owned
- `data/text/` — Extracted plain-text files per PDF, referenced by *DocumentExtracted.payload.textPath*
- `data/text_metadata.jsonl` — Per-document extraction metadata (document_id, page_count, token_count, extracted_by, extracted_at)
- `data/text_status.jsonl` — Append-only status log (document_id, status `pending|done|error`, message)

## API Endpoints
| Method | Endpoint | Description | Returns |
|---------|-----------|--------------|----------|
| POST | `/extract/{document_id}` | Run extraction for a specific document | 202 Accepted |
| GET | `/status/{document_id}` | Latest status for one document | 200 OK + JSON |
| GET | `/status` | Status timeline for all documents | 200 OK + JSON |
| GET | `/health` | Health check | 200 OK |

## Events
- **Consumes:** `DocumentDiscovered`
- **Publishes:** `DocumentExtracted`

## Communicates With
- RabbitMQ (event broker)
- Local `data/` folder