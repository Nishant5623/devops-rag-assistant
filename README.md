# DevOps Knowledge Assistant — a production-ready RAG service

[![CI](https://github.com/Nishant5623/devops-rag-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/Nishant5623/devops-rag-assistant/actions/workflows/ci.yml)
[![CD](https://github.com/Nishant5623/devops-rag-assistant/actions/workflows/cd.yml/badge.svg)](https://github.com/Nishant5623/devops-rag-assistant/actions/workflows/cd.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ready-2496ed.svg)](Dockerfile)

A full production-grade **Retrieval-Augmented Generation (RAG)** service built
with **FastAPI**, **LangChain**, **ChromaDB**, and **scikit-learn** that answers
questions over a local knowledge base of DevOps notes (Docker, Kubernetes,
Linux, CI/CD, Ansible).

> **Works fully keyless.** No API key or pretrained-model download is required.
> The app retrieves from its own document collection and returns grounded
> answers. Optionally set `ANTHROPIC_API_KEY` to upgrade to LLM-synthesized
> answers — everything else runs the same.

## ✨ Features

- **Versioned REST API** under `/api/v1` (FastAPI + OpenAPI docs at `/docs`)
- **Fully local RAG**: TF-IDF embeddings + ChromaDB vector store, no external calls needed
- **Self-healing index**: rebuilds the vector store on startup when it is missing
- **Rate limiting** per-IP on `/ask` (slowapi) and `/ingest`
- **Prometheus metrics** + **Grafana dashboard** + alerting rules
- **Structured JSON logging** and **OpenTelemetry tracing** (optional collector)
- **Request-ID correlation** and hardened **security headers**
- **Separate liveness/readiness probes** so an unindexed pod is never sent traffic
- **Optional admin API-key** auth for protected endpoints (`/ingest`, `/metrics`)
- **Multi-stage, non-root Docker image** with healthcheck
- **CI/CD** via GitHub Actions (lint → type-check → test → build → scan → deploy)
- **Kubernetes**: raw manifests (Kustomize), **Helm chart**, and **Terraform** (AWS EKS)
- **Observability stack** via docker-compose (Prometheus + Grafana)

## 🏗 Architecture

```
                    ┌──────────────────────────────────────────────┐
 data/*.txt ───────▶│  Ingestion  (app/ingest.py)                  │
                    │  load → chunk → TF-IDF fit → ChromaDB store  │
                    └──────────────────────────────────────────────┘
                                               ▲
                    ┌──────────────────────────┴──────────────────┐
  question ────────▶│  Retrieval  (app/rag.py)                    │
                    │  embed query → vector search → top-k chunks │
                    └──────────────────────────┬──────────────────┘
                                               ▼
                    ┌──────────────────────────┴──────────────────┐
                    │  Generation                                 │
                    │  extractive fallback  OR  LLM (Claude)      │
                    └───────────────────┬─────────────────────────┘
                                        ▼
                              answer + cited sources
```

## 🔌 Endpoints (all under `/api/v1`)

| Method | Path      | Description                                              |
|--------|-----------|----------------------------------------------------------|
| GET    | `/`         | Single-page chat frontend (static files)               |
| GET    | `/api/v1/health` | Liveness: process is up (always 200)             |
| GET    | `/api/v1/ready`  | Readiness: **503 until the index is queryable**    |
| POST   | `/api/v1/ingest` | (Re)build the vector index from `data/` (admin)   |
| POST   | `/api/v1/ask`    | `{"question": "...", "k": 3}` → answer + sources  |
| GET    | `/metrics` | Prometheus metrics                                     |
| GET    | `/docs`    | Interactive OpenAPI / Swagger UI                       |

- `POST /ask` is rate-limited (default **10/min/IP**).
- `POST /ingest` and `/metrics` can be protected with `ADMIN_API_KEY`
  (sent via the `X-Admin-Key` header). Empty key = open (local dev only).
- `question` is validated to 3–500 chars, `k` to 1–10 (422 otherwise).
- `/health` vs `/ready`: liveness stays 200 so Kubernetes never restart-loops a
  pod that simply has no index yet, while `/ready` returns 503 so an unusable
  replica is pulled out of the load balancer instead of serving 400s.

## 🚀 Quick Start (keyless)

**Local (no key needed):**

```bash
pip install -r requirements.txt
python -m app.ingest          # build the vector index once
uvicorn app.main:app --reload
```
Open **http://localhost:8000/** for the chat UI, or **/docs** for the API UI.

**With the full observability stack (Docker):**

```bash
docker compose up --build
```
- Chat UI: http://localhost:8000/
- Prometheus: http://localhost:9090/
- Grafana: http://localhost:3000/ (admin/admin)

**Standalone Docker:**

```bash
docker build -t devops-rag-assistant .
docker run -p 8000:8000 devops-rag-assistant
```

## 🧪 Testing & Quality

```bash
pip install -r requirements.txt
python -m app.ingest
pytest -v --cov=app --cov-report=term-missing
```

- **Lint/format:** `ruff check . && ruff format .`
- **Type-check:** `mypy app`
- **Security scan:** `bandit -c pyproject.toml -r app -q`
- **Pre-commit:** `pre-commit install`

**Load test** (requires `pip install locust`):
```bash
locust -f loadtest/locustfile.py --host http://localhost:8000
```

**RAG retrieval-quality eval:**
```bash
python -m app.ingest
python evaluation/evaluate.py
```

## ☸️ Deploying to Kubernetes

**Option A — raw manifests (Kustomize):**
```bash
kubectl apply -k k8s/
```

**Option B — Helm:**
```bash
helm upgrade --install devops-rag helm/devops-rag-assistant \
  --namespace devops-rag --create-namespace
# production example:
helm upgrade --install devops-rag helm/devops-rag-assistant \
  --namespace devops-rag \
  --values helm/devops-rag-assistant/values-production.yaml \
  --set secrets.adminApiKey=<your-key> \
  --set image.tag=2.0.0
```

The chart deploys a Deployment (with startup/liveness/readiness probes), Service,
ConfigMap, Secret, HorizontalPodAutoscaler, Ingress, and PodDisruptionBudget —
all running as a **non-root** user.

> **How the index reaches the pod:** the Docker image bakes a prebuilt index in at
> build time, but the chart mounts an `emptyDir` over `/app/chroma_store`, which
> hides it. The app therefore re-ingests on startup when the index is missing
> (`AUTO_INGEST=True`), so every replica is self-sufficient and no manual
> `POST /ingest` is needed. `/api/v1/ready` only returns 200 once that finishes,
> so `helm --wait` blocks until the app can actually answer.
>
> If you replace the `emptyDir` with a persistent volume claim, remember the index
> is per-replica local state: either keep `replicaCount: 1` or let each pod build
> its own copy rather than sharing one volume across replicas.

## 🌩 Deploying to AWS EKS with Terraform

```bash
cd terraform/aws
terraform init
# set TF_VAR_admin_api_key securely, then:
terraform plan -out=tfplan
terraform apply tfplan
```
The Terraform module provisions an EKS cluster, VPC, ECR repo (with
lifecycle policy + image scanning), and deploys the app via the Helm chart.

**CI/CD (GitHub Actions):**
- `CI` runs on every push/PR: lint → type-check → security scan → test w/ coverage.
- On `main`, it builds & pushes the image to GHCR and runs a **Trivy** scan.
- `CD` deploys to EKS via Helm (triggered by CI success or manually).

## ⚙️ Configuration (all optional)

Set via environment variables or a `.env` file (see `.env.example`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | *(empty)* | Enables LLM-synthesized answers; leave empty for keyless mode |
| `ENV` | `development` | Switches to structured JSON logging + HSTS when `production` |
| `LOG_LEVEL` | `INFO` | Log verbosity |
| `AUTO_INGEST` | `True` | Rebuild the index on startup if it is missing |
| `CORS_ORIGINS` | `*` | Allowed origins (restrict in production) |
| `ADMIN_API_KEY` | *(empty)* | Protects `/ingest` & `/metrics` via `X-Admin-Key` |
| `OTLP_ENDPOINT` | *(empty)* | Enable OpenTelemetry tracing (e.g. `collector:4317`) |

> Scale with **replicas**, not uvicorn workers. `/metrics` is served from an
> in-process Prometheus registry, so multiple workers in one container would each
> report partial metrics. Use the HPA (`autoscaling` in the Helm values) instead.

## 🔐 Before you expose this to a network

Keyless mode needs no secrets, but two defaults are deliberately open and should
be changed for anything reachable from outside your workstation:

| Setting | Default | Why it matters |
|---------|---------|----------------|
| `ADMIN_API_KEY` | *(empty)* | Empty disables auth on `POST /ingest` (rebuilds the index) and `GET /metrics`. Set a real secret. |
| `CORS_ORIGINS` | `*` | Allows any origin. Set to your real frontend origin. |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | Only affects `docker compose`; set it before sharing the stack. |

`ANTHROPIC_API_KEY` can stay empty — that is the supported keyless default.

## 🧰 Tech Stack

**Python** · **FastAPI** · **LangChain** · **ChromaDB** (vector DB) ·
**scikit-learn** (TF-IDF) · **slowapi** (rate limiting) · **Prometheus** ·
**Grafana** · **OpenTelemetry** · **Docker** · **GitHub Actions** ·
**Kubernetes** · **Helm** · **Terraform** · **locust**

## 📂 Project Layout

```
app/                 # Python application
  config.py          # centralised settings (pydantic-settings)
  embeddings.py      # TF-IDF Chroma embedding function
  ingest.py          # ingestion pipeline
  rag.py             # retrieval + generation
  main.py            # FastAPI app + routing + middleware
  middleware.py      # request-ID + security headers
  security.py        # admin API-key auth
  logging_config.py  # structured JSON logging
data/                # knowledge base (.txt notes)
static/              # chat frontend (HTML/CSS/JS)
tests/               # pytest suite
k8s/                 # raw Kubernetes manifests (Kustomize)
helm/                # Helm chart
terraform/           # AWS EKS Terraform module
docker/              # Prometheus/Grafana configs + dashboards
loadtest/            # Locust script
evaluation/          # RAG retrieval-quality harness
```

## 📄 License

MIT — see [LICENSE](LICENSE).
