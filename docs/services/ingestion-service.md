# Ingestion Service

## Responsibility
Discover, download, and register MARP guideline PDFs from the source website.  
Publishes metadata about newly fetched documents to the extraction service.

## Data Owned
- `data/pdfs/` — Raw PDF files referenced by *DocumentDiscovered.payload.downloadPath*
- `data/pdf_metadata.jsonl` — PDF metadata (document_id, title, url, download_path, pages, discovered_at)

## API Endpoints
| Method | Endpoint | Description | Returns |
|---------|-----------|--------------|----------|
| POST | `/discover` | Trigger discovery & download job | 202 Accepted |
| GET | `/documents` | List all discovered documents | 200 OK + JSON |
| GET | `/health` | Health check | 200 OK |

## Events
- **Publishes:** `DocumentDiscovered`
- **Consumes:** *(none)*

## Communicates With
- RabbitMQ (event broker)
- Local `data/` folder
- MARP source site