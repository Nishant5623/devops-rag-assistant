"""
Retrieval + generation logic.

retrieve(): pure vector-search step against ChromaDB.
generate_answer(): combines retrieved context with an LLM call (LangChain +
Anthropic) when ANTHROPIC_API_KEY is set; otherwise falls back to a plain
extractive answer so the API is fully runnable with no key configured.
"""

import logging

import chromadb
from chromadb import PersistentClient
from chromadb.errors import NotFoundError

from app.config import get_settings
from app.embeddings import TfidfEmbeddingFunction

logger = logging.getLogger("devops-rag.rag")

# Emit the "running keyless" notice exactly once per process instead of on
# every single request, which floods log aggregators in production.
_keyless_notice_logged = False


def index_available() -> bool:
    """Return True if the vectorizer and Chroma collection exist and load cleanly."""
    settings = get_settings()
    try:
        if not settings.vectorizer_path.exists():
            return False
        client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        client.get_collection(settings.collection_name)
        return True
    except Exception:
        return False


def _get_client() -> PersistentClient:  # type: ignore[valid-type]
    """Return a persistent Chroma client. Keeps the vector store path centralised."""
    settings = get_settings()
    return chromadb.PersistentClient(path=str(settings.chroma_dir))


def _get_collection():
    settings = get_settings()
    if not settings.vectorizer_path.exists():
        raise RuntimeError("No index found. Call POST /ingest first.")
    embedder = TfidfEmbeddingFunction(settings.vectorizer_path)
    client = _get_client()
    try:
        collection = client.get_collection(  # type: ignore[attr-defined]
            settings.collection_name, embedding_function=embedder
        )
    except NotFoundError as exc:
        # Chroma raises NotFoundError (not RuntimeError) for a missing
        # collection, which would otherwise escape as an opaque HTTP 500.
        raise RuntimeError(
            "Vector index is missing. Call POST /api/v1/ingest to rebuild it."
        ) from exc
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

NOT_FOUND_ANSWER = (
    "That's not in my notes. I can only answer from the local DevOps notes "
    "(Docker, Kubernetes, Linux, CI/CD, Ansible) \u2014 try rephrasing your "
    "question around one of those topics."
)


def _is_in_notes(query: str, hits: list[dict]) -> bool:
    """Return True only when the question is actually answerable from the corpus.

    TF-IDF retrieval can't spot a miss from the distance alone: a query with no
    overlapping vocabulary scores exactly 1.0, which looks *better* than many
    real hits. So a question must (1) share at least one indexed word with the
    notes and (2) have a best hit within the configured distance cap.
    """
    if not hits:
        return False
    settings = get_settings()
    embedder = TfidfEmbeddingFunction(settings.vectorizer_path)
    vector = embedder([query])[0]
    if not any(vector):
        logger.info(
            "No vocabulary overlap for question=%r; answering 'not in my notes'.",
            query,
        )
        return False
    return hits[0]["distance"] <= settings.relevance_max_distance


def generate_answer(query: str, k: int | None = None) -> dict:
    global _keyless_notice_logged

    settings = get_settings()
    hits = retrieve(query, k=k)

    # Gate before touching the LLM: never hand the model ambiguous context and
    # let it bluff. Off-topic questions get an explicit "not in my notes"
    # answer with no sources instead.
    if not _is_in_notes(query, hits):
        return {
            "question": query,
            "answer": NOT_FOUND_ANSWER,
            "found": False,
            "sources": [],
        }

    context = "\n\n".join(f"[{h['source']}] {h['text']}" for h in hits)

    # The app ships fully keyless by default: no API key is required. When an
    # ANTHROPIC_API_KEY is present we upgrade to LLM-generated answers. It is
    # read through Settings so a key supplied via .env is honoured too.
    api_key = settings.anthropic_api_key

    if api_key:
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(  # type: ignore[call-arg]
            model=settings.llm_model,
            api_key=api_key,  # type: ignore[arg-type]
            max_tokens=settings.llm_max_tokens,
        )
        prompt = PROMPT_TEMPLATE.format(context=context, question=query)
        response = llm.invoke(prompt)
        answer = response.content
    else:
        if not _keyless_notice_logged:
            # Server-side only: visitors never see implementation details like
            # "no API key configured". The answer just shows what matched.
            logger.info(
                "ANTHROPIC_API_KEY not set - serving extractive answers from "
                "retrieved context only."
            )
            _keyless_notice_logged = True
        answer = "Matching notes:\n\n" + context

    return {
        "question": query,
        "answer": answer,
        "found": True,
        "sources": [
            {"source": h["source"], "distance": h["distance"], "text": h["text"]}
            for h in hits
        ],
    }
