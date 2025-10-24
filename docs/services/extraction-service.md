# Extraction Service

## Responsibility
Convert downloaded PDFs into structured text and metadata.  
Publishes extraction results to indexing service.

## Data Owned
- `/data/text/` — extracted plain text files per PDF referenced by *DocumentExtracted.data.text_path*
- `text_metadata.jsonl` — per-document extraction metadata (document_id, page_count, token_count, extracted_by, extracted_at)

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
