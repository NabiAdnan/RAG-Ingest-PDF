# Deploying RAG-Ingest-PDF (full Inngest + Qdrant setup)

The shareable link is the Streamlit app. Behind it there are four pieces,
all kept from the original architecture: Streamlit (UI) -> Inngest (workflow)
-> FastAPI backend (chunk / embed / answer) -> Qdrant Cloud (vectors) +
Gemini (embeddings + answers).

No real keys are in this repo. Every secret below is entered in the
host's dashboard, by the repo owner.

## 1. Qdrant Cloud (free cluster)

1. Create a free cluster at Qdrant Cloud.
2. Copy its cluster URL and API key.
3. The backend creates the `docs` collection (3072-dim, cosine) on first
   use, so you do not need to create it by hand.

## 2. Gemini API key

Create a key in Google AI Studio. It is used for embeddings
(`gemini-embedding-001`) and answers (`gemini-3.5-flash-lite`).

## 3. Inngest Cloud

1. Create an Inngest Cloud app.
2. Sync it to the backend's Inngest endpoint:
   `https://<your-backend>/api/inngest`
   (the backend must be deployed first, or use its first Render URL).
3. Copy the app's event key and signing key.

Inngest runs two functions, unchanged in purpose:

- `RAG: Ingest pdf` — chunk, embed, upsert to Qdrant
- `RAG: Query PDF AI` — embed the question, search Qdrant, answer with Gemini

## 4. Render (backend + Streamlit app)

1. In Render: New -> Blueprint, select this repo and the deploy branch.
2. Fill in the secrets from `render.yaml`:
   - Backend: `GEMINI_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`,
     `INNGEST_EVENT_KEY`, `INNGEST_SIGNING_KEY`
   - Streamlit app: `INNGEST_EVENT_KEY`
3. Deploy. Copy the backend's public URL, for example
   `https://rag-ingest-backend.onrender.com`.
4. Set `RAG_BACKEND_URL` to that URL on **both** Render services and
   redeploy both. This is what lets a query answer travel back from the
   Inngest function, via the backend, to the Streamlit app. Without it,
   Streamlit falls back to polling a local Inngest dev server, which
   does not exist when deployed.
5. The Streamlit app's URL is the link to share.

## 5. Test it live

1. Open the Streamlit link, upload a PDF, wait for the ingestion
   confirmation.
2. Ask a question that is answered in that PDF. You should get a
   grounded answer plus the source filename.
3. If a question times out, check in order: Render backend logs,
   Inngest Cloud run history, Qdrant Cloud cluster status, then whether
   `RAG_BACKEND_URL` is set on both services.

## Notes and limits

- This is a demo deployment, not a production system: query answers are
  held in the backend's in-memory result store, so a backend restart
  clears pending answers, and uploaded PDFs are not kept long-term.
  The Inngest functions, Qdrant vectors, and Gemini calls are the real
  pipeline; only the answer hand-back is a demo shortcut.
- Local development is unchanged: leave `INNGEST_PRODUCTION` unset and
  run Qdrant locally plus the Inngest dev server, as in the original
  `.gitignore` notes.
- `requirements.txt` is the original Windows pip freeze and includes
  `pywin32`, which fails on Linux hosts. Deployments use
  `requirements-deploy.txt` instead.
