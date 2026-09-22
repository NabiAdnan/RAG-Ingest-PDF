import logging
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv
from fastapi import FastAPI
import inngest
import inngest.fast_api
from inngest.experimental import ai
import uuid
import datetime
from data_loader import load_and_chunk_pdf, embed_texts
from vector_db import QdrantStorage
from custom_types import RAGChunkAndSrc,RAGUpsertResult,RAGSearchResult,RAGQueryResult


load_dotenv()  # Load environment variables from .env file

gemini_client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

inngest_client = inngest.Inngest(
    app_id="rag_app",
    logger=logging.getLogger("uvicorn"),
    is_production=False,
    serializer=inngest.PydanticSerializer()
)


@inngest_client.create_function(
    fn_id="RAG: Ingest pdf",
    trigger=inngest.TriggerEvent(event="rag/ingest_pdf"),
    
)
async def rag_ingest_pdf(ctx: inngest.Context):
    def _load(ctx: inngest.Context) -> RAGChunkAndSrc:
        pdf_path = ctx.event.data["pdf_path"]
        source_id = ctx.event.data.get("source_id", pdf_path)
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

   
    return {
        "answer": answer,
        "sources": found.sources,
        "num_contexts": len(found.contexts)
    }

 
app=FastAPI() 


inngest.fast_api.serve(app, inngest_client, [rag_ingest_pdf, rag_query_pdf_ai])