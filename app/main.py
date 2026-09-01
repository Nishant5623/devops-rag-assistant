import logging
import time
from pathlib import Path

import chromadb
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from prometheus_fastapi_instrumentator import Instrumentator

from app.ingest import run_ingestion
from app.rag import generate_answer

logger = logging.getLogger("devops-rag")
logging.basicConfig(level=logging.INFO)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="DevOps Knowledge Assistant (RAG)",
    description="A small RAG app: FastAPI + LangChain + ChromaDB over local DevOps notes.",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str = Field(
        ..., min_length=3, max_length=500, description="Question to answer"
    )
    k: int = Field(3, ge=1, le=10, description="Number of retrieved chunks (1-10)")


CHROMA_DIR = Path(__file__).resolve().parent.parent / "chroma_store"
VECTORIZER_PATH = Path(__file__).resolve().parent.parent / "vectorizer.pkl"
COLLECTION_NAME = "devops_notes"


def _index_available() -> bool:
    """Return True if the vectorizer and Chroma collection exist and load cleanly."""
    try:
        if not VECTORIZER_PATH.exists():
            return False
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        client.get_collection(COLLECTION_NAME)
        return True
    except Exception:
        return False


@app.get("/health")
def health():
    index_loaded = _index_available()
    return {"status": "ok", "index_loaded": index_loaded}


@app.post("/ingest")
def ingest():
    """(Re)build the vector index from documents in the data/ folder."""
    try:
        result = run_ingestion()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result


@app.post("/ask")
@limiter.limit("10/minute")
def ask(request: Request, req: AskRequest):
    """Answer a question using retrieval-augmented generation over the indexed notes."""
    start = time.perf_counter()
    try:
        result = generate_answer(req.question, k=req.k)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "ask request | question_len=%d k=%d response_time_ms=%.1f",
            len(req.question),
            req.k,
            elapsed_ms,
        )
    return result


Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
