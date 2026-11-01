# 🚀 RAG Production App

A production-oriented **Retrieval-Augmented Generation (RAG)** application that allows users to upload PDF documents and ask natural-language questions about their content.

The application processes PDF documents, splits them into meaningful chunks, generates vector embeddings using **Google Gemini**, stores them in **Qdrant**, retrieves the most relevant chunks for a user's question, and uses a Gemini generative model to produce a context-aware answer.

The workflow is orchestrated using **Inngest**, while **FastAPI** provides the backend API and **Streamlit** provides the interactive user interface.

## Deploying

See [DEPLOY.md](DEPLOY.md) for the full Inngest + Qdrant Cloud + Render
setup and the shareable Streamlit link. Deployments use
`requirements-deploy.txt`, not the original Windows `requirements.txt`.

---

## 📌 Overview

Traditional LLM applications can generate answers based only on the information contained in the model's training data. This becomes a limitation when users want to ask questions about their own documents.

This project solves that problem using a RAG pipeline.

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
