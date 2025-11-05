
# 🔁 MARP-Guide Chatbot — Sprint 1 Retrospective

This document summarizes the team’s reflection after completing **Sprint 1 (Weeks 1–5)** for the MARP-Guide project.  
The sprint focused on building the **Core RAG Pipeline** — delivering a working end-to-end system (Ingestion → Extraction → Indexing → Retrieval → Chat) with event-driven communication and Dockerized deployment.

---

## 🧭 Sprint Recap
**Sprint Goal:**  
> Deliver a functional, containerized RAG pipeline capable of producing answers with at least one citation,  
> fully integrated across microservices using HTTP and RabbitMQ.

**Sprint Outcome:**  
✅ Achieved.  
The full core architecture is functional and all mandatory events are implemented and exchanged successfully between services.  

---

## ✅ What Went Well

| Category | Notes |
|-----------|-------|
| **Collaboration & Communication** | The team maintained active coordination via Discord and GitHub Projects. Daily updates kept everyone aware of dependencies. |
| **Architecture Design** | Clear separation of services (Ingestion, Extraction, Indexing, Retrieval, Chat, Monitoring). Each runs independently in Docker. |
| **Event Flow Implementation** | All five key events (`DocumentDiscovered`, `DocumentExtracted`, `ChunksIndexed`, `RetrievalCompleted`, `AnswerGenerated`) were successfully integrated. |
| **Code Quality & Testing** | Each service includes health checks and local tests. The pipeline runs end-to-end without blocking errors. |
| **Documentation** | Architecture diagrams, event schemas, and API specs were clearly written under `/docs/`. |
| **Team Commitment** | Tasks were completed on time despite parallel work on multiple services. Everyone contributed code and documentation. |

---

## ⚠️ What Didn’t Go So Well

| Category | Issues Encountered |
|-----------|-------------------|
| **Integration Timing** | Some delays occurred while merging branches for Indexing and Retrieval due to overlapping dependencies. |
| **Testing Coverage** | Unit and integration testing were postponed to Sprint 2 to prioritize functionality. |
| **Monitoring Dashboard** | Metrics and visual dashboards were partially implemented, requiring further refinement. |
| **CI/CD Setup** | GitHub Actions pipeline not yet completed — test automation still manual. |
| **Time Management** | Some underestimation of debugging time during embedding generation and message queue testing. |

---

## 🚀 What to Improve Next Sprint

| Improvement Area | Action Plan |
|-------------------|-------------|
| **Testing Automation** | Develop at least 10–15 unit and integration tests across services. Integrate with GitHub Actions. |
| **Monitoring & Metrics** | Finalize `/metrics` endpoint and event counter dashboard for Assessment 2. |
| **UI Development** | Begin work on the Chat Frontend (Tier 2 feature). |
| **Hybrid Search Feature** | Implement BM25 + dense retrieval fusion for higher precision in answers. |
| **Process Efficiency** | Plan smaller, more focused tasks to reduce context switching between services. |
| **Continuous Integration** | Ensure `docker compose up` and tests run automatically after each push. |

---

## 💬 Team Reflection Quotes

> **Diego:** “Getting the embedding pipeline right was tricky, but once ChromaDB and RabbitMQ were stable, everything clicked.”  
> **Ricardo:** “The ingestion and document flow worked better than expected. Seeing events trigger downstream services in real time was rewarding.”  
> **Dominik:** “Retrieval logic was smooth — but we need more test coverage before the next sprint.”  
> **Youssef:** “Chat integration was challenging but seeing the full system answer questions was a great milestone.”

---

## 🏁 Summary

- **Sprint Success:** ✅ Core RAG pipeline delivered and integrated.  
- **Pending Tasks:** Testing, CI/CD setup, Monitoring dashboard.  
- **Team Morale:** High — confident for Sprint 2 delivery.  
- **Next Focus:** Move toward production readiness with automated testing, monitoring, and hybrid retrieval.

---

_Last updated: November 2025_  
_Team: MARP.Guide.Y3 — Diego Laforet Fernández, Ricardo Coll González, Dominik Turowski, Youssef Bahaa._
