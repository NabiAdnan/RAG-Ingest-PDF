#  RAG Production App

[![Live Demo](https://img.shields.io/badge/Live%20Demo-rag--ingest--app.onrender.com-brightgreen)](https://rag-ingest-app.onrender.com)
[![Python](https://img.shields.io/badge/Python-3.14-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.64-FF4B4B)](https://streamlit.io/)
[![Qdrant](https://img.shields.io/badge/Qdrant-Cloud-DC2440)](https://qdrant.tech/)
[![Inngest](https://img.shields.io/badge/Inngest-Orchestration-5B5BD6)](https://www.inngest.com/)

Upload a PDF, ask a question about it, and get an answer grounded in that document, with the source file shown. No setup needed to try it.

##  Live Demo

**[rag-ingest-app.onrender.com](https://rag-ingest-app.onrender.com)**

1. Upload a PDF.
2. Wait for the ingestion confirmation.
3. Ask a question about the document. You will get a concise, context-only answer plus the source filename.

> The demo runs on Render's free tier, so the first load after idle can take about a minute to wake up. Large PDFs work too, including multi-hundred-KB reports. The demo uses a shared collection, so please don't upload sensitive documents.

Backend health check: https://rag-ingest-backend.onrender.com/health

##  Features

- **PDF ingestion** — upload a PDF and it is chunked, embedded, and stored for retrieval.
- **Grounded answers** — answers use only the retrieved context. If the answer isn't in the documents, it says so instead of guessing.
- **Source attribution** — every answer lists the source PDF(s) it came from.
- **Async orchestration** — ingestion and querying run as Inngest functions, not blocking request handlers.
- **Large-file safe** — uploads go to the backend first over HTTP, so they aren't limited by Inngest's 256KB event size. Only a small file reference travels through Inngest.

##  How it works

**Ingestion**

1. Streamlit uploads the PDF to the FastAPI backend (`POST /api/uploads`).
2. An Inngest event (`rag/ingest_pdf`) triggers the ingest function with the backend-local file path.
3. LlamaIndex reads and chunks the PDF, Gemini creates embeddings, and Qdrant stores the vectors with their source and text.

**Asking a question**

1. Streamlit sends an Inngest event (`rag/query_pdf_ai`) with the question and a result ID.
2. The query function embeds the question, searches Qdrant for the most relevant chunks, and asks Gemini to answer using only that context.
3. The backend hands the answer back (`/api/results/{result_id}`) and Streamlit displays it with its sources.

##  Tech stack

| Layer | Technology |
| --- | --- |
| UI | Streamlit |
| API | FastAPI + Uvicorn |
| Orchestration | Inngest |
| Embeddings / LLM | Google Gemini (`gemini-embedding-001`, `gemini-3.5-flash-lite`) |
| Vector database | Qdrant Cloud |
| PDF parsing / chunking | LlamaIndex |

##  Run locally

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in GEMINI_API_KEY, QDRANT_URL, QDRANT_API_KEY
```

Start the Inngest dev server, then the backend and the Streamlit app:

```bash
uvicorn main:app --reload
streamlit run streamlit_app.py
```

Local dev keeps the original behaviour: `INNGEST_PRODUCTION` unset, local Inngest dev server, and Qdrant on `localhost:6333` unless the env vars above are set.

## ☁️ Deploying

The deployed code lives on the [`deploy/render-inngest-qdrant`](https://github.com/NabiAdnan/RAG-Ingest-PDF/tree/deploy/render-inngest-qdrant) branch, with the full Inngest + Qdrant Cloud + Render setup in its `DEPLOY.md`. That branch uses `requirements-deploy.txt` for Linux hosts, instead of this branch's original Windows `requirements.txt`.

Deployed services:

- App (Streamlit): https://rag-ingest-app.onrender.com
- Backend (FastAPI): https://rag-ingest-backend.onrender.com
- Inngest sync URL: https://rag-ingest-backend.onrender.com/api/inngest

---

##  Why RAG?

Traditional LLM applications can only answer from their training data. That breaks when you want to ask questions about your own documents. This project solves that by retrieving the relevant passages first, then generating an answer strictly from them.

### RAG Pipeline

```text
                    ┌──────────────────┐
                    │   User Uploads   │
                    │       PDF        │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │    PDFReader     │
                    │   LlamaIndex     │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Text Chunking    │
                    │ SentenceSplitter │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Gemini Embeddings│
                    │                  │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │     Qdrant       │
                    │ Vector Database   │
                    └──────────────────┘


User Question
      │
      ▼
┌──────────────────┐
│ Gemini Embedding │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Qdrant Similarity│
│     Search       │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Relevant Context │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│   Gemini LLM     │
│ Context-Aware    │
│    Response      │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Streamlit UI     │
│     Answer       │
└──────────────────┘
```
