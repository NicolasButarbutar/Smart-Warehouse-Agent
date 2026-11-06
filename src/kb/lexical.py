"""BM25 murni Python: baseline pencarian kata kunci dan komponen hybrid search."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .vector_store import Hit, matches_where

_TOKEN = re.compile(r"[a-z0-9]+(?:[-.,][a-z0-9]+)*")
STOPWORDS = frozenset(
    """yang dan di ke dari untuk pada dengan atau ini itu adalah oleh dalam akan tidak
    harus bila jika saat agar serta sebagai para apa berapa bagaimana siapa kapan mana
    apakah kalau boleh kita saya kami sudah lebih sampai the of a an to for in is are""".split()
)


def tokenize(text: str) -> List[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS]


class BM25Index:
    def __init__(self, ids: Sequence[str], documents: Sequence[str],
                 metadatas: Sequence[Dict[str, Any]], k1: float = 1.5, b: float = 0.75) -> None:
        self.ids, self.documents, self.metadatas = list(ids), list(documents), list(metadatas)
        self.k1, self.b = k1, b
        self.term_counts = [Counter(tokenize(self._searchable(i))) for i in range(len(self.ids))]
        self.lengths = [sum(c.values()) for c in self.term_counts]
        self.avg_length = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        df: Counter = Counter()
        for counts in self.term_counts:
            df.update(counts.keys())
        n = len(self.ids)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def _searchable(self, i: int) -> str:
        meta = self.metadatas[i]
        return f"{meta.get('judul', '')} {meta.get('bab', '')} {self.documents[i]}"

    def _score(self, terms: Sequence[str], i: int) -> float:
        counts, score = self.term_counts[i], 0.0
        norm = 1 - self.b + self.b * self.lengths[i] / (self.avg_length or 1.0)
        for term in terms:
            freq = counts.get(term, 0)
            if freq:
                score += self.idf[term] * freq * (self.k1 + 1) / (freq + self.k1 * norm)
        return score

    def query(self, text: str, k: int = 5, where: Optional[Dict[str, Any]] = None) -> List[Tuple[Hit, float]]:
        terms = tokenize(text)
        scored = []
        for i in range(len(self.ids)):
            if matches_where(self.metadatas[i], where):
                score = self._score(terms, i)
                if score > 0:
                    scored.append((score, i))
        scored.sort(key=lambda s: (-s[0], self.ids[s[1]]))
        return [
            (Hit(self.ids[i], self.documents[i], self.metadatas[i], None), score)
            for score, i in scored[:k]
        ]
