"""
Retrieval + generation logic.

retrieve(): pure vector-search step against ChromaDB.
generate_answer(): combines retrieved context with an LLM call (LangChain +
Anthropic) when ANTHROPIC_API_KEY is set; otherwise falls back to a plain
extractive answer so the API is fully runnable even with no key configured.
"""
import os
from pathlib import Path

import chromadb

from app.embeddings import TfidfEmbeddingFunction

CHROMA_DIR = Path(__file__).resolve().parent.parent / "chroma_store"
VECTORIZER_PATH = Path(__file__).resolve().parent.parent / "vectorizer.pkl"
COLLECTION_NAME = "devops_notes"


def _get_collection():
    if not VECTORIZER_PATH.exists():
        raise RuntimeError("No index found. Call POST /ingest first.")
    embedder = TfidfEmbeddingFunction(str(VECTORIZER_PATH))
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_collection(COLLECTION_NAME, embedding_function=embedder)


def retrieve(query: str, k: int = 3) -> list[dict]:
    """Return the top-k most relevant chunks for a query."""
    collection = _get_collection()
    results = collection.query(query_texts=[query], n_results=k)

    hits = []
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        hits.append({"text": doc, "source": meta["source"], "distance": dist})
    return hits


PROMPT_TEMPLATE = """You are a helpful DevOps knowledge assistant. Answer the \
question using ONLY the context below. If the context doesn't contain the \
answer, say you don't have enough information.

Context:
{context}

Question: {question}

Answer:"""


def generate_answer(query: str, k: int = 3) -> dict:
    hits = retrieve(query, k=k)
    context = "\n\n".join(f"[{h['source']}] {h['text']}" for h in hits)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(model="claude-sonnet-4-6", api_key=api_key, max_tokens=400)
        prompt = PROMPT_TEMPLATE.format(context=context, question=query)
        response = llm.invoke(prompt)
        answer = response.content
    else:
        # Fallback: no LLM configured, so return the retrieved context directly
        # (extractive answer) rather than failing.
        answer = (
            "(No ANTHROPIC_API_KEY set, showing retrieved context directly.)\n\n"
            + context
        )

    return {
        "question": query,
        "answer": answer,
        "sources": [{"source": h["source"], "distance": h["distance"]} for h in hits],
    }
