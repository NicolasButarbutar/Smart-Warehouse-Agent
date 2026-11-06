"""Embedder deterministik untuk pengujian; tidak dipakai untuk hasil benchmark."""

import hashlib
import re

import numpy as np


class HashingEmbedder:
    name = "hashing-test-embedder"
    max_seq_length = 128

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def encode(self, texts):
        vectors = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in re.findall(r"\w+", text.lower()):
                slot = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % self.dim
                vectors[row, slot] += 1.0
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vectors / norms

    def count_tokens(self, texts):
        return [len(t.split()) + 2 for t in texts]
