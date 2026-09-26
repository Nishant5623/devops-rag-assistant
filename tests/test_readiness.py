"""Regression tests for deployment-critical index/readiness behaviour.

These cover the failure mode that made the Kubernetes and Helm deploys
non-functional: a fresh empty volume mounted over /app/chroma_store hides the
index baked into the image, the readiness probe still returned 200, and every
/ask call blew up with an opaque 500.
"""

import pytest
from app.config import get_settings
from app.main import _ensure_index, app
from app.rag import index_available
from fastapi.testclient import TestClient

client = TestClient(app)
settings = get_settings()


@pytest.fixture
def empty_index(tmp_path, monkeypatch):
    """Point the app at a brand-new empty Chroma dir, like a fresh emptyDir."""
    chroma_dir = tmp_path / "chroma_store"
    chroma_dir.mkdir()
    monkeypatch.setattr(settings, "chroma_dir", chroma_dir)
    assert not index_available()
    return chroma_dir


def test_ask_returns_400_not_500_when_index_missing(empty_index):
    """A missing index is a client-visible state, not an opaque server error."""
    resp = client.post(
        "/api/v1/ask", json={"question": "What is a Kubernetes Deployment?"}
    )
    assert resp.status_code == 400
    assert "ingest" in resp.json()["detail"].lower()


def test_ready_returns_503_when_index_missing(empty_index):
    """Readiness must fail so the replica is pulled from the load balancer."""
    resp = client.get("/api/v1/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["index_loaded"] is False


def test_health_stays_200_when_index_missing(empty_index):
    """Liveness must not flap on a missing index, or Kubernetes restart-loops."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["index_loaded"] is False


def test_ensure_index_rebuilds_missing_index(empty_index):
    """Startup self-heals the shadowed-index case with no manual step."""
    _ensure_index()
    assert index_available()


def test_ready_returns_200_once_index_exists():
    assert client.post("/api/v1/ingest").status_code == 200
    resp = client.get("/api/v1/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_ensure_index_is_idempotent():
    _ensure_index()
    before = index_available()
    _ensure_index()
    assert index_available() is before is True


def test_ensure_index_respects_auto_ingest_disabled(empty_index, monkeypatch):
    monkeypatch.setattr(settings, "auto_ingest", False)
    _ensure_index()
    assert not index_available()
