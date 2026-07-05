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

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._load()
        vectors = self._model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return vectors.tolist()

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


@lru_cache(maxsize=1)
def get_embedding_service(model_name: str) -> EmbeddingService:
    return EmbeddingService(model_name)
