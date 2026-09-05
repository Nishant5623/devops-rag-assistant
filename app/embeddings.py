"""
Lightweight local embedding function for ChromaDB.

TF-IDF (scikit-learn) is fitted on the ingested corpus itself, so indexing
and retrieval run fully locally with no external model download and no API
key. Swapping this out for a dense embedding model (e.g. OpenAI/HuggingFace)
later is a drop-in change: implement the same `__call__` interface.
"""
import pickle
from pathlib import Path

from chromadb import Documents, EmbeddingFunction, Embeddings
from sklearn.feature_extraction.text import TfidfVectorizer

from app.config import get_settings


class TfidfEmbeddingFunction(EmbeddingFunction):
    """Chroma-compatible embedding function backed by a fitted TfidfVectorizer."""

    def __init__(self, vectorizer_path: str | Path | None = None):
        settings = get_settings()
        self.vectorizer_path = Path(vectorizer_path or settings.vectorizer_path)
        self.max_features = settings.tfidf_max_features
        self.vectorizer: TfidfVectorizer | None = None
        if self.vectorizer_path.exists():
            self._load()

    def fit(self, corpus: list[str]) -> None:
        """Fit the vectorizer on the full corpus once, at ingestion time."""
        self.vectorizer = TfidfVectorizer(
            max_features=self.max_features, stop_words="english"
        )
        self.vectorizer.fit(corpus)
        self._save()

    def _save(self) -> None:
        # Ensure parent directory exists so saves are robust across deploys.
        self.vectorizer_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.vectorizer_path, "wb") as f:
            pickle.dump(self.vectorizer, f)

    def _load(self) -> None:
        with open(self.vectorizer_path, "rb") as f:
            self.vectorizer = pickle.load(f)

    def __call__(self, input: Documents) -> Embeddings:
        if self.vectorizer is None:
            raise RuntimeError(
                "Vectorizer not fitted yet. Run ingestion before querying."
            )
        matrix = self.vectorizer.transform(input).toarray().tolist()
        return matrix


# Explicit export so tests and callers have one obvious import surface.
embedding_function = TfidfEmbeddingFunction
