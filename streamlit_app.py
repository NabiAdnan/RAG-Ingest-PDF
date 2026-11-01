import asyncio
import base64
from pathlib import Path
import time
import uuid

import streamlit as st
import inngest
from dotenv import load_dotenv
import os
import requests

load_dotenv()

st.set_page_config(page_title="RAG Ingest PDF", page_icon="📄", layout="centered")

# Deploy: set INNGEST_PRODUCTION=true (and INNGEST_EVENT_KEY in the host
# dashboard) plus RAG_BACKEND_URL to this app's backend service.
# Local dev: leave them unset and the old local behaviour is used.
INNGEST_PRODUCTION = os.getenv("INNGEST_PRODUCTION", "false").lower() == "true"
RAG_BACKEND_URL = os.getenv("RAG_BACKEND_URL", "").rstrip("/")


@st.cache_resource
def get_inngest_client() -> inngest.Inngest:
    return inngest.Inngest(app_id="rag_app", is_production=INNGEST_PRODUCTION)


def save_uploaded_pdf(file) -> Path:
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = uploads_dir / file.name
    file_bytes = file.getbuffer()
    file_path.write_bytes(file_bytes)
    return file_path


async def send_rag_ingest_event(file_name: str, file_bytes: bytes) -> None:
    client = get_inngest_client()
    # The backend runs in a different container when deployed, so send
    # the PDF bytes (base64) instead of a local file path. The backend
    # writes them to a temp file before chunking. Local dev works the
    # same way, so this path is identical in both environments.
    await client.send(
        inngest.Event(
            name="rag/ingest_pdf",
            data={
                "pdf_content_b64": base64.b64encode(file_bytes).decode("ascii"),
                "source_id": file_name,
            },
        )
    )


st.title("Upload a PDF to Ingest")
uploaded = st.file_uploader("Choose a PDF", type=["pdf"], accept_multiple_files=False)

if uploaded is not None:
    with st.spinner("Uploading and triggering ingestion..."):
        # Kick off the event and block until the send completes
        asyncio.run(send_rag_ingest_event(uploaded.name, uploaded.getbuffer().tobytes()))
        # Small pause for user feedback continuity
        time.sleep(0.3)
    st.success(f"Triggered ingestion for: {uploaded.name}")
    st.caption("You can upload another PDF if you like.")

st.divider()
st.title("Ask a question about your PDFs")


async def send_rag_query_event(question: str, top_k: int, result_id: str) -> str:
    client = get_inngest_client()
    result = await client.send(
        inngest.Event(
            name="rag/query_pdf_ai",
            data={
                "question": question,
                "top_k": top_k,
                # Lets the backend hand the answer back to this app
                # (see main.py); the Inngest event id is still returned
                # and used for the local-dev polling path below.
                "result_id": result_id,
            },
        )
    )

    return result[0]


def wait_for_backend_result(
    result_id: str,
    timeout_s: float = 300.0,
    poll_interval_s: float = 1.0,
) -> dict:
    """Deployed polling: ask the backend for the query function's answer."""
    start = time.time()
    while True:
        resp = requests.get(
            f"{RAG_BACKEND_URL}/api/results/{result_id}",
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code != 404:
            resp.raise_for_status()
        if time.time() - start > timeout_s:
            raise TimeoutError("Timed out waiting for the answer")
        time.sleep(poll_interval_s)


def _inngest_api_base() -> str:
    # Local dev server default; configurable via env
    return os.getenv("INNGEST_API_BASE", "http://127.0.0.1:8288/v1")


def fetch_runs(event_id: str) -> list[dict]:
    url = f"{_inngest_api_base()}/events/{event_id}/runs"

    resp = requests.get(
        url,
        params={
            "includeOutput": "true"
        },
        timeout=10,
    )

    resp.raise_for_status()

    data = resp.json()
    return data.get("data", [])


def wait_for_run_output(
    event_id: str,
    timeout_s: float = 300.0,
    poll_interval_s: float = 0.5
) -> dict:

    start = time.time()
    last_status = None

    while True:

        runs = fetch_runs(event_id)

        if runs:

            run = runs[0]

            status = run.get("status")
            last_status = status or last_status

            print("Inngest status:", status)

            if status == "Completed":

                output = run.get("output")

                print("Inngest output:", output)

                if output is not None:
                    return output

                # Run is completed but output hasn't appeared yet.
                time.sleep(poll_interval_s)
                continue

            if status in ("Failed", "Cancelled"):
                raise RuntimeError(
                    f"Function run {status}: {run}"
                )

        if time.time() - start > timeout_s:
            raise TimeoutError(
                f"Timed out waiting for run output "
                f"(last status: {last_status})"
            )

        time.sleep(poll_interval_s)


with st.form("rag_query_form"):
    question = st.text_input("Your question")
    top_k = st.number_input("How many chunks to retrieve", min_value=1, max_value=20, value=5, step=1)
    submitted = st.form_submit_button("Ask")

    if submitted and question.strip():
        with st.spinner("Sending event and generating answer..."):
            result_id = str(uuid.uuid4())
            # Fire-and-forget event to Inngest for observability/workflow
            event_id = asyncio.run(
                send_rag_query_event(question.strip(), int(top_k), result_id)
            )
            if RAG_BACKEND_URL:
                # Deployed: the backend posts the answer back (main.py),
                # so poll the backend, not the local Inngest dev server.
                output = wait_for_backend_result(result_id)
            else:
                # Local dev: poll the local Inngest API for the run's output
                output = wait_for_run_output(event_id)
            answer = output.get("answer", "")
            sources = output.get("sources", [])

        st.subheader("Answer")
        st.write(answer or "(No answer)")
        if sources:
            st.caption("Sources")
            for s in sources:
                st.write(f"- {s}")
