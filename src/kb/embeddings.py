"""Pembungkus model embedding Sentence-Transformers."""

from __future__ import annotations

from typing import List, Protocol, Sequence

import numpy as np


class Embedder(Protocol):
    name: str
    max_seq_length: int

    def encode(self, texts: Sequence[str]) -> np.ndarray: ...

    def count_tokens(self, texts: Sequence[str]) -> List[int]: ...


class SentenceTransformerEmbedder:
    """Menghasilkan vektor ternormalisasi L2, sehingga dot product = cosine."""

    def __init__(self, model_name: str, batch_size: int = 32) -> None:
        from sentence_transformers import SentenceTransformer

        self.name = model_name
        self.batch_size = batch_size
        self.model = SentenceTransformer(model_name)
        self.max_seq_length = int(self.model.max_seq_length)

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        vectors = self.model.encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)

    def count_tokens(self, texts: Sequence[str]) -> List[int]:
        tokenizer = self.model.tokenizer
        return [len(tokenizer.encode(t, add_special_tokens=True, truncation=False)) for t in texts]
