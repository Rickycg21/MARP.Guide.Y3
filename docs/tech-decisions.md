# MARP-Guide Chatbot — Technology Decisions

This document explains the main technical choices made for the MARP-Guide RAG Chatbot and how they satisfy the assessment requirements.

---

## 1. Backend Framework

| Choice | Decision | Rationale |
|---------|-----------|-----------|
| **FastAPI** | Used in every microservice | Lightweight, async-ready Python framework ideal for building REST APIs quickly. Each service exposes `/health`, `/search`, `/chat`, etc. It runs easily inside Docker and supports automatic JSON validation. |

---

## 2. Inter-Service Communication

| Component | Decision | Rationale |
|------------|-----------|-----------|
| **HTTP (REST)** | Used for synchronous requests (e.g., Chat ↔ Retrieval, UI ↔ Chat) | Enables direct request/response when an immediate reply is required. |
| **RabbitMQ (AMQP)** | Used for asynchronous event flow between pipeline services | Event broker implementing the AMQP protocol. Provides durable queues, routing, and decoupling of microservices. Includes a web management UI at port 15672 for debugging. |

---

## 3. Vector Storage

| Component | Decision | Rationale |
|------------|-----------|-----------|
| **ChromaDB** | Local vector database for embeddings and metadata | Simple to integrate with Python as it can run in-process. Supports add/query operations used by Indexing and Retrieval. |

---

## 4. Embedding & Language Models

| Layer | Decision | Rationale |
|--------|-----------|-----------|
| **Sentence-Transformers / all-MiniLM-L6-v2** | Embedding model for vector creation | Compact (384-dim), fast, and accurate enough for academic-text retrieval. |
| **OpenRouter LLM endpoint** | External LLM for generating answers | Provides high-quality answers while keeping generation logic in our own chat service layer (no agent frameworks). |

---

## 5. PDF Processing & Utilities

| Tool | Decision | Rationale |
|------|-----------|-----------|
| **pdfplumber** | Text extraction with page mappings | Reliable, lightweight, keeps page numbers for citations. |
| **BeautifulSoup + httpx** | HTML parsing & downloading of MARP PDFs | Allows robust link discovery for the Ingestion service. |

---

## 6. Containerisation & Reproducibility

| Tool | Decision | Rationale |
|------|-----------|-----------|
| **Docker + Docker Compose** | Used to run all services and RabbitMQ | Enables the reproducibility requirement: `docker compose up` brings up the full system. Each container maps a unique host port (5001–5006). |
| **Health checks** | Implemented per service | Provides automated readiness verification and monitoring hooks. |

---

## 7. Continuous Integration (CI)

| Tool | Decision | Rationale |
|------|-----------|-----------|
| **GitHub Actions** | Workflow `.github/workflows/ci.yml` | Runs unit tests on every Pull Request to maintain quality. |

---
