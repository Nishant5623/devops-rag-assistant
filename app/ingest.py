"""
Ingestion pipeline: load documents -> split into chunks -> embed -> store in ChromaDB.
"""
import logging
from contextlib import suppress
from pathlib import Path

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import get_settings
from app.embeddings import TfidfEmbeddingFunction

logger = logging.getLogger("devops-rag.ingest")


def load_documents(data_dir: Path | None = None) -> list[dict]:
    """Read every .txt file in the data directory and return {text, source} records."""
    settings = get_settings()
    data_dir = data_dir or settings.data_dir
    docs: list[dict] = []
    for path in sorted(data_dir.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        docs.append({"text": text, "source": path.name})
    return docs


def chunk_documents(docs: list[dict], chunk_size: int | None = None,
                    chunk_overlap: int | None = None) -> list[dict]:
    """Split each document into overlapping chunks for better retrieval granularity."""
    settings = get_settings()
    chunk_size = chunk_size or settings.chunk_size
    if chunk_overlap is None:
        chunk_overlap = settings.chunk_overlap
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " "],
    )
    chunks: list[dict] = []
    for doc in docs:
        for i, chunk in enumerate(splitter.split_text(doc["text"])):
            chunks.append(
                {
                    "text": chunk,
                    "source": doc["source"],
                    "chunk_id": f"{doc['source']}::{i}",
                }
            )
    return chunks


def run_ingestion() -> dict:
    """Rebuild the vector index from scratch (idempotent)."""
    settings = get_settings()

    docs = load_documents(settings.data_dir)
    if not docs:
        raise RuntimeError(f"No .txt documents found in {settings.data_dir}")

    chunks = chunk_documents(docs)
    corpus = [c["text"] for c in chunks]

    embedder = TfidfEmbeddingFunction(settings.vectorizer_path)
    embedder.fit(corpus)  # fit TF-IDF vocabulary on this corpus

    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    # Start fresh each run so ingestion is idempotent (no duplicate chunks).
    with suppress(Exception):
        client.delete_collection(settings.collection_name)  # type: ignore[attr-defined]

    collection = client.create_collection(  # type: ignore[attr-defined]
        settings.collection_name, embedding_function=embedder
    )

    # chromadb's stubs are incomplete; its runtime API is dynamically typed.
    collection.add(  # type: ignore[attr-defined]
        documents=corpus,
        ids=[c["chunk_id"] for c in chunks],
        metadatas=[{"source": c["source"]} for c in chunks],
    )

    result = {"documents_ingested": len(docs), "chunks_indexed": len(chunks)}
    logger.info("ingestion complete: %s", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_ingestion()
    print(
        f"Ingested {result['documents_ingested']} documents "
        f"into {result['chunks_indexed']} chunks."
    )
