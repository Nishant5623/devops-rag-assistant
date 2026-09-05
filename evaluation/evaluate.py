"""
RAG retrieval-quality evaluation harness.

Runs a small set of (question, expected_source) pairs through the retrieval
pipeline and reports retrieval accuracy. Useful for tracking whether changes
to chunking / embeddings regress retrieval.

Usage:
    python -m app.ingest      # ensure index exists
    python evaluation/evaluate.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingest import run_ingestion
from app.rag import retrieve

# (question, expected source file)
GOLDEN_SET = [
    ("What is a Kubernetes Deployment?", "kubernetes_notes.txt"),
    ("How does Docker networking work?", "docker_notes.txt"),
    ("What is an Ansible playbook?", "ansible_notes.txt"),
    ("How do I manage process in Linux?", "linux_notes.txt"),
    ("What is continuous integration?", "cicd_notes.txt"),
]


def evaluate() -> None:
    run_ingestion()
    hits_ok = 0
    for question, expected in GOLDEN_SET:
        results = retrieve(question, k=3)
        sources = [h["source"] for h in results]
        rank = sources.index(expected) + 1 if expected in sources else 0
        hit = bool(rank)
        hits_ok += int(hit)
        print(f"{'PASS' if hit else 'FAIL'}\t{question}\texpected={expected}\trank={rank or 'N/A'}")

    accuracy = hits_ok / len(GOLDEN_SET)
    print(f"\nRetrieval accuracy (recall@3): {accuracy:.0%}")
    if accuracy < 0.8:
        print("WARNING: retrieval accuracy below threshold; consider tuning chunking/embeddings.")


if __name__ == "__main__":
    evaluate()
