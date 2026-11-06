"""CLI Milestone 3: basis pengetahuan korpus & pencarian semantik.

    uv run python src/kb_pipeline.py all                 # eksperimen, indeks, benchmark
    uv run python src/kb_pipeline.py ingest              # bangun ulang indeks saja
    uv run python src/kb_pipeline.py search "kueri" --kategori "Rantai Dingin"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kb import config as cfg  # noqa: E402


def _print_summary(results: dict) -> None:
    conf = results["konfigurasi_terpilih"]
    test = results["evaluasi_test"]
    print("\n=== RINGKASAN ===")
    print(f"Model   : {conf['model_name']}")
    print(f"Chunk   : {conf['chunk_words']} kata, overlap {conf['overlap_words']} kata")
    print(f"Ambang  : cosine >= {conf['threshold']:.3f}")
    print(f"Vektor  : {results['ingestion']['jumlah_vektor_chromadb']}")
    for mode, values in test["ringkasan_per_mode"].items():
        row = values["semua_domain"]
        print(f"{mode:7}: Hit@1={row['hit_at_1']:.3f} Hit@3={row['hit_at_3']:.3f} "
              f"MRR={row['mrr']:.3f} Answer@3={row['answer_at_3']:.3f}")
    rej = test["penolakan_ood"]
    print(f"Tolak OOD: presisi={rej['precision']:.3f} recall={rej['recall']:.3f} "
          f"salah tolak={rej['false_reject_rate']:.3f} AUC={rej['auc']:.3f}")
    print(f"\nHasil lengkap: {cfg.RESULTS_PATH}")
    print("Kirim berkas itu untuk melengkapi analisis laporan.")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    run_all = commands.add_parser("all", help="jalankan eksperimen, bangun indeks, dan benchmark")
    run_all.add_argument("--skip-model-compare", action="store_true", help="pakai model default")
    run_all.add_argument("--skip-sweep", action="store_true", help="pakai ukuran chunk default")
    commands.add_parser("ingest", help="bangun ulang indeks memakai konfigurasi tersimpan")
    search = commands.add_parser("search", help="cari di basis pengetahuan")
    search.add_argument("query")
    search.add_argument("-k", type=int, default=3)
    search.add_argument("--mode", choices=["vector", "bm25", "hybrid"], default="hybrid")
    search.add_argument("--kategori")
    search.add_argument("--jenis")
    probe = commands.add_parser("probe", help=argparse.SUPPRESS)
    probe.add_argument("vectors")
    args = parser.parse_args()

    from kb.vector_store import ChromaKnowledgeBase

    if args.command == "probe":
        import numpy as np

        store = ChromaKnowledgeBase(cfg.VECTORSTORE_DIR, cfg.COLLECTION_NAME)
        vectors = json.loads(Path(args.vectors).read_text(encoding="utf-8"))
        output = {k: [h.id for h in store.query(np.asarray(v), k=5)] for k, v in vectors.items()}
        print(json.dumps({"jumlah": store.count(), "hasil": output, "pid": os.getpid()}))
        return 0

    from kb.embeddings import SentenceTransformerEmbedder

    if args.command == "all":
        from kb.benchmark import run_benchmark

        results = run_benchmark(SentenceTransformerEmbedder, Path(__file__).resolve(),
                                args.skip_model_compare, args.skip_sweep)
        _print_summary(results)
        return 0

    conf = cfg.KBConfig.load()
    embedder = SentenceTransformerEmbedder(conf.model_name)

    if args.command == "ingest":
        from kb.benchmark import build_index
        from kb.preprocess import load_corpus

        built = build_index(load_corpus(cfg.CORPUS_DIR), embedder, conf)
        conf.save()
        report = built["report"]
        print(f"{report['jumlah_dokumen']} dokumen -> {report['jumlah_vektor_chromadb']} vektor di {cfg.VECTORSTORE_DIR}")
        return 0

    from kb.lexical import BM25Index
    from kb.retriever import Retriever

    store = ChromaKnowledgeBase(cfg.VECTORSTORE_DIR, cfg.COLLECTION_NAME)
    data = store.collection.get(include=["documents", "metadatas"])
    bm25 = BM25Index(data["ids"], data["documents"], data["metadatas"])
    where = {k: v for k, v in (("kategori", args.kategori), ("jenis", args.jenis)) if v}
    if len(where) > 1:
        where = {"$and": [{k: v} for k, v in where.items()]}
    response = Retriever(store, embedder, bm25, conf.threshold).search(
        args.query, k=args.k, mode=args.mode, where=where or None)
    print(f"Cosine tertinggi: {response.top_similarity:.3f} (ambang {conf.threshold:.3f})")
    if response.rejected:
        print("Kueri ditolak: tidak ada dokumen yang cukup relevan di basis pengetahuan.")
        return 0
    for rank, hit in enumerate(response.hits, start=1):
        score = "-" if hit.similarity is None else f"{hit.similarity:.3f}"
        print(f"\n[{rank}] cos={score} {hit.metadata['doc_id']} | {hit.metadata['judul']} | {hit.metadata['bab']}")
        print(hit.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
