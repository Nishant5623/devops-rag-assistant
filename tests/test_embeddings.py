import tempfile
from pathlib import Path

import pytest
from app.embeddings import TfidfEmbeddingFunction


def test_embedding_function_requires_fit_before_call():
    with tempfile.TemporaryDirectory() as tmp:
        ef = TfidfEmbeddingFunction(str(Path(tmp) / "vec.pkl"))
        with pytest.raises(RuntimeError, match="not fitted"):
            ef(["hello world"])


def test_embedding_function_fit_and_call():
    corpus = [
        "docker containers are lightweight and fast",
        "kubernetes orchestrates containers and pods",
    ]
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "vec.pkl")
        ef = TfidfEmbeddingFunction(path)
        ef.fit(corpus)

        vectors = ef(corpus)
        assert len(vectors) == 2
        # Vector length equals the fitted vocabulary size (bounded by max_features).
        assert all(0 < len(v) <= ef.max_features for v in vectors)
        assert len(vectors[0]) == len(vectors[1])

        # Vectorizer is persisted and loadable.
        assert Path(path).exists()
        loaded = TfidfEmbeddingFunction(path)
        assert loaded.vectorizer is not None


def test_embedding_function_saves_to_disk():
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "nested" / "vec.pkl")
        ef = TfidfEmbeddingFunction(path)
        ef.fit(["docker build image", "kubernetes deploy pods"])
        assert Path(path).exists()
