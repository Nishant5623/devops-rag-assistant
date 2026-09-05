"""
FastAPI application entry point for the DevOps Knowledge Assistant (RAG).

Sets up:
  * versioned API routes under /api/v1
  * rate limiting via slowapi
  * Prometheus metrics
  * request ID + security headers middleware
  * optional OpenTelemetry tracing
  * static chat frontend at /
"""
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import chromadb
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings
from app.ingest import run_ingestion
from app.middleware import (
    AdminGateMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)
from app.rag import generate_answer
from app.security import require_admin

logger = logging.getLogger("devops-rag")
settings = get_settings()

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _setup_telemetry(app)
    logger.info(
        "Starting %s v%s (env=%s)",
        settings.app_name,
        settings.app_version,
        settings.env,
    )
    yield
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "A small RAG app: FastAPI + LangChain + ChromaDB over local DevOps notes."
        " Endpoints are versioned under /api/v1."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/api/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# --- Middleware -----------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(AdminGateMiddleware)
app.add_middleware(SecurityHeadersMiddleware)


def _setup_telemetry(fastapi_app: FastAPI) -> None:
    """Wire up OpenTelemetry tracing if an OTLP endpoint is configured."""
    if not settings.otlp_endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": settings.app_name})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint))
        )
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(fastapi_app)
        logger.info("OpenTelemetry tracing enabled -> %s", settings.otlp_endpoint)
    except Exception as exc:
        logger.warning("Failed to enable OpenTelemetry tracing: %s", exc)


# --- Schemas --------------------------------------------------------------
class AskRequest(BaseModel):
    question: str = Field(
        ..., min_length=3, max_length=500, description="Question to answer"
    )
    k: int = Field(
        settings.default_top_k,
        ge=settings.min_top_k,
        le=settings.max_top_k,
        description="Number of retrieved chunks",
    )


# --- Router (versioned) ---------------------------------------------------
api = APIRouter(prefix=settings.api_prefix)


def _index_available() -> bool:
    """Return True if the vectorizer and Chroma collection exist and load cleanly."""
    try:
        if not settings.vectorizer_path.exists():
            return False
        client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        client.get_collection(settings.collection_name)
        return True
    except Exception:
        return False


@api.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "index_loaded": _index_available(),
        "version": settings.app_version,
    }


@api.post("/ingest", status_code=200)
@limiter.limit(settings.ingest_rate_limit)
def ingest(request: Request) -> dict:
    """(Re)build the vector index from documents in the data/ folder."""
    require_admin(request)
    try:
        return run_ingestion()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api.post("/ask", status_code=200)
@limiter.limit(settings.ask_rate_limit)
def ask(request: Request, req: AskRequest) -> dict:
    """Answer a question using retrieval-augmented generation over the indexed notes."""
    try:
        return generate_answer(req.question, k=req.k)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


app.include_router(api)

# --- Metrics --------------------------------------------------------------
Instrumentator().instrument(app).expose(
    app, endpoint="/metrics", include_in_schema=False
)


# Root API info endpoint.
@app.get("/api")
def api_root() -> dict:
    return {
        "name": "DevOps RAG Assistant",
        "docs": "/docs",
        "version": settings.app_version,
    }


# --- Static frontend (mounted last so it does not shadow API routes) ------
if settings.static_dir.exists():
    app.mount(
        "/", StaticFiles(directory=str(settings.static_dir), html=True), name="static"
    )
