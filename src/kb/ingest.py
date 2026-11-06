"""Pipeline ingestion: korpus -> bersih -> potongan -> metadata -> embedding."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .chunking import Chunk, boundary_quality, chunk_document, embedding_text
from .preprocess import CleanDocument

_RACK = re.compile(r"\bR(0[1-9]|1[0-6])\b")
METADATA_FIELDS = (
    "doc_id", "judul", "jenis", "kategori", "departemen", "pemilik", "versi",
    "tanggal_berlaku", "tahun_berlaku", "level_akses", "file_sumber", "format_sumber",
    "bab", "bab_index", "chunk_index", "total_chunk_dokumen", "n_kata", "n_kata_overlap",
    "n_token", "rak_terkait", "kata_kunci",
)


def build_chunks(documents: Sequence[CleanDocument], chunk_words: int, overlap_words: int
                 ) -> List[Tuple[CleanDocument, Chunk]]:
    pairs: List[Tuple[CleanDocument, Chunk]] = []
    for doc in documents:
        for chunk in chunk_document(doc.doc_id, doc.sections, chunk_words, overlap_words):
            pairs.append((doc, chunk))
    return pairs


def build_records(pairs: Sequence[Tuple[CleanDocument, Chunk]], embedder: Any) -> Dict[str, Any]:
    """Menyusun id, teks encode, dan metadata lengkap untuk setiap potongan."""
    texts = [embedding_text(d.meta["judul"], c.section, c.text) for d, c in pairs]
    tokens = embedder.count_tokens(texts)
    totals: Dict[str, int] = {}
    for _, c in pairs:
        totals[c.doc_id] = totals.get(c.doc_id, 0) + 1
    ids, metadatas = [], []
    for (doc, chunk), n_tokens in zip(pairs, tokens):
        meta = doc.meta
        racks = sorted({f"R{m}" for m in _RACK.findall(chunk.text)})
        ids.append(f"{chunk.doc_id}::{chunk.chunk_index:03d}")
        metadatas.append({
            "doc_id": chunk.doc_id,
            "judul": meta["judul"],
            "jenis": meta["jenis"],
            "kategori": meta["kategori"],
            "departemen": meta["departemen"],
            "pemilik": meta["pemilik"],
            "versi": meta["versi"],
            "tanggal_berlaku": meta["tanggal_berlaku"],
            "tahun_berlaku": int(meta["tanggal_berlaku"][:4]),
            "level_akses": meta["level_akses"],
            "file_sumber": meta["file_sumber"],
            "format_sumber": Path(meta["file_sumber"]).suffix.lstrip("."),
            "bab": chunk.section,
            "bab_index": chunk.section_index,
            "chunk_index": chunk.chunk_index,
            "total_chunk_dokumen": totals[chunk.doc_id],
            "n_kata": chunk.n_words,
            "n_kata_overlap": chunk.overlap_words,
            "n_token": n_tokens,
            "rak_terkait": ",".join(racks) if racks else "-",
            "kata_kunci": meta["kata_kunci"],
        })
    return {"ids": ids, "texts": texts, "documents": [c.text for _, c in pairs],
            "metadatas": metadatas, "tokens": tokens}


def chunk_statistics(pairs: Sequence[Tuple[CleanDocument, Chunk]], tokens: Sequence[int],
                     max_seq_length: int) -> Dict[str, Any]:
    chunks = [c for _, c in pairs]
    words = [c.n_words for c in chunks]
    truncated = sum(1 for t in tokens if t > max_seq_length)
    return {
        "jumlah_chunk": len(chunks),
        "kata_rata2": float(np.mean(words)),
        "kata_min": int(min(words)),
        "kata_maks": int(max(words)),
        "token_rata2": float(np.mean(tokens)),
        "token_p95": float(np.percentile(tokens, 95)),
        "token_maks": int(max(tokens)),
        "token_per_kata": float(sum(tokens) / max(1, sum(words))),
        "pct_terpotong_model": 100.0 * truncated / len(chunks),
        "pct_akhir_kalimat_utuh": boundary_quality(chunks),
    }


def save_artifacts(documents: Sequence[CleanDocument], records: Dict[str, Any],
                   clean_dir: Path, chunks_path: Path) -> None:
    clean_dir.mkdir(parents=True, exist_ok=True)
    for doc in documents:
        (clean_dir / f"{doc.doc_id}.txt").write_text(doc.to_text(), encoding="utf-8")
    chunks_path.parent.mkdir(parents=True, exist_ok=True)
    with chunks_path.open("w", encoding="utf-8") as handle:
        for i, text, meta in zip(records["ids"], records["documents"], records["metadatas"]):
            handle.write(json.dumps({"id": i, "text": text, "metadata": meta}, ensure_ascii=False) + "\n")
