"""Word-aware recursive chunking dengan overlap selaras kalimat.

Urutan pemisah: bab -> paragraf -> kalimat -> klausa -> kata. Unit dipecah lebih
halus hanya bila melebihi batas, sehingga kalimat tetap utuh selama muat.
Overlap diambil dari kalimat utuh di akhir potongan sebelumnya dan tidak pernah
melintasi batas bab.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Sequence

_ABBREV = re.compile(r"(?:\b(?:No|Nomor|dll|dsb|dst|mis|Bpk|Ibu|Dr|Rp|Pasal|hlm)\.)$")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])")
_CLAUSE_END = re.compile(r"(?<=[,;:])\s+")


@dataclass
class Chunk:
    doc_id: str
    chunk_index: int
    section: str
    section_index: int
    text: str
    n_words: int
    overlap_words: int


def word_count(text: str) -> int:
    return len(text.split())


def split_sentences(text: str) -> List[str]:
    """Memecah kalimat dan menyambung kembali pecahan akibat singkatan."""
    merged: List[str] = []
    for part in _SENTENCE_END.split(text.strip()):
        part = part.strip()
        if not part:
            continue
        if merged and _ABBREV.search(merged[-1]):
            merged[-1] = f"{merged[-1]} {part}"
        else:
            merged.append(part)
    return merged


def _split_words(text: str, limit: int) -> List[str]:
    words = text.split()
    return [" ".join(words[i : i + limit]) for i in range(0, len(words), limit)]


def _atoms(text: str, limit: int) -> List[str]:
    """Memecah rekursif sampai setiap unit paling banyak `limit` kata."""
    if word_count(text) <= limit:
        return [text.strip()] if text.strip() else []
    levels = (
        lambda t: t.split("\n\n"),
        split_sentences,
        lambda t: _CLAUSE_END.split(t),
    )
    for splitter in levels:
        parts = [p.strip() for p in splitter(text) if p.strip()]
        if len(parts) > 1:
            atoms: List[str] = []
            for part in parts:
                atoms.extend(_atoms(part, limit))
            return atoms
    return _split_words(text, limit)


def _sentence_atoms(text: str, limit: int) -> List[str]:
    """Unit dasar penggabungan: selalu kalimat, agar overlap selaras kalimat."""
    atoms: List[str] = []
    for paragraph in text.split("\n\n"):
        for sentence in split_sentences(paragraph):
            atoms.extend(_atoms(sentence, limit))
    return atoms


def chunk_section(text: str, chunk_words: int, overlap_words: int) -> List[List[str]]:
    """Menggabungkan unit menjadi potongan; hasilnya daftar unit per potongan."""
    if chunk_words <= 0:
        raise ValueError("chunk_words harus positif")
    if not 0 <= overlap_words < chunk_words:
        raise ValueError("overlap_words harus di antara 0 dan chunk_words")
    atoms = _sentence_atoms(text, chunk_words)
    chunks: List[List[str]] = []
    current: List[str] = []
    current_words = 0
    new_units = 0
    for atom in atoms:
        size = word_count(atom)
        if current and current_words + size > chunk_words:
            chunks.append(current)
            tail: List[str] = []
            tail_words = 0
            for unit in reversed(current):
                unit_size = word_count(unit)
                if tail_words + unit_size > overlap_words:
                    break
                tail.insert(0, unit)
                tail_words += unit_size
            if tail_words + size > chunk_words:  # overlap tidak boleh melewati batas
                tail, tail_words = [], 0
            current, current_words = tail, tail_words
            new_units = 0
        current.append(atom)
        current_words += size
        new_units += 1
    if current and new_units:
        chunks.append(current)
    return chunks


def chunk_document(doc_id: str, sections: Sequence, chunk_words: int, overlap_words: int) -> List[Chunk]:
    """Memotong satu dokumen bersih. `sections` berisi objek Section."""
    result: List[Chunk] = []
    for section in sections:
        previous: List[str] = []
        for units in chunk_section(section.text, chunk_words, overlap_words):
            overlap = 0
            for k in range(min(len(previous), len(units)), 0, -1):
                if previous[-k:] == units[:k]:
                    overlap = sum(word_count(u) for u in units[:k])
                    break
            body = " ".join(units)
            result.append(
                Chunk(
                    doc_id=doc_id,
                    chunk_index=len(result),
                    section=section.heading,
                    section_index=section.index,
                    text=body,
                    n_words=word_count(body),
                    overlap_words=overlap,
                )
            )
            previous = units
    return result


def embedding_text(title: str, section: str, body: str) -> str:
    """Teks yang di-encode: konteks judul dan bab, lalu isi potongan."""
    return f"{title} - {section}: {body}"


def boundary_quality(chunks: Sequence[Chunk]) -> float:
    """Persentase potongan yang berakhir di akhir kalimat."""
    if not chunks:
        return 0.0
    complete = sum(1 for c in chunks if c.text.rstrip()[-1:] in {".", "!", "?", '"'})
    return 100.0 * complete / len(chunks)
