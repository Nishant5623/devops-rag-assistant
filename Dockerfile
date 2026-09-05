# syntax=docker/dockerfile:1

# ---------------------------------------------------------------
# Build stage: install production dependencies
# ---------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install -r requirements.txt

# ---------------------------------------------------------------
# Runtime stage: minimal image, non-root user
# ---------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production

# Create a non-root user to run the app (CVE hardening best practice).
RUN groupadd --gid 10001 app && \
    useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY app/ app/
COPY data/ data/
COPY static/ static/

# Build the vector index at image build time so the container is ready to serve.
RUN python -m app.ingest

# Grant the non-root user ownership of the runtime directories it must write to.
RUN chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"

# Gunicorn-compatible graceful shutdown via uvicorn's signal handling.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
