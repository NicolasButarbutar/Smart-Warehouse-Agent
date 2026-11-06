"""Eksperimen dan benchmark temu balik.

Alur: pilih model -> pilih chunking -> kalibrasi ambang (ketiganya pada kueri dev)
-> bangun ChromaDB -> evaluasi akhir pada kueri test yang tidak dipakai untuk memilih.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
from dataclasses import asdict
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np

from . import config as cfg
from .chunking import embedding_text
from .evaluate import (calibrate_threshold, doc_ranking, evaluate_query, lexical_overlap,
                       rejection_metrics, roc_auc, summarize)
from .ingest import METADATA_FIELDS, build_chunks, build_records, chunk_statistics, save_artifacts
from .lexical import BM25Index
from .preprocess import CleanDocument, load_corpus
from .retriever import Retriever
from .vector_store import ChromaKnowledgeBase, NumpyIndex

IN_DOMAIN = ("literal", "sinonim", "ambigu")
EVAL_K = 20  # potongan yang diambil, cukup untuk peringkat dokumen sampai 5


def load_queries(path: Path = cfg.QUERIES_PATH) -> List[Dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _select(queries: Sequence[Dict[str, Any]], split: str, types: Sequence[str]) -> List[Dict[str, Any]]:
    return [q for q in queries if q["split"] == split and q["tipe"] in types]


def _prepare(documents: Sequence[CleanDocument], embedder: Any, chunk_words: int, overlap_words: int) -> Dict[str, Any]:
    pairs = build_chunks(documents, chunk_words, overlap_words)
    records = build_records(pairs, embedder)
    started = time.perf_counter()
    records["embeddings"] = embedder.encode(records["texts"])
    records["encode_seconds"] = time.perf_counter() - started
    records["stats"] = chunk_statistics(pairs, records["tokens"], embedder.max_seq_length)
    return records


def _embed_queries(queries: Sequence[Dict[str, Any]], embedder: Any) -> Dict[str, np.ndarray]:
    vectors = embedder.encode([q["kueri"] for q in queries])
    return {q["id"]: v for q, v in zip(queries, vectors)}


def _evaluate_index(index: Any, queries: Sequence[Dict[str, Any]], vectors: Dict[str, np.ndarray]) -> Dict[str, Any]:
    """Metrik pencarian vektor pada kueri dev, untuk seleksi model dan chunking."""
    in_rows, in_scores, ood_scores = [], [], []
    for query in queries:
        hits = index.query(vectors[query["id"]], k=EVAL_K)
        top = hits[0].similarity if hits else 0.0
        if query["tipe"] == "ood":
            ood_scores.append(top)
        else:
            in_rows.append(evaluate_query(query, hits))
            in_scores.append(top)
    summary = summarize(in_rows)
    return {
        **summary,
        "auc_ood": roc_auc(in_scores, ood_scores),
        "cos_rata2_domain": float(np.mean(in_scores)),
        "cos_rata2_ood": float(np.mean(ood_scores)),
    }


def compare_models(documents, queries, factory: Callable[[str], Any], models: Sequence[str],
                   chunk_words: int, overlap_words: int) -> Dict[str, Any]:
    dev = _select(queries, "dev", (*IN_DOMAIN, "ood"))
    rows = []
    for name in models:
        print(f"  model: {name}", flush=True)
        embedder = factory(name)
        records = _prepare(documents, embedder, chunk_words, overlap_words)
        index = NumpyIndex(records["ids"], records["embeddings"], records["documents"], records["metadatas"])
        metrics = _evaluate_index(index, dev, _embed_queries(dev, embedder))
        rows.append({
            "model": name,
            "dimensi": int(records["embeddings"].shape[1]),
            "max_seq_length": embedder.max_seq_length,
            "detik_encode_korpus": records["encode_seconds"],
            "pct_terpotong_model": records["stats"]["pct_terpotong_model"],
            "skor_seleksi": (metrics["mrr"] + metrics["answer_at_3"] + metrics["auc_ood"]) / 3,
            **metrics,
        })
    best = max(rows, key=lambda r: round(r["skor_seleksi"], 4))
    return {"baris": rows, "terpilih": best["model"],
            "aturan": "rata-rata MRR, Answer@3, dan AUC out-of-domain pada kueri dev"}


def sweep_chunking(documents, queries, embedder: Any) -> Dict[str, Any]:
    dev = _select(queries, "dev", (*IN_DOMAIN, "ood"))
    vectors = _embed_queries(dev, embedder)
    rows = []
    for size in cfg.CHUNK_SIZE_GRID:
        for ratio in cfg.OVERLAP_RATIO_GRID:
            overlap = int(round(size * ratio))
            records = _prepare(documents, embedder, size, overlap)
            index = NumpyIndex(records["ids"], records["embeddings"], records["documents"], records["metadatas"])
            rows.append({"chunk_words": size, "overlap_ratio": ratio, "overlap_words": overlap,
                         **records["stats"], **_evaluate_index(index, dev, vectors)})
            print(f"  chunk {size}/{overlap}: MRR={rows[-1]['mrr']:.3f} "
                  f"Answer@3={rows[-1]['answer_at_3']:.3f} terpotong={rows[-1]['pct_terpotong_model']:.1f}%", flush=True)
    allowed = [r for r in rows if r["pct_terpotong_model"] <= cfg.MAX_TRUNCATED_PCT] or rows
    best = max(allowed, key=lambda r: (round(r["mrr"], 4), round(r["answer_at_3"], 4),
                                       round(r["auc_ood"], 4), -r["jumlah_chunk"]))
    return {"baris": rows, "terpilih": {"chunk_words": best["chunk_words"], "overlap_words": best["overlap_words"]},
            "aturan": f"terpotong model <= {cfg.MAX_TRUNCATED_PCT}%, lalu MRR, Answer@3, AUC, jumlah chunk tersedikit"}


def calibrate(documents, queries, embedder: Any, conf: cfg.KBConfig) -> Dict[str, Any]:
    records = _prepare(documents, embedder, conf.chunk_words, conf.overlap_words)
    index = NumpyIndex(records["ids"], records["embeddings"], records["documents"], records["metadatas"])
    dev = _select(queries, "dev", (*IN_DOMAIN, "ood"))
    vectors = _embed_queries(dev, embedder)
    top = {q["id"]: index.query(vectors[q["id"]], k=1)[0].similarity for q in dev}
    in_scores = [top[q["id"]] for q in dev if q["tipe"] != "ood"]
    ood_scores = [top[q["id"]] for q in dev if q["tipe"] == "ood"]
    chosen = calibrate_threshold(in_scores, ood_scores, cfg.MAX_FALSE_REJECT_RATE)
    return {"terpilih": chosen, "skor_dev_domain": in_scores, "skor_dev_ood": ood_scores}


def build_index(documents, embedder: Any, conf: cfg.KBConfig, persist_dir: Path = cfg.VECTORSTORE_DIR,
                clean_dir: Path = cfg.CLEAN_DIR, chunks_path: Path = cfg.CHUNKS_PATH,
                report_path: Path = cfg.INGEST_REPORT_PATH) -> Dict[str, Any]:
    """Membangun koleksi ChromaDB persisten dan menyimpan artefak ingestion."""
    records = _prepare(documents, embedder, conf.chunk_words, conf.overlap_words)
    save_artifacts(documents, records, clean_dir, chunks_path)
    store = ChromaKnowledgeBase(persist_dir, cfg.COLLECTION_NAME)
    started = time.perf_counter()
    count = store.rebuild(records["ids"], records["embeddings"], records["documents"], records["metadatas"], {
        "model_embedding": embedder.name, "chunk_kata": conf.chunk_words, "overlap_kata": conf.overlap_words,
    })
    report = {
        "jumlah_dokumen": len(documents),
        "dokumen": [{"doc_id": d.doc_id, "judul": d.meta["judul"], "format": Path(d.meta["file_sumber"]).suffix,
                     **d.stats} for d in documents],
        "statistik_chunk": records["stats"],
        "jumlah_vektor_chromadb": count,
        "dimensi": int(records["embeddings"].shape[1]),
        "detik_encode": records["encode_seconds"],
        "detik_tulis_chromadb": time.perf_counter() - started,
        "field_metadata": list(METADATA_FIELDS),
        "pct_metadata_lengkap": _metadata_completeness(records["metadatas"]),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"report": report, "store": store, "records": records}


def _metadata_completeness(metadatas: Sequence[Dict[str, Any]]) -> float:
    total = len(metadatas) * len(METADATA_FIELDS)
    filled = sum(1 for m in metadatas for f in METADATA_FIELDS if m.get(f) not in (None, ""))
    return 100.0 * filled / total if total else 0.0


def _doc_text(documents: Sequence[CleanDocument]) -> Dict[str, str]:
    return {d.doc_id: d.to_text() for d in documents}


def evaluate_test(store: ChromaKnowledgeBase, embedder: Any, queries, documents, threshold: float) -> Dict[str, Any]:
    """Evaluasi akhir pada kueri test melalui ChromaDB yang sudah dibangun."""
    data = store.collection.get(include=["documents", "metadatas"])
    bm25 = BM25Index(data["ids"], data["documents"], data["metadatas"])
    retriever = Retriever(store, embedder, bm25, threshold)
    test = _select(queries, "test", (*IN_DOMAIN, "ood"))
    vectors = _embed_queries(test, embedder)
    texts = _doc_text(documents)
    per_query, by_mode = [], {"vector": {}, "bm25": {}, "hybrid": {}}
    latencies = []
    for query in test:
        row = {k: query[k] for k in ("id", "tipe", "kueri", "target_docs")}
        if "ood_jenis" in query:
            row["ood_jenis"] = query["ood_jenis"]
        for mode in by_mode:
            started = time.perf_counter()
            response = retriever.search_with_embedding(query["kueri"], vectors[query["id"]], k=EVAL_K, mode=mode)
            latencies.append((mode, 1000 * (time.perf_counter() - started)))
            evaluation = evaluate_query(query, response.hits)
            by_mode[mode][query["id"]] = evaluation
            row[mode] = {**evaluation, "top_doc": evaluation["top_doc"],
                         "cuplikan": response.hits[0].text[:160] if response.hits else ""}
            if mode == "vector":
                sims = [h.similarity for h in response.hits]
                row["cos_top1"] = sims[0] if sims else 0.0
                row["cos_top2_dokumen_lain"] = _second_doc_similarity(response.hits)
                row["ditolak"] = response.rejected
                row["dokumen_top5"] = doc_ranking(response.hits)[:5]
        if query["target_docs"]:
            row["kemiripan_leksikal"] = max(lexical_overlap(query["kueri"], texts[d]) for d in query["target_docs"])
        per_query.append(row)

    summary: Dict[str, Dict[str, Any]] = {}
    for mode, evaluations in by_mode.items():
        summary[mode] = {}
        for kind in (*IN_DOMAIN, "semua_domain"):
            kinds = IN_DOMAIN if kind == "semua_domain" else (kind,)
            rows = [evaluations[q["id"]] for q in test if q["tipe"] in kinds]
            summary[mode][kind] = summarize(rows)

    domain_rows = [r for r in per_query if r["tipe"] != "ood"]
    ood_rows = [r for r in per_query if r["tipe"] == "ood"]
    in_scores = [r["cos_top1"] for r in domain_rows]
    ood_scores = [r["cos_top1"] for r in ood_rows]
    rejection = rejection_metrics(in_scores, ood_scores, threshold)
    rejection["auc"] = roc_auc(in_scores, ood_scores)
    rejection["per_jenis_ood"] = {
        kind: {"n": len(rows), "ditolak": sum(r["ditolak"] for r in rows)}
        for kind in ("jauh", "dekat")
        for rows in [[r for r in ood_rows if r.get("ood_jenis") == kind]]
    }
    accepted_correct = sum(1 for r in domain_rows if not r["ditolak"] and r["vector"]["rank"] == 1)
    grid = [round(x, 2) for x in np.arange(0.10, 0.91, 0.05)]
    ambiguous = [r for r in domain_rows if r["tipe"] == "ambigu"]
    specific = [r for r in domain_rows if r["tipe"] != "ambigu"]
    return {
        "ringkasan_per_mode": summary,
        "penolakan_ood": rejection,
        "kurva_ambang": [rejection_metrics(in_scores, ood_scores, t) for t in grid],
        "sukses_end_to_end": accepted_correct / len(domain_rows) if domain_rows else 0.0,
        "statistik_cosine": {
            kind: _describe([r["cos_top1"] for r in per_query if r["tipe"] == kind])
            for kind in (*IN_DOMAIN, "ood")
        },
        "selisih_top_dokumen": {
            "ambigu": float(np.mean([r["cos_top1"] - r["cos_top2_dokumen_lain"] for r in ambiguous])) if ambiguous else None,
            "spesifik": float(np.mean([r["cos_top1"] - r["cos_top2_dokumen_lain"] for r in specific])) if specific else None,
        },
        "cakupan_target_ambigu": float(np.mean([r["vector"]["targets_in_top5"] for r in ambiguous])) if ambiguous else None,
        "kemiripan_leksikal_rata2": {
            kind: float(np.mean([r["kemiripan_leksikal"] for r in domain_rows if r["tipe"] == kind]))
            for kind in IN_DOMAIN if any(r["tipe"] == kind for r in domain_rows)
        },
        "latensi_ms": {mode: float(np.median([ms for m, ms in latencies if m == mode])) for mode in by_mode},
        "per_kueri": per_query,
    }


def _second_doc_similarity(hits: Sequence[Any]) -> float:
    if not hits:
        return 0.0
    first = hits[0].metadata["doc_id"]
    for hit in hits[1:]:
        if hit.metadata["doc_id"] != first:
            return float(hit.similarity)
    return 0.0


def _describe(values: Sequence[float]) -> Dict[str, Any]:
    if not values:
        return {"n": 0}
    return {"n": len(values), "rata2": float(np.mean(values)), "min": float(np.min(values)),
            "median": float(np.median(values)), "maks": float(np.max(values))}


def verify_filters(store: ChromaKnowledgeBase, embedder: Any, threshold: float) -> List[Dict[str, Any]]:
    """Membuktikan filter metadata bekerja: seluruh hasil harus memenuhi syarat."""
    data = store.collection.get(include=["documents", "metadatas"])
    retriever = Retriever(store, embedder, BM25Index(data["ids"], data["documents"], data["metadatas"]), threshold)
    cases = [
        ("Bagaimana aturan suhu?", {"kategori": "Rantai Dingin"}, lambda m: m["kategori"] == "Rantai Dingin"),
        ("Berapa batas jam kerja?", {"jenis": "Regulasi"}, lambda m: m["jenis"] == "Regulasi"),
        ("Aturan keselamatan apa saja?", {"$and": [{"level_akses": "publik"}, {"tahun_berlaku": {"$gte": 2026}}]},
         lambda m: m["level_akses"] == "publik" and m["tahun_berlaku"] >= 2026),
        ("Di mana barang ditaruh?", {"format_sumber": {"$in": ["md", "pdf"]}}, lambda m: m["format_sumber"] in ("md", "pdf")),
    ]
    results = []
    for query, where, check in cases:
        for mode in ("vector", "hybrid"):
            response = retriever.search(query, k=5, mode=mode, where=where)
            results.append({
                "kueri": query, "filter": where, "mode": mode, "jumlah_hasil": len(response.hits),
                "semua_sesuai_filter": all(check(h.metadata) for h in response.hits),
                "dokumen": doc_ranking(response.hits),
            })
    return results


def compare_hnsw_with_exact(store: ChromaKnowledgeBase, records: Dict[str, Any], vectors: Dict[str, np.ndarray], k: int = 5) -> Dict[str, Any]:
    """Recall HNSW terhadap pencarian eksak, dan selisih skor cosine."""
    exact = NumpyIndex(records["ids"], records["embeddings"], records["documents"], records["metadatas"])
    overlaps, deltas = [], []
    for vector in vectors.values():
        a, b = exact.query(vector, k=k), store.query(vector, k=k)
        overlaps.append(len({h.id for h in a} & {h.id for h in b}) / k)
        if a and b:
            deltas.append(abs(a[0].similarity - b[0].similarity))
    return {"recall_at_5": float(np.mean(overlaps)), "selisih_cos_maks": float(np.max(deltas)) if deltas else None}


def check_persistence(vectors: Dict[str, np.ndarray], persist_dir: Path, expected: Dict[str, List[str]], entry: Path) -> Dict[str, Any]:
    """Membuka basis data dari proses Python terpisah untuk membuktikan persistensi."""
    probe_input = persist_dir.parent / "processed" / "_probe_vectors.json"
    probe_input.write_text(json.dumps({k: v.tolist() for k, v in vectors.items()}), encoding="utf-8")
    try:
        done = subprocess.run([sys.executable, str(entry), "probe", str(probe_input)],
                              capture_output=True, text=True, encoding="utf-8", check=True)
    finally:
        probe_input.unlink(missing_ok=True)
    payload = json.loads(done.stdout.strip().splitlines()[-1])
    same = sum(1 for k, ids in expected.items() if payload["hasil"].get(k) == ids)
    return {"jumlah_vektor_proses_baru": payload["jumlah"], "kueri_diuji": len(expected),
            "kueri_hasil_identik": same, "pid_proses_baru": payload["pid"]}


def environment_info() -> Dict[str, Any]:
    versions = {}
    for package in ("chromadb", "sentence-transformers", "torch", "transformers", "numpy", "pypdf"):
        try:
            versions[package] = importlib_metadata.version(package)
        except importlib_metadata.PackageNotFoundError:
            versions[package] = None
    return {"python": platform.python_version(), "os": platform.platform(), "paket": versions,
            "waktu": time.strftime("%Y-%m-%d %H:%M:%S %z")}


def run_benchmark(factory: Callable[[str], Any], entry: Path, skip_model_compare: bool = False,
                  skip_sweep: bool = False, results_path: Path = cfg.RESULTS_PATH) -> Dict[str, Any]:
    documents = load_corpus(cfg.CORPUS_DIR)
    queries = load_queries()
    conf = cfg.KBConfig()
    results: Dict[str, Any] = {"lingkungan": environment_info()}

    if skip_model_compare:
        results["perbandingan_model"] = None
    else:
        print("[1/5] Membandingkan model embedding pada kueri dev", flush=True)
        results["perbandingan_model"] = compare_models(documents, queries, factory, cfg.CANDIDATE_MODELS,
                                                       conf.chunk_words, conf.overlap_words)
        conf.model_name = results["perbandingan_model"]["terpilih"]
    embedder = factory(conf.model_name)

    if skip_sweep:
        results["eksperimen_chunking"] = None
    else:
        print("[2/5] Eksperimen ukuran chunk dan overlap", flush=True)
        results["eksperimen_chunking"] = sweep_chunking(documents, queries, embedder)
        conf.chunk_words = results["eksperimen_chunking"]["terpilih"]["chunk_words"]
        conf.overlap_words = results["eksperimen_chunking"]["terpilih"]["overlap_words"]

    print("[3/5] Kalibrasi ambang penolakan pada kueri dev", flush=True)
    results["kalibrasi_ambang"] = calibrate(documents, queries, embedder, conf)
    conf.threshold = float(results["kalibrasi_ambang"]["terpilih"]["threshold"])
    conf.save()
    results["konfigurasi_terpilih"] = asdict(conf)

    print("[4/5] Membangun indeks ChromaDB persisten", flush=True)
    built = build_index(documents, embedder, conf)
    store, records = built["store"], built["records"]
    results["ingestion"] = built["report"]

    print("[5/5] Evaluasi akhir pada kueri test", flush=True)
    results["evaluasi_test"] = evaluate_test(store, embedder, queries, documents, conf.threshold)
    results["uji_filter_metadata"] = verify_filters(store, embedder, conf.threshold)
    test = _select(queries, "test", (*IN_DOMAIN, "ood"))
    vectors = _embed_queries(test, embedder)
    results["hnsw_vs_eksak"] = compare_hnsw_with_exact(store, records, vectors)
    expected = {k: [h.id for h in store.query(v, k=5)] for k, v in vectors.items()}
    results["uji_persistensi"] = check_persistence(vectors, cfg.VECTORSTORE_DIR, expected, entry)
    results["pid_proses_utama"] = __import__("os").getpid()

    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    return results
