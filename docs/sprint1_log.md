# 🗓️ MARP-Guide Chatbot — Sprint Log

This document records the sprint planning, progress, and outcomes for the MARP-Guide project.  
It focuses on **Sprint 1 (Weeks 1–5)** — the first increment required by the assessment:  
> “Core RAG Pipeline” — functional microservices architecture, event-driven communication, and basic RAG capability (≥1 citation).

---

## 🧭 Sprint Overview

| Sprint | Duration | Sprint Goal | Status |
|--------|------------|--------------|---------|
| **Sprint 1** | Week 1 → Week 5 | Deliver a fully functional **RAG pipeline** connecting ingestion → extraction → indexing → retrieval → chat, with working events and Docker deployment. | ✅ Completed |

---

## 🎯 Sprint Goal

> Implement the end-to-end data flow from MARP document ingestion to generating an answer with one citation using the RAG architecture.  
> All core services must run in Docker Compose and communicate asynchronously through RabbitMQ.

---

## 📅 Sprint Backlog

### ✅ Completed Items (Sprint 1)
| Epic | ID | Task | Responsible | Status | Notes |
|------|----|-------|--------------|---------|-------|
| **Ingestion** | ING-1 | Discover MARP PDF URLs | Ricardo | ✅ | Automatic discovery from university site implemented |
|  | ING-2 | Download PDFs and store metadata | Ricardo | ✅ | PDFs saved under `/data/text/` |
|  | ING-3 | Publish `DocumentDiscovered` event | Ricardo | ✅ | Event schema created and tested |
| **Extraction** | EXT-1 | Parse PDFs into clean text | Diego | ✅ | Implemented using pdfplumber |
|  | EXT-2 | Store extracted text as JSON | Diego | ✅ | JSON output ready for Indexing |
|  | EXT-3 | Publish `DocumentExtracted` event | Diego | ✅ | Event triggers Indexing workflow |
| **Indexing** | IDX-1 | Implement chunking strategy | Diego | ✅ | Custom chunking (~450 tokens, 50 overlap) |
|  | IDX-2 | Generate embeddings | Diego | ✅ | Using `sentence-transformers` model |
|  | IDX-3 | Store embeddings in ChromaDB | Diego | ✅ | Embedded vectors saved with metadata |
|  | IDX-4 | Publish `ChunksIndexed` event | Diego | ✅ | Triggers Retrieval service |
| **Retrieval** | RET-1 | Implement `/search` endpoint | Dominik | ✅ | Returns top-k chunks with metadata |
|  | RET-2 | Include page number + title + URL | Dominik | ✅ | Ensures full citation data |
|  | RET-3 | Publish `RetrievalCompleted` event | Dominik | ✅ | Forwarded to Monitoring service |
| **RAG Chat** | RAG-1 | Implement `/chat` endpoint | Youssef | ✅ | Integrated OpenRouter API |
|  | RAG-2 | Prompt engineering | Youssef | ✅ | Ensures citation format |
|  | RAG-3 | Generate answers with ≥1 citation | Youssef | ✅ | Basic RAG pipeline functional |
|  | RAG-5 | Publish `AnswerGenerated` event | Youssef | ✅ | Final event completes workflow |
| **Infrastructure** | INF-1 | Docker Compose setup | All | ✅ | Verified multi-service startup |
|  | INF-2 | RabbitMQ integration | Diego | ✅ | Fully connected via AMQP |
|  | INF-5 | Documentation under `/docs` | All | ✅ | Architecture, API, and Scrum artefacts ready |

---

### 🔄 In Progress / Carry-Over (to Sprint 2)
| Epic | ID | Task | Responsible | Status | Notes |
|------|----|-------|--------------|---------|-------|
| **Monitoring** | MON-2 | Event counter metrics | Diego | 🔄 | Dashboard under development |
| **Infrastructure** | INF-3 | Add automated tests | Dominik | 🔄 | Test catalogue being created |
| **Infrastructure** | INF-4 | GitHub Actions CI pipeline | Dominik | 🔄 | CI config draft complete |
| **Monitoring** | MON-3 | `/metrics` endpoint | Youssef | 🔄 | Planned for Assessment 2 |
| **RAG Chat** | RAG-4 | Generate answers with ≥2 citations | Youssef | 🔜 | Scheduled for next sprint |
| **UX Interface** | UX-1 | Build chat UI (React) | Ricardo | 🔜 | Next increment |
| **UX Interface** | UX-2 | Add feedback feature | Ricardo | 🔜 | Low priority for final polish |

---

## 📈 Sprint Progress Summary

- **Total planned items:** 28  
- **Completed:** 21 ✅  
- **In progress:** 4 🔄  
- **Planned (next sprint):** 3 🔜  

Overall sprint completion: **~75% functional coverage achieved**.  
Core RAG pipeline delivered and integrated successfully.

---

## 💬 Review Summary

- All core services communicate via network interfaces (HTTP + RabbitMQ).  
- Events (`DocumentDiscovered`, `DocumentExtracted`, `ChunksIndexed`, `RetrievalCompleted`, `AnswerGenerated`) validated end-to-end.  
- Docker Compose confirmed operational with `docker compose up`.  
- Monitoring and testing to be expanded in Sprint 2.

---

_Last updated: November 2025_  
_Team: MARP.Guide.Y3 — Diego Laforet Fernández, Ricardo Coll González, Dominik Turowski, Youssef Bahaa._
