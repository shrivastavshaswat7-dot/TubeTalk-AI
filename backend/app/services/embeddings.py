"""Local embeddings (all-MiniLM-L6-v2, 384 dimensions) on ONNX Runtime via FastEmbed.

FastEmbed runs the same model as sentence-transformers without PyTorch, so the backend fits in a
512 MB free host. Its vectors match the sentence-transformers ones (cosine 1.000000, max element
difference ~2e-7 on the project's transcripts), so chunks stored earlier stay valid.
"""
from functools import lru_cache

import numpy as np

from app.core.config import get_settings
from app.core.errors import AppError

EMBEDDING_DIMENSION = 384  # must match vector(384) in database/migrations/001_init.sql
BATCH_SIZE = 8  # ONNX Runtime memory grows with the batch: 8 keeps embedding at ~256 MB peak


def _embedding_error() -> AppError:
    return AppError("EMBEDDING_ERROR", "Could not generate embeddings. Please try again.", 500)


class _FastEmbedModel:
    """sentence-transformers style encode() on top of FastEmbed."""

    def __init__(self, name: str):
        from fastembed import TextEmbedding

        self._model = TextEmbedding(name)

    def encode(self, texts, batch_size=BATCH_SIZE, normalize_embeddings=True, show_progress_bar=False):
        vectors = np.asarray(list(self._model.embed(texts, batch_size=batch_size)), dtype=np.float32)
        if normalize_embeddings:
            vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors


@lru_cache
def get_model():
    """Load the model once per process (first call downloads it, then it is cached)."""
    try:
        return _FastEmbedModel(get_settings().embedding_model)
    except Exception:
        raise _embedding_error()


def embed_texts(texts: list[str], model=None) -> list[list[float]]:
    """Embed many texts in batches. Vectors are L2-normalised so cosine == dot product."""
    if not texts:
        return []
    if any(not isinstance(t, str) or not t.strip() for t in texts):
        raise AppError("EMBEDDING_ERROR", "Cannot embed empty text.", 400)
    try:
        vectors = (model or get_model()).encode(
            texts, batch_size=BATCH_SIZE, normalize_embeddings=True, show_progress_bar=False
        )
        result = [[float(x) for x in v] for v in vectors]
    except AppError:
        raise
    except Exception:
        raise _embedding_error()
    if any(len(v) != EMBEDDING_DIMENSION for v in result):
        raise AppError(
            "EMBEDDING_ERROR",
            f"Embedding model produced unexpected dimensions (expected {EMBEDDING_DIMENSION}).",
            500,
        )
    return result


def embed_query(text: str, model=None) -> list[float]:
    """Embed a user question with the SAME model used for transcript chunks."""
    return embed_texts([text], model=model)[0]
