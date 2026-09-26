#!/bin/sh
# Container entrypoint.
#
# Render (and most PaaS) assign the listen port at runtime via $PORT, and they
# terminate TLS at their own proxy and forward the real client address in
# X-Forwarded-For. Docker Compose and Kubernetes do neither, so both behaviours
# are opt-in via environment variables with safe defaults:
#
#   PORT           listen port           (default 8000)
#   HOST           bind address          (default 0.0.0.0)
#   PROXY_HEADERS  trust X-Forwarded-*   (default 0, set to 1 by render.yaml)
#
# PROXY_HEADERS matters for correctness, not cosmetics. slowapi keys its rate
# limiter on request.client.host, which without --proxy-headers is the
# platform's internal proxy IP for *every* caller. That collapses the whole
# internet into one 10-requests-per-minute bucket. It is off by default because
# trusting X-Forwarded-* from any source would let a direct-to-container client
# spoof its IP and bypass the limiter entirely.
set -eu

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

if [ "${PROXY_HEADERS:-0}" = "1" ]; then
    exec uvicorn app.main:app \
        --host "$HOST" \
        --port "$PORT" \
        --proxy-headers \
        --forwarded-allow-ips='*'
fi

exec uvicorn app.main:app --host "$HOST" --port "$PORT"
