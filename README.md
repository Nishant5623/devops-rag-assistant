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
- **Rate limiting** per-IP on `/ask` (slowapi) and `/ingest`
- **Prometheus metrics** + **Grafana dashboard** + alerting rules
- **Structured JSON logging** and **OpenTelemetry tracing** (optional collector)
- **Request-ID correlation** and hardened **security headers**
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
| GET    | `/api/v1/health` | Health check incl. index status + version         |
| POST   | `/api/v1/ingest` | (Re)build the vector index from `data/` (admin)   |
| POST   | `/api/v1/ask`    | `{"question": "...", "k": 3}` → answer + sources  |
| GET    | `/metrics` | Prometheus metrics                                     |
| GET    | `/docs`    | Interactive OpenAPI / Swagger UI                       |

- `POST /ask` is rate-limited (default **10/min/IP**).
- `POST /ingest` and `/metrics` can be protected with `ADMIN_API_KEY`
  (sent via the `X-Admin-Key` header). Empty key = open (local dev only).
- `question` is validated to 3–500 chars, `k` to 1–10 (422 otherwise).

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

The chart deploys a Deployment (with liveness/readiness probes), Service,
ConfigMap, Secret, HorizontalPodAutoscaler, Ingress, and PodDisruptionBudget —
all running as a **non-root** user.

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
| `ENV` | `development` | Switches to structured JSON logging when `production` |
| `LOG_LEVEL` | `INFO` | Log verbosity |
| `WORKERS` | `1` | Uvicorn worker count |
| `CORS_ORIGINS` | `*` | Allowed origins (restrict in production) |
| `ADMIN_API_KEY` | *(empty)* | Protects `/ingest` & `/metrics` via `X-Admin-Key` |
| `OTLP_ENDPOINT` | *(empty)* | Enable OpenTelemetry tracing (e.g. `collector:4317`) |

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
