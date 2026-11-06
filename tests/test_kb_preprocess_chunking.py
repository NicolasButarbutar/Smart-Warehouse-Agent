"""Pengujian pembersihan teks dan chunking Milestone 3."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kb.chunking import boundary_quality, chunk_document, chunk_section, split_sentences, word_count  # noqa: E402
from kb.preprocess import Section, clean_pages, find_repeated_lines, load_corpus, normalize_characters, parse_sections  # noqa: E402

CORPUS = ROOT / "data" / "raw" / "corpus"


def test_normalize_characters_fixes_quotes_and_invisible_marks():
    assert normalize_characters("“stok”­​\r\nbaru") == '"stok"\nbaru'


def test_repeated_lines_detected_as_header_footer():
    pages = ["Kop Surat\nisi satu", "Kop Surat\nisi dua", "Kop Surat\nisi tiga"]
    assert find_repeated_lines(pages) == {"Kop Surat"}


def test_clean_pages_removes_boilerplate_and_keeps_content():
    text, stats = clean_pages(["Halaman 1 dari 2\nIsi   penting.\nDokumen terkendali - GNL"])
    assert text == "Isi penting."
    assert stats["baris_boilerplate_dibuang"] == 2


def test_parse_sections_joins_wrapped_lines():
    sections = parse_sections("## 1. Tujuan\nbaris satu\nbaris dua.\n\n2. Lingkup Kerja\nisi kedua.", "Judul")
    assert [s.heading for s in sections] == ["1. Tujuan", "2. Lingkup Kerja"]
    assert sections[0].text == "baris satu baris dua."


def test_parse_sections_keeps_procedure_sentence_as_body():
    sections = parse_sections("1. Tujuan\n2. Petugas memindai barang.", "Judul")
    assert len(sections) == 1 and "memindai" in sections[0].text


def test_split_sentences_respects_abbreviation_and_decimal():
    parts = split_sentences("Lihat No. 8 pada lampiran. Akurasi 99,5 persen. Rp10.000.000 wajib dicek.")
    assert parts == ["Lihat No. 8 pada lampiran.", "Akurasi 99,5 persen.", "Rp10.000.000 wajib dicek."]


TEXT = " ".join(f"Kalimat nomor {i} berisi beberapa kata penjelas tentang gudang." for i in range(40))


@pytest.mark.parametrize("size,overlap", [(30, 0), (30, 9), (60, 12), (120, 36)])
def test_chunks_respect_limit_and_keep_sentences_whole(size, overlap):
    for units in chunk_section(TEXT, size, overlap):
        body = " ".join(units)
        assert word_count(body) <= size
        assert body.startswith("Kalimat") and body.endswith("gudang.")


def test_overlap_repeats_trailing_sentences():
    chunks = chunk_section(TEXT, 30, 10)
    assert len(chunks) > 1
    for previous, current in zip(chunks, chunks[1:]):
        assert current[0] in previous


def test_no_overlap_when_zero():
    chunks = chunk_section(TEXT, 30, 0)
    flat = [u for c in chunks for u in c]
    assert len(flat) == len(set(flat)) == 40


def test_all_sentences_are_preserved():
    chunks = chunk_section(TEXT, 30, 10)
    assert {u for c in chunks for u in c} == set(split_sentences(TEXT))


def test_oversized_sentence_is_split_recursively():
    long_sentence = "Klausa pertama sangat panjang, " + ", ".join(["kata isi tambahan lagi"] * 20) + "."
    chunks = chunk_section(long_sentence, 12, 0)
    assert all(word_count(" ".join(c)) <= 12 for c in chunks)
    assert word_count(" ".join(" ".join(c) for c in chunks)) == word_count(long_sentence)


def test_invalid_parameters_are_rejected():
    with pytest.raises(ValueError):
        chunk_section(TEXT, 0, 0)
    with pytest.raises(ValueError):
        chunk_section(TEXT, 10, 10)


def test_overlap_never_crosses_sections():
    sections = [Section("1. A", 0, TEXT), Section("2. B", 1, "Isi bab kedua yang singkat.")]
    chunks = chunk_document("X", sections, 30, 10)
    last = [c for c in chunks if c.section == "2. B"]
    assert len(last) == 1 and last[0].overlap_words == 0
    assert last[0].text == "Isi bab kedua yang singkat."


def test_corpus_meets_assignment_minimum_and_is_clean():
    documents = load_corpus(CORPUS)
    assert len(documents) >= 15
    formats = {Path(d.meta["file_sumber"]).suffix for d in documents}
    assert {".pdf", ".md", ".txt"} <= formats
    for document in documents:
        text = document.to_text()
        assert "Dokumen Terkendali" not in text
        assert "Halaman 1" not in text
        assert "\r" not in text
        assert len(document.sections) >= 3
        assert all(s.heading != "Pendahuluan" for s in document.sections), document.doc_id


def test_corpus_chunks_end_at_sentence_boundaries():
    chunks = [c for d in load_corpus(CORPUS) for c in chunk_document(d.doc_id, d.sections, 70, 14)]
    assert boundary_quality(chunks) >= 95.0
    assert any(c.overlap_words > 0 for c in chunks)
