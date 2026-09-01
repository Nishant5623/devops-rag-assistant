from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "index_loaded" in body


def test_ingest_then_ask_returns_sources():
    ingest_resp = client.post("/ingest")
    assert ingest_resp.status_code == 200

    resp = client.post(
        "/ask", json={"question": "What is a Kubernetes Deployment?", "k": 3}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"]
    assert body["sources"], "Expected non-empty sources"
    assert len(body["sources"]) > 0


def test_ask_with_short_question_returns_422():
    resp = client.post("/ask", json={"question": "a", "k": 3})
    assert resp.status_code == 422
