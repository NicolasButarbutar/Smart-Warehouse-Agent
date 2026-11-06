"""Pemuatan dan pembersihan dokumen korpus (.md, .txt, .pdf)."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

_BOILERPLATE = [
    re.compile(r"^halaman\s+\d+(\s+dari\s+\d+)?$", re.I),
    re.compile(r"^.{0,60}dokumen terkendali\b.*$", re.I),
    re.compile(r"^dilarang menggandakan\b.*$", re.I),
    re.compile(r"^[-–—\s]*\d+[-–—\s]*$"),
    re.compile(r"^[=\-_*]{3,}$"),
]
_CHAR_MAP = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "­": "", "​": "", "﻿": "",
    " ": " ",
}
_HEADING = re.compile(r"^(?:#{1,6}\s*)?(\d+(?:\.\d+)*)\.?\s+([A-Z][^.!?]{2,80})$")
_TITLE_MD = re.compile(r"^#\s+")


@dataclass
class Section:
    heading: str
    index: int
    text: str


@dataclass
class CleanDocument:
    meta: Dict[str, str]
    sections: List[Section]
    stats: Dict[str, int] = field(default_factory=dict)

    @property
    def doc_id(self) -> str:
        return self.meta["doc_id"]

    def to_text(self) -> str:
        parts = [self.meta["judul"]]
        parts += [f"{s.heading}\n{s.text}" for s in self.sections]
        return "\n\n".join(parts) + "\n"


def extract_pages(path: Path) -> List[str]:
    """Mengembalikan teks per halaman; berkas teks dianggap satu halaman."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        return [page.extract_text() or "" for page in PdfReader(str(path)).pages]
    if suffix in {".md", ".txt"}:
        return [path.read_text(encoding="utf-8-sig", errors="replace")]
    raise ValueError(f"Format tidak didukung: {path.name}")


def normalize_characters(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(str.maketrans(_CHAR_MAP))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "".join(c for c in text if c == "\n" or c == "\t" or unicodedata.category(c)[0] != "C")


def find_repeated_lines(pages: Sequence[str], min_ratio: float = 0.6) -> set:
    """Baris yang muncul pada banyak halaman dianggap header/footer."""
    if len(pages) < 2:
        return set()
    counts: Counter = Counter()
    for page in pages:
        counts.update({ln.strip() for ln in page.splitlines() if ln.strip()})
    limit = max(2, int(len(pages) * min_ratio))
    return {ln for ln, n in counts.items() if n >= limit}


def clean_pages(pages: Sequence[str]) -> Tuple[str, Dict[str, int]]:
    """Membersihkan halaman menjadi satu teks; mengembalikan teks dan statistik."""
    normalized = [normalize_characters(p) for p in pages]
    repeated = find_repeated_lines(normalized)
    kept: List[str] = []
    removed = 0
    for page in normalized:
        for raw in page.split("\n"):
            line = re.sub(r"[ \t]+", " ", raw).strip()
            if line and (line in repeated or any(p.match(line) for p in _BOILERPLATE)):
                removed += 1
                continue
            kept.append(line)
    text = "\n".join(kept)
    text = re.sub(r"(?<=[a-z])-\n(?=[a-z])", "", text)  # pemenggalan akhir baris
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    raw_words = sum(len(p.split()) for p in pages)
    return text, {
        "kata_mentah": raw_words,
        "kata_bersih": len(text.split()),
        "baris_boilerplate_dibuang": removed,
    }


def parse_sections(text: str, title: str = "") -> List[Section]:
    """Memecah teks bersih per bab bernomor; baris dalam bab disambung kembali."""
    sections: List[Section] = []
    heading = "Pendahuluan"
    buffer: List[str] = []
    title_key = title.strip().lower()

    def flush() -> None:
        paragraphs = [" ".join(p.split()) for p in "\n".join(buffer).split("\n\n")]
        body = "\n\n".join(p for p in paragraphs if p)
        # Sisa judul yang terbungkus dua baris pada PDF bukan isi dokumen.
        if not sections and heading == "Pendahuluan" and set(body.lower().split()) <= set(title_key.split()):
            body = ""
        if body:
            sections.append(Section(heading=heading, index=len(sections), text=body))

    for line in text.split("\n"):
        stripped = line.strip()
        if _TITLE_MD.match(stripped) or (title_key and stripped.lower() == title_key):
            continue
        match = _HEADING.match(stripped)
        if match:
            flush()
            heading = f"{match.group(1)}. {match.group(2).strip()}"
            buffer = []
        else:
            buffer.append(stripped)
    flush()
    return sections


def load_manifest(corpus_dir: Path) -> List[Dict[str, str]]:
    return json.loads((corpus_dir / "manifest.json").read_text(encoding="utf-8"))


def load_corpus(corpus_dir: Path) -> List[CleanDocument]:
    """Memuat seluruh dokumen pada manifest menjadi dokumen bersih."""
    documents = []
    for meta in load_manifest(corpus_dir):
        path = corpus_dir / meta["file_sumber"]
        pages = extract_pages(path)
        text, stats = clean_pages(pages)
        sections = parse_sections(text, meta["judul"])
        if not sections:
            raise ValueError(f"Dokumen tanpa isi setelah dibersihkan: {path.name}")
        stats["jumlah_bab"] = len(sections)
        stats["jumlah_halaman"] = len(pages)
        documents.append(CleanDocument(meta=dict(meta), sections=sections, stats=stats))
    return documents
