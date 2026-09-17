"""Sanitized representative source from Lodestar.

Local sentence-transformers embedding provider with explicit provenance,
query/passage asymmetry, dimensionality validation and lazy model loading.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class EmbeddingStamp:
    embed_provider: str
    embed_model: str
    embed_version: str
    embed_dim: int

    def as_metadata(self) -> dict:
        return {
            "embed_provider": self.embed_provider,
            "embed_model": self.embed_model,
            "embed_version": self.embed_version,
            "embed_dim": self.embed_dim,
        }


class EmbeddingProvider(Protocol):
    @property
    def dim(self) -> int: ...

    @property
    def stamp(self) -> EmbeddingStamp: ...

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


_BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class SentenceTransformersProvider:
    def __init__(self, model_name: str, dim: int):
        import threading

        self._model_name = model_name
        self._dim = dim
        self._model = None
        self._load_lock = threading.Lock()
        self._use_bge_prefix = "bge" in model_name.lower()
        version = model_name.rsplit("-", 1)[-1] if "-" in model_name else "unknown"
        self._stamp = EmbeddingStamp(
            embed_provider="sentence_transformers",
            embed_model=model_name,
            embed_version=version,
            embed_dim=dim,
        )

    def _ensure_model(self):
        if self._model is None:
            with self._load_lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    model = SentenceTransformer(self._model_name)
                    loaded_dim = model.get_sentence_embedding_dimension()
                    if loaded_dim != self._dim:
                        raise RuntimeError(
                            f"configured dim={self._dim}, but {self._model_name} "
                            f"produces {loaded_dim}; re-index before cutover"
                        )
                    self._model = model
        return self._model

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def stamp(self) -> EmbeddingStamp:
        return self._stamp

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        model = self._ensure_model()
        vectors = model.encode(
            list(texts),
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [v.tolist() for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        model = self._ensure_model()
        query = f"{_BGE_QUERY_PREFIX}{text}" if self._use_bge_prefix else text
        vector = model.encode(
            [query],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )[0]
        return vector.tolist()
