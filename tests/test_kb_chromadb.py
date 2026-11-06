"""Pengujian integrasi ChromaDB asli; dilewati bila chromadb belum terpasang."""

import sys
from pathlib import Path

import numpy as np
import pytest

chromadb = pytest.importorskip("chromadb")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from kb import config as cfg  # noqa: E402
from kb.benchmark import build_index  # noqa: E402
from kb.preprocess import load_corpus  # noqa: E402
from kb.vector_store import ChromaKnowledgeBase, NumpyIndex  # noqa: E402
from kb_helpers import HashingEmbedder  # noqa: E402


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    base = tmp_path_factory.mktemp("kb")
    conf = cfg.KBConfig(model_name="hash", chunk_words=70, overlap_words=14, threshold=0.2)
    result = build_index(load_corpus(ROOT / "data" / "raw" / "corpus"), HashingEmbedder(), conf,
                         persist_dir=base / "store", clean_dir=base / "clean",
                         chunks_path=base / "chunks.jsonl", report_path=base / "report.json")
    return base, result


def test_all_chunks_are_indexed(built):
    _, result = built
    assert result["store"].count() == len(result["records"]["ids"]) > 0


def test_index_persists_after_reopening(built):
    base, result = built
    reopened = ChromaKnowledgeBase(base / "store", cfg.COLLECTION_NAME)
    assert reopened.count() == result["store"].count()


def test_collection_records_build_config(built):
    _, result = built
    meta = result["store"].collection.metadata
    assert meta["metode_jarak"] == "cosine" and meta["chunk_kata"] == 70


def test_similarity_matches_exact_cosine(built):
    _, result = built
    records = result["records"]
    vector = HashingEmbedder().encode(["suhu ruang dingin"])[0]
    exact = NumpyIndex(records["ids"], records["embeddings"], records["documents"], records["metadatas"]).query(vector, k=1)[0]
    stored = result["store"].query(vector, k=1)[0]
    assert np.isclose(stored.similarity, exact.similarity, atol=1e-3)


def test_metadata_filter_in_chromadb(built):
    _, result = built
    vector = HashingEmbedder().encode(["suhu"])[0]
    hits = result["store"].query(vector, k=5, where={"$and": [{"kategori": "Rantai Dingin"}, {"tahun_berlaku": {"$gte": 2026}}]})
    assert hits and all(h.metadata["kategori"] == "Rantai Dingin" for h in hits)


def test_rebuild_is_idempotent(built):
    base, result = built
    records = result["records"]
    store = ChromaKnowledgeBase(base / "store", cfg.COLLECTION_NAME)
    count = store.rebuild(records["ids"], records["embeddings"], records["documents"], records["metadatas"], {"chunk_kata": 70})
    assert count == len(records["ids"])
