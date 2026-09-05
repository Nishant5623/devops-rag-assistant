"""
Centralized application configuration.

All settings are read once at import time and shared across the app. Values
can be overridden through environment variables (e.g. APP_*_DIR, or the
documented top-level vars below) following pydantic-settings conventions.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, populated from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Paths ----------------------------------------------------------------
    app_dir: Path = Path(__file__).resolve().parent
    data_dir: Path = Path(__file__).resolve().parent.parent / "data"
    chroma_dir: Path = Path(__file__).resolve().parent.parent / "chroma_store"
    vectorizer_path: Path = (
        Path(__file__).resolve().parent.parent / "vectorizer.pkl"
    )
    static_dir: Path = Path(__file__).resolve().parent.parent / "static"
    collection_name: str = "devops_notes"

    # --- Service ----------------------------------------------------------
    app_name: str = "DevOps Knowledge Assistant (RAG)"
    app_version: str = "2.0.0"
    api_prefix: str = "/api/v1"
    # Bind to all interfaces so the container can accept external traffic.
    host: str = "0.0.0.0"  # noqa: S104
    port: int = 8000
    workers: int = 1

    # --- Retrieval / generation ------------------------------------------
    default_top_k: int = 3
    min_top_k: int = 1
    max_top_k: int = 10
    chunk_size: int = 400
    chunk_overlap: int = 60
    tfidf_max_features: int = 4096
    llm_model: str = "claude-sonnet-4-6"
    llm_max_tokens: int = 400

    # --- Rate limiting ----------------------------------------------------
    ask_rate_limit: str = "10/minute"
    ingest_rate_limit: str = "5/minute"

    # --- Security ---------------------------------------------------------
    # Comma-separated list of allowed CORS origins. "*" allows all.
    cors_origins: list[str] = ["*"]
    # Shared secret required to call /ingest and to read /metrics. Leave empty
    # to disable auth (not recommended for production).
    admin_api_key: str = ""

    # --- Observability ----------------------------------------------------
    env: str = "development"
    log_level: str = "INFO"
    otlp_endpoint: str = ""

    @property
    def project_root(self) -> Path:
        return self.app_dir.parent

    @property
    def is_production(self) -> bool:
        return self.env.lower() in {"production", "prod", "staging"}


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (pydantic settings are read once)."""
    return Settings()
