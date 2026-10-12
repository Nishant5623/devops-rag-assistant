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
    /opt/venv/bin/pip install -r requirements.txt && \
    # Hardening: the runtime image does not need the packaging toolchain, so
    # remove it now that the dependencies above are installed. pip, setuptools
    # and wheel are build-only; the app never imports them at run time.
    # Removing them also disposes of two things that only ever mislead the
    # Trivy scanner: setuptools' vendored jaraco.context/wheel code (shipped at
    # pinned versions that carry CVEs) and pip's _vendor/bom.cdx.json, a stale
    # CycloneDX SBOM of pip's own build deps (setuptools 70.3.0, msgpack 1.1.2,
    # urllib3 2.7.0) that Trivy's [sbom] analyzer imports as if those packages
    # were installed. pip is uninstalled last because it runs the uninstalls.
    /opt/venv/bin/pip uninstall -y setuptools wheel && \
    /opt/venv/bin/pip uninstall -y pip

# ---------------------------------------------------------------
# Runtime stage: minimal image, non-root user
# ---------------------------------------------------------------
FROM python:3.12-slim AS runtime

# The exact commit this image was built from. CI passes github.sha; when the
# image is built elsewhere (e.g. Render) the value stays "dev" and the app
# falls back to Render's RENDER_GIT_COMMIT env var at runtime. See config.py.
ARG GIT_SHA=dev

# UTC timestamp of the build, injected by CI. Reported on /health alongside the
# commit so an operator can tell exactly which artifact is live.
ARG BUILD_TIME=unknown

# NOTE: the app reads the ENV variable (see app/config.py). Setting APP_ENV
# here would silently leave the container in development mode, which disables
# JSON logging and HSTS.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    ENV=production \
    ANONYMIZED_TELEMETRY=False \
    AUTO_INGEST=True \
    GIT_SHA=${GIT_SHA} \
    BUILD_TIME=${BUILD_TIME}

# Pull in all pending OS security updates at build time (e.g. liblzma5,
# DSA-6549-1). The floating python:3.12-slim base tag can lag its own repos,
# so refresh the OS layer rather than shipping a stale, vulnerable base.
RUN apt-get update && \
    apt-get upgrade -y --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# The base python:3.12-slim image ships its own pip/setuptools under
# /usr/local/lib. The app is served by the tooling-free /opt/venv (see the
# builder stage), so these are dead weight: removing them drops the vendored
# setuptools metadata and pip's stale _vendor/bom.cdx.json SBOM that would
# otherwise feed the HIGH,CRITICAL Trivy gate phantom findings for packages
# that are not installed. pip is uninstalled last because it runs the
# uninstalls.
RUN /usr/local/bin/python3.12 -m pip uninstall -y setuptools wheel && \
    /usr/local/bin/python3.12 -m pip uninstall -y pip

# Create a non-root user to run the app (CVE hardening best practice).
RUN groupadd --gid 10001 app && \
    useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY app/ app/
COPY data/ data/
COPY static/ static/
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Build the vector index at image build time so the container is ready to serve.
# The app also re-ingests on startup when the index is missing, which covers
# deployments that mount an empty volume over /app/chroma_store.
RUN python -m app.ingest

# Grant the non-root user ownership of the runtime directories it must write to,
# and make the entrypoint executable while still running as root.
RUN chown -R app:app /app && \
    chmod +x /usr/local/bin/docker-entrypoint.sh

USER app

EXPOSE 8000

# Liveness only checks that the process serves HTTP. Use /api/v1/live, which is
# index-agnostic: /api/v1/health returns 503 when the index is not loaded, so
# pointing the container healthcheck at it would mark a merely-unindexed
# container unhealthy. Readiness is /api/v1/ready, which keeps traffic off a
# replica whose index is not queryable yet.
# Reads PORT so this stays correct when a platform overrides the listen port.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/v1/live', timeout=3)"

# Single worker per container on purpose: /metrics is served from an in-process
# Prometheus registry, so multiple workers would report partial metrics. Scale
# with replicas (see the HPA) instead of WORKERS.
#
# The entrypoint honours $PORT/$HOST and optionally trusts X-Forwarded-* when
# running behind a platform proxy such as Render's.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
