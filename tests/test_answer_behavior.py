"""Behavioural contract for RAG answers (the "verify the chat" step).

Two user-visible guarantees are locked in here:

* the **"not in my notes" gate** - a question outside the corpus is answered
  with an explicit message and no sources, never a guess;
* the **sources field** - a normal answer carries the exact note chunks
  (file, distance, chunk text) that produced it.

The gate unit tests exercise both refusal paths directly: no vocabulary overlap
with the notes, and a hit beyond the relevance-distance cap.
"""

import pytest
from app.config import get_settings
from app.ingest import run_ingestion
from app.main import app
from app.rag import _is_in_notes, generate_answer
from fastapi.testclient import TestClient

client = TestClient(app)
settings = get_settings()

ON_TOPIC = "What is a Kubernetes Deployment?"
OFF_TOPIC = [
    "What's the capital of France?",
    "Who won the 2022 FIFA World Cup?",
    "What is the best pizza recipe?",
    "What is the weather in Tokyo?",
]


@pytest.fixture(scope="module", autouse=True)
def indexed():
    """The gate needs the fitted vectorizer, so build the index once."""
    run_ingestion()
    return True


def _hit(distance: float) -> list[dict]:
    return [{"source": "docker_notes.txt", "distance": distance, "text": "a chunk"}]


# --- The "not in my notes" gate (unit) -------------------------------------
def test_gate_refuses_a_perfect_hit_with_no_vocabulary_overlap():
    """distance 0.0 looks like a perfect match, but the question shares no
    vocabulary with the notes, so the gate must still refuse to answer."""
    assert _is_in_notes(OFF_TOPIC[0], _hit(0.0)) is False


def test_gate_refuses_a_hit_beyond_the_relevance_cap():
    """On-topic vocabulary but a best hit past the cap is not trustworthy."""
    far = settings.relevance_max_distance + 1.0
    assert _is_in_notes(ON_TOPIC, _hit(far)) is False


def test_gate_accepts_an_on_topic_hit_within_the_cap():
    assert _is_in_notes(ON_TOPIC, _hit(0.0)) is True


# --- The gate, end to end (response contract) ------------------------------
@pytest.mark.parametrize("question", OFF_TOPIC)
def test_off_topic_questions_return_not_in_my_notes(question):
    resp = client.post("/api/v1/ask", json={"question": question, "k": 3})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["found"] is False
    assert body["sources"] == [], "a gated answer must cite nothing"
    assert "not in my notes" in body["answer"].lower()


def test_generate_answer_gate_matches_the_api():
    """The library path and the API agree: no index match -> found=False."""
    body = generate_answer(OFF_TOPIC[0])
    assert body["found"] is False
    assert body["sources"] == []
    assert "not in my notes" in body["answer"].lower()


# --- The sources field (response contract) ---------------------------------
def test_on_topic_answer_reports_the_chunks_used():
    resp = client.post("/api/v1/ask", json={"question": ON_TOPIC, "k": 3})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["found"] is True
    assert "not in my notes" not in body["answer"].lower()
    sources = body["sources"]
    assert sources, "a grounded answer must cite the chunks it used"

    for source in sources:
        assert set(source) == {"source", "distance", "text"}
        assert source["source"], "each chunk names the note file it came from"
        assert source["text"], "each chunk carries the text that was used"
        assert isinstance(source["distance"], (int, float))

    # The Kubernetes question must retrieve Kubernetes notes, not just any note.
    assert any("kubernetes" in s["source"] for s in sources)


def test_sources_are_bounded_by_k():
    body = client.post("/api/v1/ask", json={"question": ON_TOPIC, "k": 2}).json()
    assert body["found"] is True
    assert 1 <= len(body["sources"]) <= 2
