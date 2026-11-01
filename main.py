import base64
import logging
import tempfile
from pathlib import Path
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
import inngest
import inngest.fast_api
from inngest.experimental import ai
import requests
import uuid
import datetime
from data_loader import load_and_chunk_pdf, embed_texts
from vector_db import QdrantStorage
from custom_types import RAGChunkAndSrc,RAGUpsertResult,RAGSearchResult,RAGQueryResult


load_dotenv()  # Load environment variables from .env file

gemini_client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

# Deploy: set INNGEST_PRODUCTION=true and the Inngest event/signing keys
# in the host dashboard (the SDK reads INNGEST_EVENT_KEY /
# INNGEST_SIGNING_KEY from the environment). Local dev keeps the old
# behaviour: is_production=False, talking to the local Inngest dev server.
INNGEST_PRODUCTION = os.getenv("INNGEST_PRODUCTION", "false").lower() == "true"
# Public URL of this backend, e.g. https://rag-ingest-backend.onrender.com.
# Used only so the query function can hand its answer back to the
# Streamlit app (see the result endpoints below). Unset locally.
RAG_BACKEND_URL = os.getenv("RAG_BACKEND_URL", "").rstrip("/")

inngest_client = inngest.Inngest(
    app_id="rag_app",
    logger=logging.getLogger("uvicorn"),
    is_production=INNGEST_PRODUCTION,
    serializer=inngest.PydanticSerializer()
)


@inngest_client.create_function(
    fn_id="RAG: Ingest pdf",
    trigger=inngest.TriggerEvent(event="rag/ingest_pdf"),
    
)
async def rag_ingest_pdf(ctx: inngest.Context):
    def _load(ctx: inngest.Context) -> RAGChunkAndSrc:
        # Deploy: Streamlit and this backend run in different containers,
        # so a Streamlit-local file path does not exist here. The deployed
        # Streamlit app therefore either (a) uploads the PDF to this
        # backend first (/api/uploads) and sends the backend-local
        # pdf_path, or (b) for small files only, sends the PDF as base64
        # (pdf_content_b64) and this step writes it to a temp file here.
        # (b) fails on Inngest Cloud for files over ~192KB: base64
        # inflates the event past Inngest's 262144-byte event limit, so
        # (a) is the normal deployed path. Local dev: a pdf_path event
        # still loads that path.
        pdf_b64 = ctx.event.data.get("pdf_content_b64")
        source_id = ctx.event.data.get("source_id")
        if pdf_b64:
            pdf_bytes = base64.b64decode(pdf_b64)
            suffix = ".pdf"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(pdf_bytes)
                pdf_path = tmp.name
            source_id = source_id or ctx.event.data.get("pdf_path", "uploaded.pdf")
        else:
            pdf_path = ctx.event.data["pdf_path"]
            source_id = source_id or pdf_path
        chunks=load_and_chunk_pdf(pdf_path)
        return  RAGChunkAndSrc(chunks=chunks, source_id=source_id)

    def _upsert(chunk_and_src: RAGChunkAndSrc) -> RAGUpsertResult:
        chunks=chunk_and_src.chunks
        source_id=chunk_and_src.source_id
        vecs=embed_texts(chunks)
        
        ids= [str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}_{i}")) for i in range(len(chunks))]
        payloads=[{"source": source_id, "text": chunks[i]} for i in range(len(chunks))]
        QdrantStorage().upsert(ids, vecs, payloads)
        return RAGUpsertResult(ingested=len(chunks))

    chunks_and_src = await ctx.step.run("load-and-chunk", lambda: _load(ctx),output_type=RAGChunkAndSrc)
    ingested = await ctx.step.run("embed-and-upsert", lambda: _upsert(chunks_and_src),output_type=RAGUpsertResult)
    return ingested.model_dump()



@inngest_client.create_function(
    fn_id="RAG: Query PDF AI",
    trigger=inngest.TriggerEvent(event="rag/query_pdf_ai")
)
async def rag_query_pdf_ai(ctx: inngest.Context):

    def _search(
        question: str,
        top_k: int = 5
    ) -> RAGSearchResult:

        query_vec = embed_texts([question])[0]

        store = QdrantStorage()

        found = store.search(
            query_vec,
            top_k
        )

        return RAGSearchResult(
            contexts=found["contexts"],
            sources=found["sources"]
        )

    question = ctx.event.data["question"]
    top_k = int(ctx.event.data.get("top_k", 5))

   

    found = await ctx.step.run(
        "embed-and-search",
        lambda: _search(question, top_k),
        output_type=RAGSearchResult
    )

    
    context_blocks = "\n\n".join(
        f"- {c}"
        for c in found.contexts
    )

    user_content = (
        "Use the following context to answer the question. "
        "If the context does not contain the answer, say "
        "'I don't know'.\n\n"
        f"Context:\n{context_blocks}\n\n"
        f"Question: {question}\n"
        "Answer concisely using only the context above."
    )

    

    response_text = await ctx.step.run(
        "llm-answer",
        lambda: gemini_client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You answer questions using only the provided context. "
                    "If the answer is not present in the context, say "
                    "'I don't know'."
                ),
                temperature=0.2,
                max_output_tokens=1024,
            )
        ).text
    )

    answer = response_text.strip()

    result = {
        "answer": answer,
        "sources": found.sources,
        "num_contexts": len(found.contexts)
    }

    # Deploy: the deployed Streamlit app cannot poll the local Inngest
    # dev server, so the function hands its answer back to this backend
    # (if RAG_BACKEND_URL is set) and Streamlit polls this backend.
    # Local dev: RAG_BACKEND_URL is unset, so this is skipped and
    # Streamlit keeps polling the dev server exactly as before.
    result_id = ctx.event.data.get("result_id")
    if result_id and RAG_BACKEND_URL:
        try:
            requests.post(
                f"{RAG_BACKEND_URL}/api/results/{result_id}",
                json=result,
                timeout=10,
            )
        except Exception:
            # The Inngest return value below is still the record of
            # the run; a failed callback must not fail the answer.
            pass

    return result

 
app=FastAPI()


# In-memory result store for deployed query polling. This is a demo
# store: results live only while this backend process is running.
# (Render's free tier may restart the service, which clears it.)
_query_results: dict[str, dict] = {}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"status": "ok", "app": "rag_app"}


@app.post("/api/results/{result_id}")
def store_result(result_id: str, result: dict):
    _query_results[result_id] = result
    return {"stored": True}


# Uploaded PDFs live in this backend container, so the Inngest function
# (which also runs against this backend) can read them by path. This
# endpoint is what makes large PDFs work: the file bytes travel
# Streamlit -> backend over plain HTTP, and only a tiny pdf_path
# reference travels via Inngest, well under its 262144-byte event limit.
# Files are ephemeral on Render's free tier, like the result store above;
# ingestion should run soon after upload, which is the normal flow.
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.post("/api/uploads")
async def upload_pdf(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only PDF files are accepted")
    safe_name = Path(file.filename or "uploaded.pdf").name
    upload_id = str(uuid.uuid4())
    dest = UPLOAD_DIR / f"{upload_id}_{safe_name}"
    contents = await file.read()
    dest.write_bytes(contents)
    return {
        "upload_id": upload_id,
        "pdf_path": str(dest.resolve()),
        "source_id": safe_name,
        "size_bytes": len(contents),
    }


@app.get("/api/results/{result_id}")
def get_result(result_id: str):
    if result_id not in _query_results:
        raise HTTPException(status_code=404, detail="result not ready yet")
    return _query_results[result_id]


inngest.fast_api.serve(app, inngest_client, [rag_ingest_pdf, rag_query_pdf_ai])