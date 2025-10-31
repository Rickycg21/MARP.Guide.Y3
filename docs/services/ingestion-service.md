# Ingestion Service

## Responsibility
Discover, download, and register MARP guideline PDFs from the source website.  
Publishes metadata about newly fetched documents to extraction service.

## Data Owned
- `/data/pdfs/` — Raw PDF files referenced by *DocumentDiscovered.data.download_path*
- `/data/pdf_metadata.jsonl` - PDF metadata (document_id, title, url, download_path, pages, discovered_at)

## API Endpoints
| Method | Endpoint | Description | Returns |
|---------|-----------|--------------|----------|
| POST | `/discover` | Trigger discovery and download job | 202 Accepted + job ID |
| GET | `/documents` | List all discovered documents | 200 OK + JSON array |
| GET | `/health` | Health check | 200 OK |

## Events
- **Publishes:** `DocumentDiscovered`
- **Consumes:** *(none)*

## Talks To
- RabbitMQ (event broker)
- Persistent volume (`/data`)
- MARP document source