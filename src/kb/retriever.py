"""Retriever: vektor, BM25, hybrid (RRF), filter metadata, penolakan out-of-domain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from .lexical import BM25Index
from .vector_store import Hit

RRF_K = 60  # nilai lazim dari makalah RRF (Cormack dkk., 2009)


def reciprocal_rank_fusion(rankings: Sequence[Sequence[Hit]], k: int, rrf_k: int = RRF_K) -> List[Hit]:
    """Menggabungkan peringkat tanpa perlu menyamakan skala skor."""
    scores: Dict[str, float] = {}
    best: Dict[str, Hit] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            scores[hit.id] = scores.get(hit.id, 0.0) + 1.0 / (rrf_k + rank)
            if hit.id not in best or (best[hit.id].similarity is None and hit.similarity is not None):
                best[hit.id] = hit
    ordered = sorted(scores, key=lambda i: (-scores[i], i))
    return [best[i] for i in ordered[:k]]


@dataclass
class SearchResponse:
    query: str
    rejected: bool
    top_similarity: Optional[float]
    hits: List[Hit]


class Retriever:
    def __init__(self, index: Any, embedder: Any, bm25: BM25Index, threshold: float) -> None:
        self.index, self.embedder, self.bm25, self.threshold = index, embedder, bm25, threshold

    def search_with_embedding(self, query: str, query_embedding: np.ndarray, k: int = 5,
                              mode: str = "hybrid", where: Optional[Dict[str, Any]] = None,
                              candidates: int = 20) -> SearchResponse:
        vector_hits = self.index.query(query_embedding, k=max(k, candidates), where=where)
        top = vector_hits[0].similarity if vector_hits else None
        if mode == "vector":
            hits = vector_hits[:k]
        elif mode == "bm25":
            hits = [h for h, _ in self.bm25.query(query, k=k, where=where)]
        elif mode == "hybrid":
            lexical = [h for h, _ in self.bm25.query(query, k=max(k, candidates), where=where)]
            hits = reciprocal_rank_fusion([vector_hits, lexical], k)
        else:
            raise ValueError(f"Mode tidak dikenal: {mode}")
        rejected = top is None or top < self.threshold
        return SearchResponse(query, rejected, top, hits)

    def search(self, query: str, k: int = 5, mode: str = "hybrid",
               where: Optional[Dict[str, Any]] = None) -> SearchResponse:
        embedding = self.embedder.encode([query])[0]
        return self.search_with_embedding(query, embedding, k=k, mode=mode, where=where)
