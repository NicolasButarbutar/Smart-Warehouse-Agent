"""Pengujian metrik, BM25, hybrid search, dan kalibrasi ambang Milestone 3."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from kb.evaluate import (answer_rank, calibrate_threshold, doc_ranking, evaluate_query, first_relevant_rank,  # noqa: E402
                         lexical_overlap, rejection_metrics, roc_auc, summarize, wilson_interval)
from kb.ingest import METADATA_FIELDS, build_chunks, build_records  # noqa: E402
from kb.lexical import BM25Index, tokenize  # noqa: E402
from kb.preprocess import load_corpus  # noqa: E402
from kb.retriever import Retriever, reciprocal_rank_fusion  # noqa: E402
from kb.vector_store import Hit, NumpyIndex, matches_where  # noqa: E402
from kb_helpers import HashingEmbedder  # noqa: E402

CORPUS = ROOT / "data" / "raw" / "corpus"
QUERIES = json.loads((ROOT / "data" / "benchmark" / "queries.json").read_text(encoding="utf-8"))


def hit(doc, text="isi", sim=0.5, id_=None):
    return Hit(id_ or f"{doc}-{text}", text, {"doc_id": doc}, sim)


def test_doc_ranking_deduplicates_and_keeps_order():
    assert doc_ranking([hit("A"), hit("A", "b"), hit("B")]) == ["A", "B"]


def test_first_relevant_rank_is_document_level():
    hits = [hit("A"), hit("A", "b"), hit("B")]
    assert first_relevant_rank(hits, ["B"]) == 2
    assert first_relevant_rank(hits, ["C"]) == 0


def test_answer_rank_needs_target_doc_and_term():
    hits = [hit("A", "suhu 8 derajat"), hit("B", "suhu 8 derajat")]
    assert answer_rank(hits, ["B"], ["8 DERAJAT"]) == 2
    assert answer_rank(hits, ["B"], ["18 derajat"]) == 0


def test_summarize_computes_hit_and_mrr():
    rows = [evaluate_query({"target_docs": ["A"], "answer_terms": ["isi"]}, [hit("A")]),
            evaluate_query({"target_docs": ["B"], "answer_terms": ["isi"]}, [hit("A"), hit("B")])]
    result = summarize(rows)
    assert result["hit_at_1"] == 0.5 and result["hit_at_3"] == 1.0 and result["mrr"] == 0.75


def test_wilson_interval_bounds():
    low, high = wilson_interval(9, 10)
    assert 0.55 < low < 0.6 and 0.98 < high <= 1.0
    assert wilson_interval(0, 0) == (0.0, 0.0)


def test_roc_auc_perfect_and_tie():
    assert roc_auc([0.9, 0.8], [0.1, 0.2]) == 1.0
    assert roc_auc([0.5], [0.5]) == 0.5


def test_rejection_metrics_treat_ood_as_positive():
    metrics = rejection_metrics([0.8, 0.3], [0.2, 0.6], 0.5)
    assert (metrics["tp"], metrics["fp"], metrics["fn"], metrics["tn"]) == (1, 1, 1, 1)
    assert metrics["precision"] == 0.5 and metrics["recall"] == 0.5


def test_calibration_separates_when_possible():
    chosen = calibrate_threshold([0.7, 0.8, 0.9], [0.2, 0.3], 0.1)
    assert 0.3 < chosen["threshold"] < 0.7 and chosen["f1"] == 1.0 and chosen["constraint_met"]


def test_calibration_respects_false_reject_limit():
    in_domain = [0.2] + [0.8] * 19
    ood = [0.3, 0.35]
    chosen = calibrate_threshold(in_domain, ood, 0.1)
    assert chosen["false_reject_rate"] <= 0.1


def test_lexical_overlap_ignores_stopwords():
    assert lexical_overlap("apa suhu ruang", "suhu ruang dingin") == 1.0
    assert lexical_overlap("kata lain", "suhu ruang") == 0.0


def test_tokenize_keeps_numbers_and_codes():
    assert "e-305" in tokenize("Kode E-305 berarti lot diblokir")
    assert "yang" not in tokenize("barang yang rusak")


@pytest.mark.parametrize("where,expected", [
    ({"a": 1}, True), ({"a": 2}, False), ({"a": {"$in": [1, 2]}}, True), ({"a": {"$ne": 1}}, False),
    ({"$and": [{"a": 1}, {"b": "x"}]}, True), ({"$or": [{"a": 9}, {"b": "x"}]}, True),
    ({"a": {"$gte": 2}}, False), (None, True),
])
def test_matches_where(where, expected):
    assert matches_where({"a": 1, "b": "x"}, where) is expected


def test_rrf_rewards_agreement():
    a, b, c = hit("A", id_="a"), hit("B", id_="b"), hit("C", id_="c")
    assert [h.id for h in reciprocal_rank_fusion([[a, b], [c, b]], 3)][0] == "b"


def test_rrf_prefers_hit_with_similarity():
    with_sim = hit("A", id_="a", sim=0.7)
    without = hit("A", id_="a", sim=None)
    assert reciprocal_rank_fusion([[without], [with_sim]], 1)[0].similarity == 0.7


@pytest.fixture(scope="module")
def retriever():
    embedder = HashingEmbedder()
    pairs = build_chunks(load_corpus(CORPUS), 70, 14)
    records = build_records(pairs, embedder)
    index = NumpyIndex(records["ids"], embedder.encode(records["texts"]), records["documents"], records["metadatas"])
    return Retriever(index, embedder, BM25Index(records["ids"], records["documents"], records["metadatas"]), 0.0), records


def test_metadata_is_complete_for_hybrid_search(retriever):
    _, records = retriever
    for meta in records["metadatas"]:
        assert set(METADATA_FIELDS) <= set(meta)
        assert all(isinstance(meta[f], (str, int, float, bool)) and meta[f] != "" for f in METADATA_FIELDS)
    assert len(set(records["ids"])) == len(records["ids"])


def test_bm25_finds_literal_code(retriever):
    engine, _ = retriever
    response = engine.search("kode E-305", k=3, mode="bm25")
    assert response.hits[0].metadata["doc_id"] == "MAN-01"


@pytest.mark.parametrize("mode", ["vector", "bm25", "hybrid"])
def test_filter_applies_in_every_mode(retriever, mode):
    engine, _ = retriever
    response = engine.search("suhu ruang dingin", k=5, mode=mode, where={"kategori": "Rantai Dingin"})
    assert response.hits and all(h.metadata["kategori"] == "Rantai Dingin" for h in response.hits)


def test_threshold_rejects_low_similarity(retriever):
    engine, _ = retriever
    strict = Retriever(engine.index, engine.embedder, engine.bm25, threshold=1.5)
    assert strict.search("suhu", mode="vector").rejected
    assert not engine.search("suhu", mode="vector").rejected


def test_unknown_mode_raises(retriever):
    engine, _ = retriever
    with pytest.raises(ValueError):
        engine.search("suhu", mode="salah")


def test_benchmark_set_is_valid_against_corpus():
    documents = {d.doc_id: d.to_text().lower() for d in load_corpus(CORPUS)}
    ids = [q["id"] for q in QUERIES]
    assert len(ids) == len(set(ids)) and len(ids) >= 5
    for query in QUERIES:
        assert query["split"] in {"dev", "test"}
        if query["tipe"] == "ood":
            assert not query["target_docs"] and query["ood_jenis"] in {"jauh", "dekat"}
            continue
        assert query["target_docs"] and query["answer_terms"]
        for doc in query["target_docs"]:
            assert doc in documents, query["id"]
        found = any(t.lower() in documents[d] for t in query["answer_terms"] for d in query["target_docs"])
        assert found, query["id"]


def test_each_split_covers_every_query_type():
    for split in ("dev", "test"):
        kinds = {q["tipe"] for q in QUERIES if q["split"] == split}
        assert kinds == {"literal", "sinonim", "ambigu", "ood"}
        assert {q["ood_jenis"] for q in QUERIES if q["split"] == split and q["tipe"] == "ood"} == {"jauh", "dekat"}
    dev, test = [{q["kueri"] for q in QUERIES if q["split"] == s} for s in ("dev", "test")]
    assert not dev & test


def test_vector_scores_are_cosine(retriever):
    engine, records = retriever
    embedding = engine.embedder.encode(["suhu ruang"])[0]
    assert np.isclose(np.linalg.norm(embedding), 1.0)
    top = engine.index.query(embedding, k=1)[0]
    assert -1.0 <= top.similarity <= 1.0
