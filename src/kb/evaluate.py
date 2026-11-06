"""Metrik temu balik dan kalibrasi ambang penolakan."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple

from .lexical import tokenize
from .vector_store import Hit


def wilson_interval(successes: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Selang kepercayaan 95% Wilson, cocok untuk sampel kecil."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def doc_ranking(hits: Sequence[Hit]) -> List[str]:
    """Daftar dokumen unik, urut menurut kemunculan terbaik."""
    ranking: List[str] = []
    for hit in hits:
        doc = hit.metadata["doc_id"]
        if doc not in ranking:
            ranking.append(doc)
    return ranking


def first_relevant_rank(hits: Sequence[Hit], targets: Sequence[str]) -> int:
    """Peringkat dokumen relevan pertama (mulai 1); 0 bila tidak ditemukan."""
    for rank, doc in enumerate(doc_ranking(hits), start=1):
        if doc in targets:
            return rank
    return 0


def answer_rank(hits: Sequence[Hit], targets: Sequence[str], answer_terms: Sequence[str]) -> int:
    """Peringkat potongan pertama dari dokumen target yang memuat bukti jawaban."""
    for rank, hit in enumerate(hits, start=1):
        text = hit.text.lower()
        if hit.metadata["doc_id"] in targets and any(t.lower() in text for t in answer_terms):
            return rank
    return 0


def evaluate_query(query: Dict[str, Any], hits: Sequence[Hit]) -> Dict[str, Any]:
    targets = query.get("target_docs", [])
    rank = first_relevant_rank(hits, targets)
    answer = answer_rank(hits, targets, query.get("answer_terms", []))
    ranking = doc_ranking(hits)
    return {
        "rank": rank,
        "rr": 1.0 / rank if rank else 0.0,
        "answer_rank": answer,
        "top_doc": ranking[0] if ranking else None,
        "targets_in_top5": len(set(ranking[:5]) & set(targets)),
    }


def summarize(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Agregat Hit@k, MRR, dan Answer@3 untuk baris hasil kueri dalam domain."""
    n = len(rows)
    if n == 0:
        return {"n": 0}
    def rate(pred) -> float:
        return sum(1 for r in rows if pred(r)) / n
    hit1 = sum(1 for r in rows if r["rank"] == 1)
    ci = wilson_interval(hit1, n)
    return {
        "n": n,
        "hit_at_1": hit1 / n,
        "hit_at_1_ci95": list(ci),
        "hit_at_3": rate(lambda r: 0 < r["rank"] <= 3),
        "hit_at_5": rate(lambda r: 0 < r["rank"] <= 5),
        "mrr": sum(r["rr"] for r in rows) / n,
        "answer_at_3": rate(lambda r: 0 < r["answer_rank"] <= 3),
    }


def roc_auc(positive: Sequence[float], negative: Sequence[float]) -> float:
    """AUC berbasis peringkat: peluang skor positif lebih tinggi dari skor negatif."""
    if not positive or not negative:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in positive for n in negative)
    return wins / (len(positive) * len(negative))


def rejection_metrics(in_domain: Sequence[float], ood: Sequence[float], threshold: float) -> Dict[str, Any]:
    """Kelas positif = ditolak. Kueri dengan skor di bawah ambang ditolak."""
    tp = sum(1 for s in ood if s < threshold)
    fp = sum(1 for s in in_domain if s < threshold)
    fn = len(ood) - tp
    tn = len(in_domain) - fp
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "threshold": threshold, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall, "f1": f1,
        "false_reject_rate": fp / len(in_domain) if in_domain else 0.0,
        "precision_ci95": list(wilson_interval(tp, tp + fp)),
        "recall_ci95": list(wilson_interval(tp, tp + fn)),
    }


def calibrate_threshold(in_domain: Sequence[float], ood: Sequence[float],
                        max_false_reject: float = 0.10) -> Dict[str, Any]:
    """Memilih ambang ber-F1 tertinggi yang penolakan kelirunya tidak melewati batas."""
    scores = sorted(set(in_domain) | set(ood))
    candidates = [(a + b) / 2 for a, b in zip(scores, scores[1:])] or [0.5]
    evaluated = [rejection_metrics(in_domain, ood, t) for t in candidates]
    allowed = [m for m in evaluated if m["false_reject_rate"] <= max_false_reject]
    constrained = bool(allowed)
    pool = allowed or evaluated
    best = max(pool, key=lambda m: (m["f1"], m["precision"], -m["threshold"]))
    return {**best, "constraint_met": constrained}


def lexical_overlap(query: str, document: str) -> float:
    """Porsi kata kueri yang muncul persis di dokumen: tanda sifat literal kueri."""
    terms = set(tokenize(query))
    if not terms:
        return 0.0
    return len(terms & set(tokenize(document))) / len(terms)
