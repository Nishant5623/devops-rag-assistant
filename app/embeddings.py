"""
Lightweight local embedding function for ChromaDB.

Downloading pretrained neural embedding models (e.g. sentence-transformers,
OpenAI/HF hosted weights) requires network access to hosts that aren't
reachable from this environment, so this project uses a TF-IDF vectorizer
(scikit-learn) fitted on the ingested corpus itself. It is fully local,
deterministic, and easy to explain end-to-end: no external model download,
no API key required just to index and retrieve documents.

Swapping this out for a dense embedding model (e.g. OpenAI/HuggingFace
embeddings) later is a drop-in change: implement the same __call__ interface.
"""
import pickle
from pathlib import Path
from typing import List

from sklearn.feature_extraction.text import TfidfVectorizer
from chromadb import Documents, EmbeddingFunction, Embeddings


class TfidfEmbeddingFunction(EmbeddingFunction):
    """Chroma-compatible embedding function backed by a fitted TfidfVectorizer."""

    def __init__(self, vectorizer_path: str = "vectorizer.pkl"):
        self.vectorizer_path = Path(vectorizer_path)
        self.vectorizer: TfidfVectorizer | None = None
        if self.vectorizer_path.exists():
            self._load()

    def fit(self, corpus: List[str]) -> None:
        """Fit the vectorizer on the full corpus once, at ingestion time."""
        self.vectorizer = TfidfVectorizer(max_features=4096, stop_words="english")
        self.vectorizer.fit(corpus)
        self._save()

    def _save(self) -> None:
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
        matrix = self.vectorizer.transform(input)
        return matrix.toarray().tolist()
