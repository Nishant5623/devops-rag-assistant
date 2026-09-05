"""
Retrieval + generation logic.

retrieve(): pure vector-search step against ChromaDB.
generate_answer(): combines retrieved context with an LLM call (LangChain +
Anthropic) when ANTHROPIC_API_KEY is set; otherwise falls back to a plain
extractive answer so the API is fully runnable even with no key configured.
"""
import logging
import os

import chromadb
from chromadb import PersistentClient

from app.config import get_settings
from app.embeddings import TfidfEmbeddingFunction

logger = logging.getLogger("devops-rag.rag")


def _get_client() -> PersistentClient:
    """Return a persistent Chroma client. Keeps the vector store path centralised."""
    settings = get_settings()
    return chromadb.PersistentClient(path=str(settings.chroma_dir))


def _get_collection():
    settings = get_settings()
    if not settings.vectorizer_path.exists():
        raise RuntimeError("No index found. Call POST /ingest first.")
    embedder = TfidfEmbeddingFunction(settings.vectorizer_path)
    client = _get_client()
    collection = client.get_collection(
        settings.collection_name, embedding_function=embedder
    )
    if collection.count() == 0:
        raise RuntimeError("Index is empty. Call POST /ingest to rebuild it.")
    return collection


def retrieve(query: str, k: int | None = None) -> list[dict]:
    """Return the top-k most relevant chunks for a query."""
    settings = get_settings()
    k = k or settings.default_top_k
    k = max(settings.min_top_k, min(k, settings.max_top_k))

    collection = _get_collection()
    results = collection.query(query_texts=[query], n_results=k)

    hits: list[dict] = []
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]
    for doc, meta, dist in zip(documents, metadatas, distances, strict=True):
        hits.append(
            {
                "text": doc,
                "source": meta.get("source", "unknown"),
                "distance": dist,
            }
        )
    return hits


PROMPT_TEMPLATE = """You are a helpful DevOps knowledge assistant. Answer the \
question using ONLY the context below. If the context doesn't contain the \
answer, say you don't have enough information.

Context:
{context}

Question: {question}

Answer:"""


def generate_answer(query: str, k: int | None = None) -> dict:
    settings = get_settings()
    hits = retrieve(query, k=k)
    context = "\n\n".join(f"[{h['source']}] {h['text']}" for h in hits)

    # The app ships fully keyless by default: no API key is required. When an
    # ANTHROPIC_API_KEY is present we upgrade to LLM-generated answers.
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if api_key:
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(
            model=settings.llm_model,
            api_key=api_key,
            max_tokens=settings.llm_max_tokens,
        )
        prompt = PROMPT_TEMPLATE.format(context=context, question=query)
        response = llm.invoke(prompt)
        answer = response.content
    else:
        logger.warning("No ANTHROPIC_API_KEY set; returning extractive fallback.")
        answer = (
            "(No ANTHROPIC_API_KEY set, showing retrieved context directly.)\n\n"
            + context
        )

    return {
        "question": query,
        "answer": answer,
        "sources": [{"source": h["source"], "distance": h["distance"]} for h in hits],
    }
