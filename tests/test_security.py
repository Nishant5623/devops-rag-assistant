from app.config import get_settings
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_metrics_requires_admin_key_when_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "admin_api_key", "topsecret")
    # Force middleware to re-read settings (cached object mutated in place).
    resp = client.get("/metrics")
    assert resp.status_code == 401


def test_metrics_accepts_valid_admin_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "admin_api_key", "topsecret")
    resp = client.get("/metrics", headers={"X-Admin-Key": "topsecret"})
    assert resp.status_code == 200


def test_metrics_rejects_wrong_admin_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "admin_api_key", "topsecret")
    resp = client.get("/metrics", headers={"X-Admin-Key": "wrong"})
    assert resp.status_code == 403


def test_ingest_requires_admin_key_when_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "admin_api_key", "topsecret")
    resp = client.post("/api/v1/ingest")
    assert resp.status_code in (401, 403)


def test_metrics_open_when_no_key_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "admin_api_key", "")
    resp = client.get("/metrics")
    assert resp.status_code == 200


def test_health_returns_request_id_header():
    resp = client.get("/api/v1/health")
    assert "x-request-id" in resp.headers
