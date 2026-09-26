"""Tests for the keyless (no AI API key) code path and config plumbing."""

from app.config import Settings, get_settings
from app.main import app
from app.rag import generate_answer
from fastapi.testclient import TestClient

client = TestClient(app)


def test_settings_reads_anthropic_key_from_env(monkeypatch):
    """The key must come through Settings, not os.environ, so a key placed in
    .env is honoured instead of being silently ignored."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env")
    s = Settings(_env_file=None)
    assert s.anthropic_api_key == "sk-ant-from-env"


def test_settings_reads_anthropic_key_from_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=sk-ant-from-file\n", encoding="utf-8")
    s = Settings(_env_file=str(env_file))
    assert s.anthropic_api_key == "sk-ant-from-file"


def test_anthropic_key_defaults_to_empty_keyless():
    assert Settings(_env_file=None).anthropic_api_key == ""


def test_generate_answer_works_without_any_api_key(monkeypatch):
    """The whole point: a fully functional app with no AI key configured."""
    client.post("/api/v1/ingest")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")

    out = generate_answer("What is a Kubernetes Deployment?", k=2)
    assert out["answer"]
    assert out["sources"]
    assert "kubernetes" in out["answer"].lower()


def test_keyless_answer_reports_extractive_mode(monkeypatch):
    client.post("/api/v1/ingest")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")

    out = generate_answer("How do Docker volumes work?", k=1)
    assert "ANTHROPIC_API_KEY" in out["answer"]


def test_ask_endpoint_succeeds_keyless(monkeypatch):
    client.post("/api/v1/ingest")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")

    resp = client.post(
        "/api/v1/ask", json={"question": "How does Ansible automate tasks?", "k": 2}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"]
    assert body["sources"]
