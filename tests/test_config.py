"""Config parsing tests.

CORS_ORIGINS is a list, but pydantic-settings only JSON-decodes complex fields.
That silently broke every non-JSON form the project documents and ships: the
`.env.example` default ("*"), docker-compose ("*"), and the Kubernetes/Helm
ConfigMaps ("https://rag.example.com"). These tests pin the accepted formats.
"""

from app.config import Settings


def _settings(monkeypatch, value: str) -> Settings:
    monkeypatch.setenv("CORS_ORIGINS", value)
    return Settings(_env_file=None)


def test_cors_origins_defaults_to_wildcard():
    assert Settings(_env_file=None).cors_origins == ["*"]


def test_cors_origins_accepts_star(monkeypatch):
    assert _settings(monkeypatch, "*").cors_origins == ["*"]


def test_cors_origins_accepts_single_origin(monkeypatch):
    # This is exactly what k8s/configmap.yml and the Helm chart set.
    assert _settings(monkeypatch, "https://rag.example.com").cors_origins == [
        "https://rag.example.com"
    ]


def test_cors_origins_accepts_comma_separated(monkeypatch):
    assert _settings(monkeypatch, "https://a.com, https://b.com").cors_origins == [
        "https://a.com",
        "https://b.com",
    ]


def test_cors_origins_accepts_json_array(monkeypatch):
    # render.yaml ships "[]" so the list form must keep working too.
    assert _settings(monkeypatch, "[]").cors_origins == []
    assert _settings(monkeypatch, '["https://a.com"]').cors_origins == ["https://a.com"]
