"""Penyimpanan vektor: ChromaDB persisten dan indeks numpy untuk eksperimen."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np


@dataclass
class Hit:
    id: str
    text: str
    metadata: Dict[str, Any]
    similarity: Optional[float]


def matches_where(metadata: Dict[str, Any], where: Optional[Dict[str, Any]]) -> bool:
    """Evaluator filter metadata bersintaks Chroma, untuk BM25 dan indeks numpy."""
    if not where:
        return True
    for key, condition in where.items():
        if key == "$and":
            if not all(matches_where(metadata, c) for c in condition):
                return False
        elif key == "$or":
            if not any(matches_where(metadata, c) for c in condition):
                return False
        elif isinstance(condition, dict):
            value = metadata.get(key)
            for op, expected in condition.items():
                if op == "$eq" and value != expected:
                    return False
                if op == "$ne" and value == expected:
                    return False
                if op == "$in" and value not in expected:
                    return False
                if op == "$nin" and value in expected:
                    return False
                if op in {"$gt", "$gte", "$lt", "$lte"}:
                    if value is None:
                        return False
                    ok = {"$gt": value > expected, "$gte": value >= expected,
                          "$lt": value < expected, "$lte": value <= expected}[op]
                    if not ok:
                        return False
        elif metadata.get(key) != condition:
            return False
    return True


class NumpyIndex:
    """Pencarian eksak. Dipakai pada eksperimen dan pembanding hasil HNSW."""

    def __init__(self, ids: Sequence[str], embeddings: np.ndarray,
                 documents: Sequence[str], metadatas: Sequence[Dict[str, Any]]) -> None:
        self.ids = list(ids)
        self.embeddings = np.asarray(embeddings, dtype=np.float32)
        self.documents = list(documents)
        self.metadatas = list(metadatas)

    def query(self, query_embedding: np.ndarray, k: int = 5,
              where: Optional[Dict[str, Any]] = None) -> List[Hit]:
        scores = self.embeddings @ np.asarray(query_embedding, dtype=np.float32)
        hits = []
        for i in np.argsort(-scores):
            if matches_where(self.metadatas[i], where):
                hits.append(Hit(self.ids[i], self.documents[i], self.metadatas[i], float(scores[i])))
                if len(hits) == k:
                    break
        return hits


class ChromaKnowledgeBase:
    """Akses ke koleksi ChromaDB persisten berjarak cosine."""

    def __init__(self, persist_dir: Path, collection_name: str) -> None:
        import chromadb
        from chromadb.config import Settings

        persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(persist_dir), settings=Settings(anonymized_telemetry=False)
        )
        self.collection_name = collection_name
        self._collection = None

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.client.get_collection(self.collection_name, embedding_function=None)
        return self._collection

    def rebuild(self, ids: Sequence[str], embeddings: np.ndarray, documents: Sequence[str],
                metadatas: Sequence[Dict[str, Any]], collection_meta: Dict[str, Any],
                batch_size: int = 256) -> int:
        """Membangun ulang koleksi; idempoten untuk korpus dan konfigurasi yang sama."""
        existing = {c.name if hasattr(c, "name") else c for c in self.client.list_collections()}
        if self.collection_name in existing:
            self.client.delete_collection(self.collection_name)
        collection = self.client.create_collection(
            self.collection_name,
            embedding_function=None,  # vektor dihitung sendiri oleh Sentence-Transformers
            configuration={"hnsw": {"space": "cosine"}},
            metadata={"metode_jarak": "cosine", **collection_meta},
        )
        self._collection = collection
        for start in range(0, len(ids), batch_size):
            end = start + batch_size
            collection.upsert(
                ids=list(ids[start:end]),
                embeddings=np.asarray(embeddings[start:end], dtype=np.float32).tolist(),
                documents=list(documents[start:end]),
                metadatas=list(metadatas[start:end]),
            )
        self._verify_cosine(ids, embeddings)
        return collection.count()

    def _verify_cosine(self, ids: Sequence[str], embeddings: np.ndarray) -> None:
        """Gagal lantang bila skor Chroma bukan cosine, agar laporan tidak keliru."""
        vectors = np.asarray(embeddings, dtype=np.float32)
        lookup = {identifier: i for i, identifier in enumerate(ids)}
        for hit in self.query(vectors[0], k=min(5, len(ids))):
            expected = float(vectors[lookup[hit.id]] @ vectors[0])
            if abs(hit.similarity - expected) > 0.01:
                raise RuntimeError(
                    f"Skor ChromaDB {hit.similarity:.4f} berbeda dari cosine {expected:.4f}. "
                    "Periksa konfigurasi ruang jarak koleksi."
                )

    def count(self) -> int:
        return self.collection.count()

    def query(self, query_embedding: np.ndarray, k: int = 5,
              where: Optional[Dict[str, Any]] = None) -> List[Hit]:
        total = self.count()
        kwargs: Dict[str, Any] = {}
        if where:
            kwargs["where"] = where
        result = self.collection.query(
            query_embeddings=[np.asarray(query_embedding, dtype=np.float32).tolist()],
            n_results=min(k, total),
            include=["documents", "metadatas", "distances"],
            **kwargs,
        )
        return [
            Hit(i, doc, meta, 1.0 - float(dist))  # jarak cosine Chroma = 1 - cos
            for i, doc, meta, dist in zip(
                result["ids"][0], result["documents"][0],
                result["metadatas"][0], result["distances"][0],
            )
        ]

    def get_all(self) -> Dict[str, Any]:
        return self.collection.get(include=["documents", "metadatas", "embeddings"])
