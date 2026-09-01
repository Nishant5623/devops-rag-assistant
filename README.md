# DevOps Knowledge Assistant — a minimal RAG app

[![CI](https://github.com/Nishant5623/devops-rag-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/Nishant5623/devops-rag-assistant/actions/workflows/ci.yml)

> **Live demo:** (link coming soon) — deploy this repo or `docker run` the
> image below, then open the single-page chat UI at `/`.

A small, working Retrieval-Augmented Generation (RAG) service built with
**FastAPI**, **LangChain**, and **ChromaDB**, that answers questions over a
local knowledge base of DevOps notes (Docker, Kubernetes, Linux, CI/CD,
Ansible) instead of relying on the LLM's training data alone.

> RAG here means retrieval from **my own document collection**, not the
> internet — the app searches only the files in `data/`, then hands the most
> relevant chunks to an LLM as grounding context before it answers.

## Demo

Once running locally, open **http://localhost:8000/** for the single-page,
dark-mode chat UI. It keeps a chat-bubble conversation history, shows each
answer's cited sources (filename + relevance) in smaller text below it, and
shows a typing indicator while waiting for a response.

<!-- Screenshots: replace the lines below with your own captures after running
     it locally. 1. The chat UI 2. The /docs Swagger UI 3. A sample /ask
     response with retrieved sources.
![Chat UI](docs/screenshot-chat.png)
![Swagger UI](docs/screenshot-swagger.png)
![Sample query](docs/screenshot-query.png)
--> 

**Example query:**
```json
POST /ask
{ "question": "What is a Kubernetes Deployment?", "k": 3 }
```
**Response (sources always show which notes were actually used):**
```json
{
  "answer": "...A Deployment manages a set of replica Pods and handles rolling updates and rollbacks...",
  "sources": [
    { "source": "kubernetes_notes.txt", "distance": 1.07 },
    { "source": "kubernetes_notes.txt", "distance": 1.62 },
    { "source": "kubernetes_notes.txt", "distance": 1.83 }
  ]
}
```

## How it works

```
data/*.txt  --chunk-->  TF-IDF vectorizer  --embed-->  ChromaDB (vector store)
                                                              |
question  --embed (same vectorizer)-->  similarity search ---'
                                                              |
                                                  top-k chunks (context)
                                                              |
                                        LangChain + Claude ---'--> answer
```

1. **Ingestion** (`app/ingest.py`) — reads every `.txt` file in `data/`, splits
   it into overlapping chunks with LangChain's `RecursiveCharacterTextSplitter`,
   and indexes the chunks into a persistent ChromaDB collection.
2. **Embeddings** (`app/embeddings.py`) — a custom Chroma-compatible embedding
   function backed by scikit-learn's `TfidfVectorizer`, fitted on the corpus at
   ingestion time. Fully local — no pretrained model download required, which
   also makes it easy to explain end-to-end. Swapping in a dense embedding
   model (OpenAI/HuggingFace) later is a drop-in change behind the same
   interface.
3. **Retrieval + generation** (`app/rag.py`) — embeds the incoming question
   with the same vectorizer, retrieves the top-k most similar chunks from
   Chroma, and passes them as context to Claude (via `langchain-anthropic`) to
   generate a grounded answer. With no API key configured, it still returns
   the retrieved context directly (extractive fallback), so the retrieval
   half of the pipeline is fully testable without any key.
4. **API** (`app/main.py`) — a FastAPI app with the endpoints below. It also
   applies per-IP rate limiting on `/ask` (10 req/min), validates `question`
   (3–500 chars) and `k` (1–10), and exposes Prometheus metrics.

## Endpoints

| Method | Path      | Description                                              |
|--------|-----------|-------------------------------------------------------------|
| GET    | `/`         | Single-page chat frontend (served as static files)        |
| GET    | `/health` | Health check incl. whether the vector index is loaded      |
| POST   | `/ingest` | (Re)build the vector index from `data/`                    |
| POST   | `/ask`    | `{"question": "...", "k": 3}` → grounded answer + sources  |
| GET    | `/metrics` | Prometheus metrics (request count, latency, etc.)          |

> `/ask` is rate limited to **10 requests per minute per IP**. Setting `k` to a
> value outside 1–10 or asking a question shorter than 3 or longer than 500
> characters returns a `422` validation error.

## Running it

**macOS / Linux**
```bash
pip install -r requirements.txt
python -m app.ingest          # build the index once
export ANTHROPIC_API_KEY=...  # optional — enables real LLM-generated answers
uvicorn app.main:app --reload
```

**Windows (PowerShell)**
```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m app.ingest
$env:ANTHROPIC_API_KEY="..."   # optional
uvicorn app.main:app --reload
```

Then open **http://localhost:8000/** for the chat UI, or
**http://localhost:8000/docs** for an interactive API test UI, or:
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is a Kubernetes Deployment?", "k": 3}'
```

**Running tests:**
```bash
pytest -v
```

**Running with Docker:**
```bash
docker build -t devops-rag-assistant .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=... devops-rag-assistant
```
The image builds the vector index at build time, then serves the API and the
chat UI at `http://localhost:8000/`.

## Design choices worth knowing (things I'd expect to be asked about)

- **TF-IDF instead of neural embeddings**: chosen for a fully-local,
  no-download, no-API-key-required indexing step. The trade-off is weaker
  semantic recall than dense embeddings — it matches on vocabulary overlap,
  not meaning. Swapping in OpenAI/HuggingFace embeddings for production use
  would be a natural next step, behind the same `EmbeddingFunction` interface.
- **Extractive fallback with no API key**: keeps the retrieval half of the
  system fully testable and honest about what's "real" vs. what needs a key.
- **Idempotent ingestion**: re-running `/ingest` rebuilds the collection from
  scratch rather than silently duplicating chunks.

## Tech stack
Python · FastAPI · LangChain · ChromaDB (vector database) · scikit-learn ·
slowapi (rate limiting) · Prometheus (metrics via prometheus-fastapi-instrumentator)

## Possible extensions
- Swap the `.txt` loader for PDFs (`pypdf` is already in `requirements.txt`)
- Swap TF-IDF for a dense embedding model
- Add multi-turn conversation memory
- Deploy behind a managed vector DB (Pinecone/Qdrant)
