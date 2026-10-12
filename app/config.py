"""
Centralized application configuration.

All settings are read once at import time and shared across the app. Values
can be overridden through environment variables (e.g. APP_*_DIR, or the
documented top-level vars below) following pydantic-settings conventions.
"""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    vectorizer_path: Path = Path(__file__).resolve().parent.parent / "vectorizer.pkl"
    static_dir: Path = Path(__file__).resolve().parent.parent / "static"
    collection_name: str = "devops_notes"

    # --- Service ----------------------------------------------------------
    app_name: str = "DevOps Knowledge Assistant (RAG)"
    app_version: str = "2.0.0"
    api_prefix: str = "/api/v1"
    # The exact commit this build was compiled from. Set via the Dockerfile's
    # GIT_SHA build arg (CI passes github.sha). Kept a plain field so the
    # Dockerfile default below is a sentinel for "built outside CI".
    git_sha: str = "dev"
    # UTC timestamp of the image build, set via the Dockerfile's BUILD_TIME
    # build arg (CI passes the workflow's start time). Reported on /health so
    # an operator can tell exactly which artifact is live, not just which
    # commit. "unknown" outside CI.
    build_time: str = "unknown"
    # Bind to all interfaces so the container can accept external traffic.
    host: str = "0.0.0.0"  # noqa: S104
    port: int = 8000
    # Build the vector index on startup if it is missing. The image bakes an
    # index in at build time, but a Kubernetes emptyDir mounted over
    # /app/chroma_store hides it, so each pod must rebuild its own index.
    auto_ingest: bool = True

    # --- Retrieval / generation ------------------------------------------
    default_top_k: int = 3
    min_top_k: int = 1
    max_top_k: int = 10
    chunk_size: int = 400
    chunk_overlap: int = 60
    tfidf_max_features: int = 4096
    llm_model: str = "claude-sonnet-4-6"
    llm_max_tokens: int = 400
    # Answer-sufficiency gate: a question whose TF-IDF embedding shares no
    # vocabulary with the notes can never match, and a best-hit distance above
    # this cap is treated as "not in my notes" instead of guessing.
    relevance_max_distance: float = 2.0

    # --- Rate limiting ----------------------------------------------------
    ask_rate_limit: str = "10/minute"
    ingest_rate_limit: str = "5/minute"

    # --- Security ---------------------------------------------------------
    # Comma-separated list of allowed CORS origins. "*" allows all. Accepts the
    # JSON-array form (["a", "b"]) and the comma-separated form (a,b) used in
    # .env files and the Kubernetes/Helm ConfigMaps.
    cors_origins: Annotated[list[str], NoDecode] = ["*"]
    # Shared secret required to call /ingest and to read /metrics. Leave empty
    # to disable auth (not recommended for production).
    admin_api_key: str = ""

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        """Accept a JSON array or a plain/comma-separated origin list.

        pydantic-settings only JSON-decodes complex fields, so a plain
        "https://app.example.com" (or "*") would raise a SettingsError before
        validation ever runs. Normalise the string forms here instead, while
        still honouring a pre-parsed list from .env / init kwargs.
        """
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                return json.loads(text)
            return [item.strip() for item in text.split(",") if item.strip()]
        return value

    # --- Optional LLM ------------------------------------------------------
    # Optional. When empty the app answers in extractive mode from the
    # retrieved context only, so it is fully functional without any AI key.
    anthropic_api_key: str = ""

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

    @property
    def resolved_git_sha(self) -> str:
        """The commit actually running, resolving CI-less builds too.

        Render builds the image itself (CI build args never reach it), but it
        injects RENDER_GIT_COMMIT with the deployed commit hash at runtime.
        So /health can always report the real SHA, not just 'dev'.
        """
        if self.git_sha != "dev":
            return self.git_sha
        return os.environ.get("RENDER_GIT_COMMIT", "dev")


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (pydantic settings are read once)."""
    return Settings()
