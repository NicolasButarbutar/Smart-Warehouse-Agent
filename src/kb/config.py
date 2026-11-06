"""Konfigurasi terpusat pipeline basis pengetahuan (Milestone 3)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "data" / "raw" / "corpus"
CLEAN_DIR = ROOT / "data" / "processed" / "corpus_clean"
CHUNKS_PATH = ROOT / "data" / "processed" / "chunks.jsonl"
INGEST_REPORT_PATH = ROOT / "data" / "processed" / "ingest_report.json"
KB_CONFIG_PATH = ROOT / "data" / "processed" / "kb_config.json"
VECTORSTORE_DIR = ROOT / "data" / "vectorstore"
QUERIES_PATH = ROOT / "data" / "benchmark" / "queries.json"
RESULTS_PATH = ROOT / "results" / "benchmark_results.json"

COLLECTION_NAME = "enterprise_kb"

# Model yang dibandingkan. Pemenang ditentukan dari kueri dev, bukan diasumsikan.
CANDIDATE_MODELS = [
    "sentence-transformers/all-MiniLM-L6-v2",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
]

# Grid eksperimen chunking (ukuran dalam kata, overlap sebagai rasio ukuran).
CHUNK_SIZE_GRID = [40, 55, 70, 90, 110, 130]
OVERLAP_RATIO_GRID = [0.0, 0.1, 0.2, 0.3]
# Konfigurasi dengan potongan terpotong model di atas batas ini tidak dipilih.
MAX_TRUNCATED_PCT = 5.0
# Batas penolakan keliru kueri dalam domain saat kalibrasi ambang.
MAX_FALSE_REJECT_RATE = 0.10


@dataclass
class KBConfig:
    """Konfigurasi aktif indeks. Disimpan agar pencarian memakai model yang sama."""

    model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    chunk_words: int = 70
    overlap_words: int = 14
    threshold: float = 0.45

    def save(self, path: Path = KB_CONFIG_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path = KB_CONFIG_PATH) -> "KBConfig":
        if path.exists():
            return cls(**json.loads(path.read_text(encoding="utf-8")))
        return cls()
