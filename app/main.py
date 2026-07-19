from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.ingest import run_ingestion
from app.rag import generate_answer

app = FastAPI(
    title="DevOps Knowledge Assistant (RAG)",
    description="A small RAG app: FastAPI + LangChain + ChromaDB over local DevOps notes.",
)


class AskRequest(BaseModel):
    question: str
    k: int = 3


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingest")
def ingest():
    """(Re)build the vector index from documents in the data/ folder."""
    try:
        result = run_ingestion()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result


@app.post("/ask")
def ask(req: AskRequest):
    """Answer a question using retrieval-augmented generation over the indexed notes."""
    try:
        return generate_answer(req.question, k=req.k)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
