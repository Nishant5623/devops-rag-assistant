import pytest
from app.ingest import run_ingestion
from app.rag import retrieve


@pytest.fixture(scope="module")
def indexed():
    """Ensure an index exists once for the retrieval tests."""
    run_ingestion()
    return True


def test_retrieve_returns_expected_fields(indexed):
    hits = retrieve("What is a Kubernetes Deployment?", k=3)
    assert hits
    for hit in hits:
        assert "text" in hit
        assert "source" in hit
        assert "distance" in hit


def test_retrieve_respects_k(indexed):
    hits = retrieve("Docker", k=2)
    assert len(hits) <= 2


def test_retrieve_returns_kubernetes_for_kubernetes_question(indexed):
    hits = retrieve("How does a Deployment rollout work?", k=5)
    sources = {h["source"] for h in hits}
    assert any("kubernetes" in s for s in sources)
