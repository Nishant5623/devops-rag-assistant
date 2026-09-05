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


def test_ask_with_short_question_returns_422():
    resp = client.post("/api/v1/ask", json={"question": "a", "k": 3})
    assert resp.status_code == 422


def test_ask_with_question_too_long_returns_422():
    resp = client.post(
        "/api/v1/ask", json={"question": "x" * 501, "k": 3}
    )
    assert resp.status_code == 422


def test_ask_with_top_k_out_of_range_returns_422():
    resp = client.post(
        "/api/v1/ask", json={"question": "what is docker?", "k": 99}
    )
    assert resp.status_code == 422


def test_metrics_endpoint_present():
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "http_requests_total" in resp.text
