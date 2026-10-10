from app.config import get_settings
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_returns_200():
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "index_loaded" in body


def test_health_returns_version():
    resp = client.get("/api/v1/health")
    body = resp.json()
    assert body["version"] == get_settings().app_version


def test_health_reports_commit_sha():
    """sha is exposed on /api/v1/health so CD can verify what commit is live."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sha"] == get_settings().git_sha


def test_health_root_alias_reports_sha():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert "sha" in resp.json()


def test_ingest_then_ask_returns_sources():
    ingest_resp = client.post("/api/v1/ingest")
    assert ingest_resp.status_code == 200
    ingest_body = ingest_resp.json()
    assert ingest_body["documents_ingested"] > 0
    assert ingest_body["chunks_indexed"] > 0

    resp = client.post(
        "/api/v1/ask", json={"question": "What is a Kubernetes Deployment?", "k": 3}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"]
    assert body["sources"], "Expected non-empty sources"
    assert len(body["sources"]) > 0


def test_ask_sources_include_chunk_text():
    client.post("/api/v1/ingest")
    resp = client.post(
        "/api/v1/ask", json={"question": "What is a Kubernetes Deployment?", "k": 2}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is True
    for source in body["sources"]:
        assert source["text"], "Each source should carry the chunk text used"
        assert source["source"]
        assert "distance" in source


def test_ask_out_of_scope_returns_not_in_my_notes():
    client.post("/api/v1/ingest")
    resp = client.post(
        "/api/v1/ask", json={"question": "What is the capital of France?", "k": 3}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is False
    assert body["sources"] == [], "No chunks are used to answer an off-topic question"
    assert "not in my notes" in body["answer"].lower()


def test_health_alias_at_root():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == get_settings().app_version


def test_ask_with_short_question_returns_422():
    resp = client.post("/api/v1/ask", json={"question": "a", "k": 3})
    assert resp.status_code == 422


def test_ask_with_question_too_long_returns_422():
    resp = client.post("/api/v1/ask", json={"question": "x" * 501, "k": 3})
    assert resp.status_code == 422


def test_ask_with_top_k_out_of_range_returns_422():
    resp = client.post("/api/v1/ask", json={"question": "what is docker?", "k": 99})
    assert resp.status_code == 422


def test_metrics_endpoint_present():
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "http_requests_total" in resp.text
