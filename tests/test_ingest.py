import tempfile
from pathlib import Path

from app.config import get_settings
from app.ingest import chunk_documents, load_documents, run_ingestion


def test_load_documents_reads_txt_files():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "a.txt").write_text("content a", encoding="utf-8")
        (d / "b.txt").write_text("content b", encoding="utf-8")
        (d / "c.md").write_text("not read", encoding="utf-8")

        docs = load_documents(d)
        sources = {doc["source"] for doc in docs}
        assert sources == {"a.txt", "b.txt"}


def test_chunk_documents_produces_ids_and_sources():
    docs = [{"text": "sentence one. sentence two. sentence three.", "source": "x.txt"}]
    chunks = chunk_documents(docs, chunk_size=10, chunk_overlap=2)
    assert chunks
    for c in chunks:
        assert c["source"] == "x.txt"
        assert c["chunk_id"].startswith("x.txt::")
        assert c["text"]


def test_run_ingestion_produces_counts():
    settings = get_settings()
    result = run_ingestion()
    assert result["documents_ingested"] > 0
    assert result["chunks_indexed"] > 0
    assert settings.vectorizer_path.exists()
