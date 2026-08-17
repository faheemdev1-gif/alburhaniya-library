"""
Singleton wrapper around the Arabic sentence-transformer model.
Loading is deferred until first use to keep startup fast.
"""
from __future__ import annotations
import logging
from functools import lru_cache
from typing import List

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info("Loading embedding model: %s (device: %s)", self.model_name, device)
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, device=device)
            logger.info("Model loaded ✓ on %s", device)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self._load()
        prompts = getattr(self._model, "prompts", {}) or {}
        inputs = texts if any(name in prompts for name in ("document", "passage", "corpus")) else [
            f"passage: {text}" for text in texts
        ]
        vectors = self._model.encode_document(
            inputs,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        self._load()
        prompts = getattr(self._model, "prompts", {}) or {}
        value = text if "query" in prompts else f"query: {text}"
        vector = self._model.encode_query(
            [value],
            batch_size=1,
            show_progress_bar=False,
            normalize_embeddings=True,
        )[0]
        return vector.tolist()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Compatibility alias for the dormant legacy ingestion path."""
        return self.embed_documents(texts)

    def embed_one(self, text: str) -> list[float]:
        return self.embed_query(text)


@lru_cache(maxsize=4)
def get_embedding_service(model_name: str) -> EmbeddingService:
    return EmbeddingService(model_name)
