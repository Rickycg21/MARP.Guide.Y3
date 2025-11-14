# MARP-Guide Chatbot — Sprint Log

This document records the sprint planning, progress, and outcomes for the MARP-Guide project.  
It focuses on **Sprint 1 (Weeks 1–5)** — the first increment required by the assessment:  
> “Core RAG Pipeline” — functional microservices architecture, event-driven communication, and basic RAG capability (≥1 citation).

---

## Sprint Overview

| Sprint | Duration | Sprint Goal | Status |
|--------|------------|--------------|---------|
| **Sprint 1** | Week 1 → Week 5 | Deliver a fully functional **RAG pipeline** connecting ingestion → extraction → indexing → retrieval → chat, with working events and Docker deployment. | Completed |

---

## Sprint Goal

> Implement the end-to-end data flow from MARP document ingestion to generating an answer with one citation using the RAG architecture.  
> All core services must run in Docker Compose and communicate asynchronously through RabbitMQ.

---

## Sprint Backlog

### Completed Items (Sprint 1)
| Epic | ID | Task | Responsible | Status | Notes |
|------|----|-------|--------------|---------|-------|
| **Ingestion** | ING-1 | Discover MARP PDF URLs | Youssef, Dominik | ✅ | Automatic discovery from university site implemented |
|  | ING-2 | Download PDFs and store metadata | Youssef, Dominik | ✅ | PDFs saved under `/data/text/` |
|  | ING-3 | Publish `DocumentDiscovered` event | Youssef | ✅ | Event schema created and tested |
|  | TEST-ING | Unit tests for ingestion workflow | - | 🔜 | Basic endpoint and event tests added (pytest) |
| **Extraction** | EXT-1 | Parse PDFs into clean text | Youssef, Ricardo | ✅ | Implemented using pdfplumber |
|  | EXT-2 | Store extracted text as JSON | Youssef, Ricardo | ✅ | JSON output ready for Indexing |
|  | EXT-3 | Publish `DocumentExtracted` event | Youssef, Ricardo | ✅ | Event triggers Indexing workflow |
|  | TEST-EXT | Unit tests for extraction logic | - | 🔜 | Verified text parsing and event emission |
| **Indexing** | IDX-1 | Implement chunking strategy | Diego | ✅ | Custom chunking (~450 tokens, 50 overlap) |
|  | IDX-2 | Generate embeddings | Diego | ✅ | Using `sentence-transformers` model |
|  | IDX-3 | Store embeddings in ChromaDB | Diego | ✅ | Embedded vectors saved with metadata |
|  | IDX-4 | Publish `ChunksIndexed` event | Diego | ✅ | Triggers Retrieval service |
|  | TEST-IDX | Unit tests for chunking & embedding pipeline | Diego | 🔄 | Coverage for pipeline flow and endpoints |
| **Retrieval** | RET-1 | Implement `/search` endpoint | Ricardo | ✅ | Returns top-k chunks with metadata |
|  | RET-2 | Include page number + title + URL | Ricardo | ✅ | Ensures full citation data |
|  | RET-3 | Publish `RetrievalCompleted` event | Ricardo | ✅ | Forwarded to Monitoring service |
|  | TEST-RET | Unit tests for retrieval API | - | 🔜 | Verified ranking logic and response formatting |
| **RAG Chat** | RAG-1 | Implement `/chat` endpoint | Dominik | ✅ | Integrated OpenRouter API |
|  | RAG-2 | Prompt engineering | Dominik | ✅ | Ensures citation format |
|  | RAG-3 | Generate answers with ≥1 citation | Dominik | ✅ | Basic RAG pipeline functional |
|  | RAG-5 | Publish `AnswerGenerated` event | Dominik | ✅ | Final event completes workflow |
|  | TEST-RAG | Unit tests for RAG response builder | - | 🔜 | Covered prompt assembly and LLM call simulation |
| **Infrastructure** | INF-1 | Docker Compose setup | Diego, Youssef | ✅ | Verified multi-service startup |
|  | INF-2 | RabbitMQ integration | Youssef | ✅ | Fully connected via AMQP |
|  | INF-5a | Service documentation under `/docs/services` | All | ✅ | Includes architecture, services descriptions |
|  | INF-5b | Project documentation under `/docs` | Youssef, Diego | ✅ | Contains Scrum artefacts, markdown deliverables |
|  | TEST-INF | Basic service health & container tests | All | ✅ | Smoke tests confirm all services reachable |


---

### In Progress / Carry-Over (to Sprint 2)
| Epic | ID | Task | Responsible | Status | Notes |
|------|----|-------|--------------|---------|-------|
| **Monitoring** | MON-2 | Event counter metrics | - | 🔜 | Planned for Assessment 2 |
| **Infrastructure** | INF-3 | Add automated tests | All | 🔜 | Planned for Assessment 2 |
| **Infrastructure** | INF-4 | GitHub Actions CI pipeline | Diego | 🔄 | CI tests being implemented |
| **Monitoring** | MON-3 | `/metrics` endpoint | - | 🔜 | Planned for Assessment 2 |
| **RAG Chat** | RAG-4 | Generate answers with ≥2 citations | - | 🔜 | Planned for Assessment 2 |
| **UX Interface** | UX-1 | Build chat UI (React) | - | 🔜 | Planned for Assessment 2 |
| **UX Interface** | UX-2 | Add feedback feature | - | 🔜 | Planned for Assessment 2 |

---

## Sprint Progress Summary

- **Total planned items:** 33  
- **Completed:** 26 ✅  
- **In progress:** 2 🔄  
- **Planned (next sprint):** 5 🔜  

Overall sprint completion: **≈75% functional coverage achieved.**  
Core RAG pipeline successfully implemented across all services.  
Unit tests initiated for each component; full automation and CI integration scheduled for Sprint 2.

---

## Review Summary

- All core services communicate via network interfaces (HTTP + RabbitMQ).  
- Events (`DocumentDiscovered`, `DocumentExtracted`, `ChunksIndexed`, `RetrievalCompleted`, `AnswerGenerated`) validated end-to-end.  
- Docker Compose confirmed operational with `docker compose up`.  
- Monitoring and testing to be expanded in Sprint 2.

---

_Last updated: November 2025_  
_Team: MARP.Guide.Y3 — Diego Laforet Fernández, Ricardo Coll González, Dominik Turowski, Youssef Bahaa._







