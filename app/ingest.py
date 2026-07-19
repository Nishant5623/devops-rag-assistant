"""
Ingestion pipeline: load documents -> split into chunks -> embed -> store in ChromaDB.
"""
from pathlib import Path

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.embeddings import TfidfEmbeddingFunction

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CHROMA_DIR = Path(__file__).resolve().parent.parent / "chroma_store"
VECTORIZER_PATH = Path(__file__).resolve().parent.parent / "vectorizer.pkl"
COLLECTION_NAME = "devops_notes"


def load_documents() -> list[dict]:
    """Read every .txt file in data/ and return {text, source} records."""
    docs = []
    for path in sorted(DATA_DIR.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        docs.append({"text": text, "source": path.name})
    return docs


def chunk_documents(docs: list[dict]) -> list[dict]:
    """Split each document into overlapping chunks for better retrieval granularity."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=400, chunk_overlap=60, separators=["\n\n", "\n", ". ", " "]
    )
    chunks = []
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
    docs = load_documents()
    if not docs:
        raise RuntimeError(f"No .txt documents found in {DATA_DIR}")

    chunks = chunk_documents(docs)
    corpus = [c["text"] for c in chunks]

    embedder = TfidfEmbeddingFunction(str(VECTORIZER_PATH))
    embedder.fit(corpus)  # fit TF-IDF vocabulary on this corpus

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    # Start fresh each time ingestion runs so re-running is idempotent.
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(
        COLLECTION_NAME, embedding_function=embedder
    )

    collection.add(
        documents=corpus,
        ids=[c["chunk_id"] for c in chunks],
        metadatas=[{"source": c["source"]} for c in chunks],
    )

    return {"documents_ingested": len(docs), "chunks_indexed": len(chunks)}


if __name__ == "__main__":
    result = run_ingestion()
    print(f"Ingested {result['documents_ingested']} documents "
          f"into {result['chunks_indexed']} chunks.")
