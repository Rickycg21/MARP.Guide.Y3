# 🧾 MARP-Guide Chatbot — Product Backlog

This backlog lists all planned features, user stories, and technical tasks for the MARP-Guide system.  
It is structured by epics (Ingestion, Extraction, Indexing, Retrieval, RAG Chat, Monitoring, Infrastructure).  
Each item includes a short description, priority, and current status.

---

## 🏁 Product Goal
> Build a chat application that can accurately answer questions about Lancaster University’s MARP (Manual of Academic Regulations and Procedures) using a Retrieval-Augmented Generation (RAG) pipeline — with correct citations (title, page, and link).

---

## 📦 Epics & Stories

### 🧩 EPIC 1 — Ingestion Service
| ID | User Story / Task | Description | Priority | Status |
|----|-------------------|--------------|-----------|---------|
| ING-1 | Discover MARP PDF URLs | Automatically discover all MARP-related PDFs from the official Lancaster website. | High | ✅ Done |
| ING-2 | Download PDFs | Fetch and store all discovered MARP PDFs locally with metadata (URL, title, date). | High | ✅ Done |
| ING-3 | Publish `DocumentDiscovered` event | Notify the Extraction service when a new document is fetched. | High | ✅ Done |
| ING-4 | Implement `/discover` endpoint | Allow manual triggering of discovery process via API. | Medium | ✅ Done |

---

### 📄 EPIC 2 — Extraction Service
| ID | User Story / Task | Description | Priority | Status |
|----|-------------------|--------------|-----------|---------|
| EXT-1 | Parse PDFs to text | Convert PDFs into clean, per-page text using PyPDF2/pdfplumber. | High | ✅ Done |
| EXT-2 | Store extracted text as JSON | Save structured text and metadata for downstream services. | High | ✅ Done |
| EXT-3 | Publish `DocumentExtracted` event | Notify Indexing service after successful extraction. | High | ✅ Done |
| EXT-4 | Implement health endpoint | Provide `/health` for Docker Compose checks. | Low | ✅ Done |

---

### 🧠 EPIC 3 — Indexing Service
| ID | User Story / Task | Description | Priority | Status |
|----|-------------------|--------------|-----------|---------|
| IDX-1 | Implement chunking strategy | Split extracted text into semantic chunks (~450 tokens, 50 overlap). | High | ✅ Done |
| IDX-2 | Generate embeddings | Use `sentence-transformers` to create dense vector representations. | High | ✅ Done |
| IDX-3 | Store embeddings in ChromaDB | Save chunks + vectors with metadata. | High | ✅ Done |
| IDX-4 | Publish `ChunksIndexed` event | Notify Retrieval service when vectors are stored. | High | ✅ Done |
| IDX-5 | Test indexing workflow | Ensure end-to-end indexing pipeline runs correctly. | Medium | 🔄 In progress |

---

### 🔍 EPIC 4 — Retrieval Service
| ID | User Story / Task | Description | Priority | Status |
|----|-------------------|--------------|-----------|---------|
| RET-1 | Implement `/search` endpoint | Return top-k relevant chunks given a query embedding. | High | ✅ Done |
| RET-2 | Handle metadata and ranking | Include page number, title, and URL in each result. | High | ✅ Done |
| RET-3 | Publish `RetrievalCompleted` event | Notify Monitoring/Chat when retrieval is finished. | Medium | ✅ Done |
| RET-4 | Support hybrid search (BM25 + dense) | Tier-2 feature for Assessment 2. | Medium | 🔜 Planned |

---

### 💬 EPIC 5 — RAG Chat Service
| ID | User Story / Task | Description | Priority | Status |
|----|-------------------|--------------|-----------|---------|
| RAG-1 | Implement `/chat` endpoint | Accept a query and build the RAG pipeline response. | High | ✅ Done |
| RAG-2 | Prompt engineering | Design LLM prompt templates ensuring citations are included. | High | ✅ Done |
| RAG-3 | Generate answers with ≥1 citation | Assessment 1 requirement. | High | ✅ Done |
| RAG-4 | Generate answers with ≥2 citations | Final MVP requirement. | High | 🔜 Planned |
| RAG-5 | Publish `AnswerGenerated` event | Notify Monitoring service. | Medium | ✅ Done |

---

### 📊 EPIC 6 — Monitoring (Tier 1 Feature)
| ID | User Story / Task | Description | Priority | Status |
|----|-------------------|--------------|-----------|---------|
| MON-1 | Health checks dashboard | Display `/health` status of all services. | Medium | ✅ Done |
| MON-2 | Event counter metrics | Track number of processed events by type. | Medium | 🔄 In progress |
| MON-3 | REST API for `/metrics` | Expose metrics for Grafana or CI integration. | Low | 🔜 Planned |

---

### ⚙️ EPIC 7 — Infrastructure & CI/CD
| ID | User Story / Task | Description | Priority | Status |
|----|-------------------|--------------|-----------|---------|
| INF-1 | Docker Compose setup | All services start and connect via `docker compose up`. | High | ✅ Done |
| INF-2 | Implement RabbitMQ broker | Setup AMQP queues for inter-service communication. | High | ✅ Done |
| INF-3 | Add automated tests | Minimum 10–15 unit/integration tests. | High | 🔜 Planned |
| INF-4 | GitHub Actions CI pipeline | Run tests automatically on push. | Medium | 🔜 Planned |
| INF-5 | Documentation under `/docs` | Architecture, API specs, events, Scrum artefacts. | High | ✅ Done |

---

### 🧭 EPIC 8 — UX & Chat Interface (Tier 2 Feature)
| ID | User Story / Task | Description | Priority | Status |
|----|-------------------|--------------|-----------|---------|
| UX-1 | Build chat UI (React) | Simple interface for sending questions and showing answers + citations. | Medium | 🔜 Planned |
| UX-2 | Add feedback option | Allow user thumbs-up/down feedback for answers. | Low | 🔜 Planned |

---

## 🧩 Definition of Done
- Code implemented, reviewed, and merged into `develop` branch.  
- Service runs in Docker Compose with health check passing.  
- Event published and consumed successfully.  
- Documentation updated in `/docs/`.  
- All tests passing (where applicable).

---

_Last updated: November 2025_  
_Team: MARP.Guide.Y3 — Diego Laforet Fernández, Ricky C., and team members_

