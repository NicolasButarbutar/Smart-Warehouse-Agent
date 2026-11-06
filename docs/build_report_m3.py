"""Membangun laporan Grup19-Tugas03.pdf dari korpus dan hasil benchmark.

    uv run --extra report python docs/build_report_m3.py --output Grup19-Tugas03.pdf

Tanpa results/benchmark_results.json, laporan dibangun sebagai DRAF: setiap angka
yang bergantung pada model ditandai kuning dan tidak pernah diisi nilai perkiraan.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, Preformatted, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kb.chunking import boundary_quality, chunk_document  # noqa: E402
from kb.config import CHUNK_SIZE_GRID, CORPUS_DIR, OVERLAP_RATIO_GRID, QUERIES_PATH, RESULTS_PATH  # noqa: E402
from kb.ingest import METADATA_FIELDS  # noqa: E402
from kb.preprocess import load_corpus  # noqa: E402

REPO_URL = "https://github.com/NicolasButarbutar/Smart-Warehouse-Agent"
INK, MUTED, BLUE, ORANGE, GREEN = "#1a1a1a", "#52514e", "#2a78d6", "#d9622b", "#1f9d7a"
HEADER = colors.HexColor("#1f3a5f")


def register_fonts() -> tuple:
    base = Path("/usr/share/fonts/truetype/liberation")
    if (base / "LiberationSerif-Regular.ttf").exists():
        for name, file in (("Body", "LiberationSerif-Regular"), ("Body-B", "LiberationSerif-Bold"),
                           ("Body-I", "LiberationSerif-Italic"), ("Body-BI", "LiberationSerif-BoldItalic"),
                           ("Mono", "LiberationMono-Regular")):
            pdfmetrics.registerFont(TTFont(name, str(base / f"{file}.ttf")))
        pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-B", italic="Body-I", boldItalic="Body-BI")
        return "Body", "Body-B", "Mono"
    return "Times-Roman", "Times-Bold", "Courier"


FONT, BOLD, MONO = register_fonts()
BODY = ParagraphStyle("body", fontName=FONT, fontSize=11, leading=15.5, alignment=TA_JUSTIFY, spaceAfter=7)
BULLET = ParagraphStyle("bullet", parent=BODY, leftIndent=16, bulletIndent=5, spaceAfter=4)
H1 = ParagraphStyle("h1", fontName=BOLD, fontSize=14, leading=18, spaceBefore=12, spaceAfter=7, textColor=HEADER, keepWithNext=1)
H2 = ParagraphStyle("h2", fontName=BOLD, fontSize=11.5, leading=15, spaceBefore=8, spaceAfter=4, textColor=HEADER, keepWithNext=1)
CAP = ParagraphStyle("cap", fontName=FONT, fontSize=9.5, leading=12, alignment=TA_CENTER, textColor=colors.HexColor(MUTED), spaceBefore=3, spaceAfter=9)
TCAP = ParagraphStyle("tcap", parent=CAP, spaceBefore=6, spaceAfter=3, keepWithNext=1)
CELL = ParagraphStyle("cell", fontName=FONT, fontSize=9.2, leading=11.5)
CELLH = ParagraphStyle("cellh", parent=CELL, fontName=BOLD, textColor=colors.white)
CODE = ParagraphStyle("code", fontName=MONO, fontSize=8.6, leading=11, backColor=colors.HexColor("#f3f3f1"), borderPadding=6, spaceBefore=5, spaceAfter=10, leftIndent=6)
CENTER = ParagraphStyle("center", fontName=FONT, fontSize=11.5, leading=16, alignment=TA_CENTER)
PENDING = "<font backColor='#fff2a8'>[hasil]</font>"


class Report:
    def __init__(self, results: dict | None, analysis: dict, workdir: Path) -> None:
        self.r, self.analysis, self.workdir = results, analysis, workdir
        self.story: list = []
        self.docs = load_corpus(CORPUS_DIR)
        self.queries = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))

    def p(self, text: str, style=BODY) -> None:
        self.story.append(Paragraph(text, style))

    def bullets(self, items) -> None:
        for item in items:
            self.story.append(Paragraph(item, BULLET, bulletText="•"))

    def h1(self, text: str) -> None:
        self.p(text, H1)

    def h2(self, text: str) -> None:
        self.p(text, H2)

    def table(self, caption: str, rows: list, widths: list, fontsize: float | None = None) -> None:
        cell = CELL if fontsize is None else ParagraphStyle("c2", parent=CELL, fontSize=fontsize, leading=fontsize + 2.2)
        head = CELLH if fontsize is None else ParagraphStyle("h2c", parent=CELLH, fontSize=fontsize, leading=fontsize + 2.2)
        data = [[Paragraph(str(v), head if i == 0 else cell) for v in row] for i, row in enumerate(rows)]
        table = Table(data, colWidths=[w * cm for w in widths], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HEADER),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b9b8b2")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f6f4")]),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        self.story.append(Paragraph(caption, TCAP))
        self.story.append(table)
        self.story.append(Spacer(1, 9))

    def figure(self, path: Path, width_cm: float, caption: str, heading: str | None = None) -> None:
        from PIL import Image as PILImage

        w, h = PILImage.open(path).size
        parts = [Paragraph(heading, H2)] if heading else []
        parts += [Image(str(path), width=width_cm * cm, height=width_cm * cm * h / w), Paragraph(caption, CAP)]
        self.story.append(KeepTogether(parts))

    def v(self, *path, fmt="{:.3f}", pct=False):
        """Mengambil nilai hasil; tanda kuning bila hasil belum tersedia."""
        node = self.r
        if node is None:
            return PENDING
        for key in path:
            if node is None or (isinstance(node, dict) and key not in node):
                return PENDING
            node = node[key]
        if node is None:
            return "-"
        if isinstance(node, (int, float)) and not isinstance(node, bool):
            return fmt.format(node * 100 if pct else node)
        return escape(str(node))

    def analysis_or_pending(self, key: str) -> None:
        paragraphs = self.analysis.get(key)
        if paragraphs:
            for text in paragraphs:
                self.p(text)
        else:
            self.p("<font backColor='#fff2a8'>[Analisis bagian ini ditulis dari hasil benchmark asli "
                   "setelah results/benchmark_results.json tersedia.]</font>")


def arch_figure(path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.4, 3.5), dpi=200)
    ax.set_xlim(0, 100), ax.set_ylim(0, 40), ax.axis("off")
    def box(x, y, w, h, title, sub, color="#eef3f9"):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.25,rounding_size=1", fc=color, ec=HEADER.hexval().replace("0x", "#"), lw=1))
        ax.text(x + w / 2, y + h * 0.66, title, ha="center", va="center", fontsize=8.6, weight="bold", color=INK)
        ax.text(x + w / 2, y + h * 0.28, sub, ha="center", va="center", fontsize=6.9, color=MUTED)
    def arrow(a, b):
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=9, lw=1, color=MUTED))
    w = 17
    xs = [1, 21.5, 42, 62.5, 83]
    top = [("Korpus", "18 dokumen\nMD, TXT, PDF"), ("preprocess", "normalisasi, buang\nheader dan footer"),
           ("chunking", "bab > paragraf > kalimat\noverlap selaras kalimat"), ("embeddings", "Sentence-Transformers\nvektor L2 ternormalisasi"),
           ("vector_store", "ChromaDB persisten\ncosine + metadata")]
    for x, (t, s) in zip(xs, top):
        box(x, 26, w, 12, t, s)
    for a, b in zip(xs, xs[1:]):
        arrow((a + w + 0.3, 32), (b - 0.3, 32))
    box(62.5, 3, w, 12, "retriever", "vektor, BM25, hybrid RRF\nfilter dan ambang", "#eaf6f1")
    box(83, 3, w, 12, "Hasil", "potongan bersumber\natau penolakan", "#eaf6f1")
    box(42, 3, w, 12, "Kueri pengguna", "di-encode dengan\nmodel yang sama", "#eaf6f1")
    arrow((59.3, 9), (62.2, 9)); arrow((79.8, 9), (82.7, 9)); arrow((91.5, 25.7), (73, 15.5))
    ax.text(84, 19.5, "dibaca saat pencarian", fontsize=6.8, color=MUTED)
    ax.text(1, 11, "Tahap atas: ingestion (sekali jalan)\nTahap bawah: pencarian (setiap kueri)", fontsize=7.6, color=MUTED, va="center")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def style_axes(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#b9b8b2")
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(axis="both", color="#ecebe6", lw=0.6)
    ax.set_axisbelow(True)


def chunk_figure(results: dict, path: Path) -> None:
    rows = results["eksperimen_chunking"]["baris"]
    fig, ax = plt.subplots(figsize=(6.6, 3.2), dpi=200)
    for ratio, color, marker in zip(OVERLAP_RATIO_GRID, (BLUE, ORANGE, GREEN, "#6250d6"), "osD^"):
        points = sorted((r["chunk_words"], r["mrr"]) for r in rows if r["overlap_ratio"] == ratio)
        ax.plot(*zip(*points), color=color, marker=marker, ms=4.5, lw=1.6, label=f"overlap {ratio:.0%}")
    ax.set_xlabel("Ukuran chunk (kata)", fontsize=8.5, color=MUTED); ax.set_ylabel("MRR kueri dev", fontsize=8.5, color=MUTED)
    style_axes(ax); ax.legend(frameon=False, fontsize=7.5, ncols=4, loc="lower center", bbox_to_anchor=(0.5, 1.0))
    fig.savefig(path, bbox_inches="tight", facecolor="white"); plt.close(fig)


def cosine_figure(results: dict, path: Path) -> None:
    rows = results["evaluasi_test"]["per_kueri"]
    threshold = results["konfigurasi_terpilih"]["threshold"]
    groups = [("Literal", "literal", None), ("Sinonim", "sinonim", None), ("Ambigu", "ambigu", None),
              ("OOD dekat", "ood", "dekat"), ("OOD jauh", "ood", "jauh")]
    fig, ax = plt.subplots(figsize=(6.6, 3), dpi=200)
    for y, (label, kind, sub) in enumerate(reversed(groups)):
        values = [r["cos_top1"] for r in rows if r["tipe"] == kind and (sub is None or r.get("ood_jenis") == sub)]
        offsets = [y + ((i % 5) - 2) * 0.07 for i in range(len(values))]
        ax.scatter(values, offsets, s=26, color=ORANGE if kind == "ood" else BLUE, edgecolor="white", lw=0.6, marker="s" if kind == "ood" else "o", zorder=3)
    ax.axvline(threshold, color=INK, lw=1, ls="--")
    ax.text(threshold, len(groups) - 0.42, f" ambang {threshold:.3f}", fontsize=7.5, color=INK)
    ax.set_yticks(range(len(groups)), [g[0] for g in reversed(groups)])
    ax.set_xlabel("Cosine similarity potongan teratas (kueri test)", fontsize=8.5, color=MUTED)
    style_axes(ax); fig.savefig(path, bbox_inches="tight", facecolor="white"); plt.close(fig)


def threshold_figure(results: dict, path: Path) -> None:
    curve = results["evaluasi_test"]["kurva_ambang"]
    threshold = results["konfigurasi_terpilih"]["threshold"]
    fig, ax = plt.subplots(figsize=(6.6, 2.9), dpi=200)
    xs = [c["threshold"] for c in curve]
    for key, label, color in (("precision", "Presisi penolakan", BLUE), ("recall", "Recall penolakan", ORANGE), ("false_reject_rate", "Salah tolak kueri domain", GREEN)):
        ax.plot(xs, [c[key] for c in curve], color=color, lw=1.8, label=label)
    ax.axvline(threshold, color=INK, lw=1, ls="--")
    ax.set_xlabel("Ambang cosine", fontsize=8.5, color=MUTED); ax.set_ylim(-0.03, 1.05)
    style_axes(ax); ax.legend(frameon=False, fontsize=7.5, ncols=3, loc="lower center", bbox_to_anchor=(0.5, 1.0))
    fig.savefig(path, bbox_inches="tight", facecolor="white"); plt.close(fig)


def cover(rep: Report) -> None:
    rep.story.append(Spacer(1, 1.2 * cm))
    rep.p("<b>SMART WAREHOUSE MANAGEMENT AGENT</b>", ParagraphStyle("t", parent=CENTER, fontSize=18, leading=24, textColor=HEADER))
    rep.p("<b>Basis Pengetahuan Korpus dan Vector Semantic Search</b>", ParagraphStyle("t2", parent=CENTER, fontSize=13, leading=20, spaceAfter=22))
    meta = [["Mata Kuliah", "10S3001 – Kecerdasan Buatan (Artificial Intelligence) (+P)"],
            ["Kode Tugas", "Tugas 3 (Milestone 3 – W07) (Milestone Proyek Terpadu)"],
            ["Judul Milestone 3", "Pembangunan Basis Pengetahuan Korpus &amp; Vector Semantic Search"],
            ["Kelompok", "19"], ["Dosen Pengampu", "Samuel Indra Gunawan Situmeang"],
            ["Semester / T.A.", "Gasal 2026/2027"], ["Repositori GitHub", REPO_URL]]
    table = Table([[Paragraph(f"<b>{a}</b>", CELL), Paragraph(b, CELL)] for a, b in meta], colWidths=[4.2 * cm, 11.3 * cm])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b9b8b2")), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f9"))]))
    rep.story.append(table)
    rep.story.append(Spacer(1, 22))
    rep.p("Disusun oleh:", CENTER)
    rep.story.append(Spacer(1, 6))
    rows = [["Nama", "NIM"], ["Nicolas J Grace Butarbutar", "12S24038"], ["Indah Triyuni Siahaan", "12S24052"], ["Swasti Maristella Sihombing", "12S24030"]]
    data = [[Paragraph(v, CELLH if i == 0 else CELL) for v in row] for i, row in enumerate(rows)]
    team = Table(data, colWidths=[7 * cm, 3.5 * cm])
    team.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), HEADER), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b9b8b2")), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    rep.story.append(team)
    rep.story.append(Spacer(1, 2.2 * cm))
    for line in ("PROGRAM STUDI SARJANA SISTEM INFORMASI", "FAKULTAS INFORMATIKA DAN TEKNIK ELEKTRO", "INSTITUT TEKNOLOGI DEL", "2026/2027"):
        rep.p(f"<b>{line}</b>", CENTER)
    rep.story.append(PageBreak())


def build(rep: Report, args) -> None:
    docs, queries, r = rep.docs, rep.queries, rep.r
    words_raw = sum(d.stats["kata_mentah"] for d in docs)
    words_clean = sum(d.stats["kata_bersih"] for d in docs)
    removed = sum(d.stats["baris_boilerplate_dibuang"] for d in docs)
    pages = sum(d.stats["jumlah_halaman"] for d in docs)
    fmt_count = {}
    for d in docs:
        fmt = Path(d.meta["file_sumber"]).suffix.lstrip(".").upper()
        fmt_count[fmt] = fmt_count.get(fmt, 0) + 1
    cover(rep)

    rep.h1("1. Pendahuluan")
    rep.h2("1.1 Posisi Milestone 3 dalam Proyek")
    rep.p("Pada Milestone 1, Smart Warehouse Agent untuk studi kasus Gudang Nusantara Logistik memutuskan lokasi dan rute barang dengan UCS dan A*. Milestone 2 menambahkan penjadwalan shift staf dengan CSP (AC-3 dan Backtracking). Kedua modul itu menjawab pertanyaan keputusan, tetapi belum dapat menjawab pertanyaan pengetahuan seperti “berapa suhu ruang beku?” atau “bolehkah operator tanpa lisensi mengemudikan forklift?”.")
    rep.p("Jawaban pertanyaan tersebut tersimpan pada SOP, kebijakan, manual, dan ringkasan regulasi. Pencarian kata kunci sering gagal karena karyawan memakai kata yang berbeda dari kata pada dokumen. Milestone 3 membangun memori semantik yang menemukan potongan dokumen berdasarkan makna, dan yang berani menolak bila pertanyaan berada di luar cakupan korpus. Fondasi ini akan dihubungkan ke model bahasa besar pada tahap Retrieval-Augmented Generation (RAG) (Lewis dkk., 2020).")
    rep.h2("1.2 Pemetaan terhadap Rubrik")
    rep.table("Tabel 1.1 Pemetaan rubrik Milestone 3 ke bagian laporan dan artefak", [
        ["Komponen Rubrik", "Bobot", "Bagian Laporan", "Artefak di Repositori"],
        ["Kualitas Data Korpus &amp; Prapemrosesan", "25%", "Bab 2 dan Bab 3", "data/raw/corpus/, src/kb/preprocess.py, src/kb/chunking.py"],
        ["Pipeline Embedding &amp; Vector Store ChromaDB", "45%", "Bab 4 dan Bab 7", "src/kb/embeddings.py, vector_store.py, retriever.py, data/vectorstore/"],
        ["Akurasi &amp; Analisis Temu Balik Semantik", "30%", "Bab 5 dan Bab 6", "data/benchmark/queries.json, src/kb/benchmark.py, results/benchmark_results.json"],
    ], [5.4, 1.2, 2.8, 6.6])

    rep.h1("2. Korpus Dokumen Enterprise")
    rep.h2("2.1 Sumber dan Sifat Korpus")
    formats = ", ".join(f"{n} {k}" for k, n in sorted(fmt_count.items()))
    rep.p(f"Korpus terdiri atas {len(docs)} dokumen ({formats}) dengan total {words_clean:,} kata bersih".replace(",", ".") + f". Jumlah ini melampaui syarat minimal 10–15 dokumen. Seluruhnya merupakan dokumen <b>sintetis</b> untuk perusahaan fiktif Gudang Nusantara Logistik, sehingga prosedur dan angka internalnya tidak berasal dari perusahaan nyata. REG-01 merangkum peraturan yang berlaku umum, yaitu UU 13/2003 sebagaimana diubah UU 6/2023, PP 35/2021, dan Permenaker 8/2020, dan dokumennya sendiri menyatakan bahwa ringkasan itu bukan pengganti teks resmi.")
    rows = [["ID", "Judul Dokumen", "Jenis", "Format", "Kata"]]
    for d in docs:
        rows.append([d.doc_id, escape(d.meta["judul"]), d.meta["jenis"], Path(d.meta["file_sumber"]).suffix.lstrip(".").upper(), d.stats["kata_bersih"]])
    rep.table("Tabel 2.1 Daftar dokumen korpus", rows, [1.6, 9.2, 2.0, 1.4, 1.2], fontsize=8.8)
    rep.h2("2.2 Representativitas terhadap Domain")
    rep.p("Dokumen dipilih agar mencakup seluruh rantai proses gudang serta kebutuhan modul sebelumnya, bukan sekadar memenuhi jumlah. Isi korpus konsisten dengan data proyek: identitas rak R01–R16, DOCK_IN, DOCK_OUT, STAGING, tiga shift, dan batas 40 jam per minggu pada solver M2.")
    rep.table("Tabel 2.2 Keterkaitan korpus dengan pain points dan modul proyek", [
        ["Kebutuhan", "Dokumen", "Keterkaitan"],
        ["Salah taruh dan selisih stok (M1)", "SOP-01, SOP-02, SOP-08", "Aturan pemindaian, slotting, dan penyelesaian selisih."],
        ["Waktu picking tinggi (M1)", "SOP-02, SOP-03, KEB-05", "Zona fast-moving, rute terpendek, dan target kinerja."],
        ["Keputusan rute agen (M1)", "SOP-02, SOP-10", "Rute A*, lorong terhalang, jalur bersama AGV dan forklift."],
        ["Batasan penjadwalan (M2)", "KEB-01, KEB-02, REG-01", "Aturan C0–C4 dan dasar regulasinya, dalam bentuk bahasa alami."],
        ["Mutu dan keamanan barang", "SOP-05, SOP-06, SOP-07, SOP-09", "Rantai dingin, FEFO, barang rapuh, dan retur."],
        ["Risiko operasional", "SOP-04, SOP-11, KEB-03, KEB-04, MAN-01", "Serah terima, darurat, K3, keamanan, dan gangguan sistem."],
    ], [5.0, 4.4, 6.6])
    rep.h2("2.3 Pembersihan Teks")
    rep.p("Berkas PDF dan TXT sengaja dibiarkan membawa gangguan yang lazim pada dokumen perusahaan: header dan footer berulang, nomor halaman, kutip melengkung, spasi ganda, akhir baris Windows, dan baris yang terbungkus. Modul preprocess.py membersihkannya secara otomatis dengan urutan berikut.")
    rep.bullets([
        "<b>Normalisasi karakter:</b> Unicode NFKC, penyeragaman kutip dan tanda hubung, serta penghapusan karakter kontrol dan karakter tak terlihat.",
        "<b>Header dan footer:</b> baris yang muncul pada minimal 60% halaman dibuang, ditambah pola nomor halaman dan label dokumen terkendali.",
        "<b>Rekonstruksi struktur:</b> pemenggalan akhir baris disambung, baris dalam satu bab digabung, dan judul bab bernomor dikenali tanpa keliru mengenali langkah prosedur sebagai judul.",
        "<b>Validasi:</b> dokumen yang kosong setelah dibersihkan menghentikan proses, dan pengujian otomatis memastikan tidak ada sisa header pada korpus.",
    ])
    pdf_docs = [d for d in docs if d.meta["file_sumber"].endswith(".pdf")]
    txt_docs = [d for d in docs if d.meta["file_sumber"].endswith(".txt")]
    md_docs = [d for d in docs if d.meta["file_sumber"].endswith(".md")]
    rows = [["Format", "Dokumen", "Halaman", "Kata mentah", "Kata bersih", "Baris gangguan dibuang"]]
    for label, group in (("PDF", pdf_docs), ("TXT", txt_docs), ("MD", md_docs), ("Total", docs)):
        rows.append([label, len(group), sum(d.stats["jumlah_halaman"] for d in group), sum(d.stats["kata_mentah"] for d in group), sum(d.stats["kata_bersih"] for d in group), sum(d.stats["baris_boilerplate_dibuang"] for d in group)])
    rep.table("Tabel 2.3 Dampak pembersihan pada korpus", rows, [2.2, 2.0, 2.0, 2.8, 2.8, 4.2])
    rep.p(f"Pembersihan membuang {removed} baris gangguan atau {words_raw - words_clean} kata ({100 * (words_raw - words_clean) / words_raw:.1f}% kata mentah) tanpa mengurangi isi bab. Hasilnya disimpan pada data/processed/corpus_clean/ agar dapat diperiksa.")

    rep.h1("3. Strategi Chunking")
    rep.h2("3.1 Algoritma Word-Aware Recursive Chunking")
    rep.p("Pemotongan dilakukan bertingkat: bab, paragraf, kalimat, klausa, lalu kata. Tingkat yang lebih halus hanya dipakai bila satu unit melebihi batas, sehingga kalimat tetap utuh selama muat. Batas diukur dalam jumlah kata. Overlap tidak mengambil N kata secara mekanis, melainkan mengulang kalimat utuh terakhir dari potongan sebelumnya sampai batas overlap, dan tidak melintasi batas bab agar konteks dua topik tidak bercampur.")
    rep.story.append(Preformatted("""function CHUNK(bab, ukuran, overlap):
    unit <- pecah bab menjadi kalimat (dipecah lagi hanya bila > ukuran)
    for u in unit:
        if kata(potongan) + kata(u) > ukuran:
            simpan potongan
            potongan <- kalimat utuh terakhir dengan total kata <= overlap
        tambahkan u ke potongan
    simpan potongan terakhir bila memuat kalimat baru""", CODE))
    rep.p("Teks yang di-encode diberi awalan judul dokumen dan nama bab (“judul - bab: isi”). Dengan demikian, potongan seperti “Alarm merah berbunyi…” tetap membawa konteks bahwa ia berasal dari SOP rantai dingin. Isi potongan disimpan terpisah dari awalan ini.")
    rep.h2("3.2 Justifikasi Parameter Size dan Overlap")
    rep.p("Parameter tidak ditetapkan secara intuitif, melainkan melalui tiga dasar berikut.")
    rep.bullets([
        "<b>Batas model.</b> Model keluarga paraphrase-multilingual memiliki max_seq_length 128 token. Token di luar batas diabaikan tanpa peringatan, sehingga potongan yang terlalu panjang kehilangan bagian akhirnya saat di-encode. Sistem karena itu menghitung token setiap potongan dengan tokenizer model yang dipakai, termasuk awalan judul, dan konfigurasi dengan lebih dari 5% potongan terpotong tidak dapat dipilih.",
        "<b>Eksperimen terkendali.</b> Enam ukuran (" + ", ".join(map(str, CHUNK_SIZE_GRID)) + " kata) dan empat rasio overlap (" + ", ".join(f"{int(x * 100)}%" for x in OVERLAP_RATIO_GRID) + ") dievaluasi pada kueri dev, sehingga ada 24 konfigurasi.",
        "<b>Aturan pilih yang ditetapkan lebih dulu.</b> Di antara konfigurasi yang lolos batas token, dipilih MRR tertinggi, lalu Answer@3, lalu AUC out-of-domain, lalu jumlah chunk tersedikit. Kueri test tidak dipakai pada tahap ini.",
    ])
    rows = [["Ukuran", "Overlap", "Jumlah chunk", "Rata-rata kata", "Maks. kata", "Berakhir di akhir kalimat", "Chunk ber-overlap"]]
    for size in CHUNK_SIZE_GRID:
        for ratio in (0.0, 0.2):
            chunks = [c for d in docs for c in chunk_document(d.doc_id, d.sections, size, int(round(size * ratio)))]
            rows.append([size, int(round(size * ratio)), len(chunks), f"{sum(c.n_words for c in chunks) / len(chunks):.1f}", max(c.n_words for c in chunks), f"{boundary_quality(chunks):.1f}%", sum(c.overlap_words > 0 for c in chunks)])
    rep.table("Tabel 3.1 Struktur potongan pada sebagian grid (terukur dari korpus, tanpa model)", rows, [1.6, 1.6, 2.2, 2.4, 1.9, 3.5, 2.8])
    worst = min(boundary_quality([c for d in docs for c in chunk_document(d.doc_id, d.sections, size, int(round(size * ratio)))]) for size in CHUNK_SIZE_GRID for ratio in OVERLAP_RATIO_GRID)
    rep.p(("Pada seluruh 24 konfigurasi, semua potongan berakhir di akhir kalimat" if worst == 100 else f"Pada seluruh 24 konfigurasi, minimal {worst:.1f}% potongan berakhir di akhir kalimat") + ", sehingga pemotongan tidak memutus makna kalimat. Jumlah chunk ber-overlap menurun pada ukuran besar karena lebih banyak bab yang sudah muat dalam satu potongan.")
    rows = [["Ukuran", "Overlap", "Chunk", "Token rata-rata", "% terpotong", "Hit@1", "MRR", "Answer@3", "AUC OOD"]]
    if r and r.get("eksperimen_chunking"):
        chosen = r["eksperimen_chunking"]["terpilih"]
        for row in r["eksperimen_chunking"]["baris"]:
            mark = row["chunk_words"] == chosen["chunk_words"] and row["overlap_words"] == chosen["overlap_words"]
            cells = [row["chunk_words"], row["overlap_words"], row["jumlah_chunk"], f"{row['token_rata2']:.0f}", f"{row['pct_terpotong_model']:.1f}", f"{row['hit_at_1']:.3f}", f"{row['mrr']:.3f}", f"{row['answer_at_3']:.3f}", f"{row['auc_ood']:.3f}"]
            rows.append([f"<b>{c}</b>" for c in cells] if mark else cells)
    else:
        rows.append(["40–130", "0–30%", PENDING, PENDING, PENDING, PENDING, PENDING, PENDING, PENDING])
    rep.table("Tabel 3.2 Hasil eksperimen chunking pada kueri dev (baris tebal = terpilih)", rows, [1.5, 1.5, 1.4, 2.0, 1.9, 1.6, 1.6, 2.0, 1.9], fontsize=8.6)
    if r and r.get("eksperimen_chunking"):
        fig = rep.workdir / "chunk.png"
        chunk_figure(r, fig)
        rep.figure(fig, 12.5, "Gambar 3.1 MRR kueri dev terhadap ukuran chunk dan overlap")
    rep.analysis_or_pending("chunking")

    rep.story.append(PageBreak())
    rep.h1("4. Pipeline Embedding dan Vector Store")
    fig = rep.workdir / "arch.png"
    arch_figure(fig)
    rep.figure(fig, 16, "Gambar 4.1 Arsitektur pipeline basis pengetahuan", heading="4.1 Arsitektur Modular")
    rep.table("Tabel 4.1 Modul pada src/kb/", [
        ["Modul", "Tanggung Jawab"],
        ["preprocess.py", "Memuat MD, TXT, PDF; membersihkan teks; mengenali struktur bab."],
        ["chunking.py", "Word-aware recursive chunking dengan overlap selaras kalimat."],
        ["embeddings.py", "Pembungkus Sentence-Transformers, vektor L2, dan penghitung token."],
        ["ingest.py", "Menyusun ID, teks encode, metadata, dan statistik potongan."],
        ["vector_store.py", "Akses ChromaDB persisten dan indeks numpy eksak sebagai pembanding."],
        ["lexical.py / retriever.py", "BM25, fusi hybrid RRF, filter metadata, dan penolakan out-of-domain."],
        ["evaluate.py / benchmark.py", "Metrik, kalibrasi ambang, seleksi model dan chunking, evaluasi test."],
        ["kb_pipeline.py", "Antarmuka baris perintah: all, ingest, search."],
    ], [5.0, 11.0])
    rep.h2("4.2 Pemilihan Model Embedding")
    rep.p("Korpus berbahasa Indonesia dengan istilah gudang berbahasa Inggris (put-away, picking, cold storage), sehingga model multibahasa diduga lebih tepat. Dugaan ini diuji, bukan diasumsikan: model khusus bahasa Inggris dipakai sebagai pembanding, dan arsitektur Sentence-Transformers (Reimers &amp; Gurevych, 2019) dipakai pada ketiganya. Pemenang ditentukan dari rata-rata MRR, Answer@3, dan AUC pada kueri dev.")
    rows = [["Model", "Dimensi", "Maks. token", "Hit@1", "MRR", "Answer@3", "AUC OOD", "Skor"]]
    specs = [("all-MiniLM-L6-v2", 384, 256), ("paraphrase-multilingual-MiniLM-L12-v2", 384, 128), ("paraphrase-multilingual-mpnet-base-v2", 768, 128)]
    if r and r.get("perbandingan_model"):
        for row in r["perbandingan_model"]["baris"]:
            cells = [row["model"].split("/")[-1], row["dimensi"], row["max_seq_length"], f"{row['hit_at_1']:.3f}", f"{row['mrr']:.3f}", f"{row['answer_at_3']:.3f}", f"{row['auc_ood']:.3f}", f"{row['skor_seleksi']:.3f}"]
            rows.append([f"<b>{c}</b>" for c in cells] if row["model"] == r["perbandingan_model"]["terpilih"] else cells)
    else:
        for name, dim, seq in specs:
            rows.append([name, dim, seq, PENDING, PENDING, PENDING, PENDING, PENDING])
    rep.table("Tabel 4.2 Perbandingan model pada kueri dev (baris tebal = terpilih)", rows, [5.6, 1.5, 1.3, 1.3, 1.3, 1.7, 1.4, 1.3], fontsize=8.2)
    rep.analysis_or_pending("model")
    rep.h2("4.3 Penyimpanan ChromaDB Persisten")
    rep.p("Indeks disimpan melalui chromadb.PersistentClient pada data/vectorstore/, dengan koleksi enterprise_kb berjarak cosine. Vektor dihitung sendiri lalu dinormalisasi L2, sehingga skor kemiripan adalah 1 − jarak cosine. Setiap kali koleksi dibangun, sistem membandingkan skor ChromaDB dengan perkalian titik vektor dan berhenti bila berbeda, sehingga skor pada laporan pasti cosine. Koleksi dibangun ulang secara idempoten dan menyimpan nama model serta parameter chunking.")
    rep.table("Tabel 4.3 Bukti pengindeksan dan persistensi", [
        ["Pemeriksaan", "Hasil"],
        ["Jumlah vektor tersimpan", rep.v("ingestion", "jumlah_vektor_chromadb", fmt="{:d}")],
        ["Dimensi vektor", rep.v("ingestion", "dimensi", fmt="{:d}")],
        ["Model, ukuran chunk, overlap", f"{rep.v('konfigurasi_terpilih', 'model_name')}, {rep.v('konfigurasi_terpilih', 'chunk_words', fmt='{:d}')} kata, {rep.v('konfigurasi_terpilih', 'overlap_words', fmt='{:d}')} kata"],
        ["Potongan terpotong oleh model", f"{rep.v('ingestion', 'statistik_chunk', 'pct_terpotong_model', fmt='{:.1f}')}%"],
        ["Dibuka ulang dari proses Python terpisah: jumlah vektor", rep.v("uji_persistensi", "jumlah_vektor_proses_baru", fmt="{:d}")],
        ["Kueri dengan hasil identik setelah dibuka ulang", f"{rep.v('uji_persistensi', 'kueri_hasil_identik', fmt='{:d}')} dari {rep.v('uji_persistensi', 'kueri_diuji', fmt='{:d}')}"],
        ["Recall@5 HNSW terhadap pencarian eksak", rep.v("hnsw_vs_eksak", "recall_at_5")],
        ["Metadata terisi lengkap", f"{rep.v('ingestion', 'pct_metadata_lengkap', fmt='{:.1f}')}%"],
    ], [10.5, 5.5])
    rep.h2("4.4 Metadata untuk Hybrid Search")
    rep.p(f"Setiap vektor menyimpan {len(METADATA_FIELDS)} kolom metadata. Kolom ini memungkinkan penyaringan terstruktur, audit asal jawaban, dan sitasi sumber pada tahap RAG.")
    rep.table("Tabel 4.4 Skema metadata per potongan", [
        ["Kelompok", "Kolom", "Kegunaan"],
        ["Identitas", "doc_id, judul, file_sumber, format_sumber", "Sitasi sumber dan pelacakan ke berkas asli."],
        ["Klasifikasi", "jenis, kategori, departemen, level_akses, kata_kunci", "Filter topik dan kontrol akses."],
        ["Tata kelola", "pemilik, versi, tanggal_berlaku, tahun_berlaku", "Memilih dokumen yang masih berlaku."],
        ["Struktur", "bab, bab_index, chunk_index, total_chunk_dokumen", "Mengambil potongan tetangga dan menampilkan bab."],
        ["Teknis", "n_kata, n_kata_overlap, n_token", "Audit kualitas chunking."],
        ["Domain", "rak_terkait", "Menghubungkan pengetahuan dengan rak pada modul M1."],
    ], [2.6, 7.2, 6.2])
    rep.p("Mode hybrid menggabungkan peringkat vektor dengan BM25 (Robertson &amp; Zaragoza, 2009) melalui Reciprocal Rank Fusion dengan k = 60 (Cormack dkk., 2009), sehingga kode persis seperti E-305 tetap mudah ditemukan tanpa kehilangan kemampuan menangkap sinonim. Keduanya menghormati filter metadata yang sama. ChromaDB memakai indeks HNSW (Malkov &amp; Yashunin, 2020).")
    rows = [["Kueri", "Filter", "Mode", "Hasil", "Semua sesuai filter"]]
    if r:
        for row in r["uji_filter_metadata"]:
            rows.append([escape(row["kueri"]), escape(json.dumps(row["filter"])), row["mode"], row["jumlah_hasil"], "Ya" if row["semua_sesuai_filter"] else "Tidak"])
    else:
        rows.append(["4 kueri, 2 mode", PENDING, "vector, hybrid", PENDING, PENDING])
    rep.table("Tabel 4.5 Uji filter metadata pada ChromaDB", rows, [4.7, 6.3, 1.5, 1.2, 2.3], fontsize=8.4)

    rep.h1("5. Metodologi Benchmark")
    rep.h2("5.1 Himpunan Kueri")
    count = lambda t, s, j=None: sum(1 for q in queries if q["tipe"] == t and q["split"] == s and (j is None or q.get("ood_jenis") == j))
    rep.p(f"Benchmark memakai {len(queries)} kueri, jauh di atas syarat minimal 5 kueri. Kueri dibagi menjadi <b>dev</b> untuk memilih model, chunking, dan ambang, serta <b>test</b> yang hanya dipakai pada evaluasi akhir. Pemisahan ini mencegah skor akhir terlalu optimistis akibat parameter yang disesuaikan dengan kueri uji.")
    rep.table("Tabel 5.1 Komposisi kueri", [
        ["Tipe", "Dev", "Test", "Tujuan"],
        ["Literal", count("literal", "dev"), count("literal", "test"), "Kontrol: kueri memakai kata yang sama dengan dokumen."],
        ["Sinonim", count("sinonim", "dev"), count("sinonim", "test"), "Inti pengujian: makna sama, kata berbeda, termasuk dua kueri bahasa Inggris."],
        ["Ambigu", count("ambigu", "dev"), count("ambigu", "test"), "Kueri umum yang sah dijawab beberapa dokumen."],
        ["OOD jauh", count("ood", "dev", "jauh"), count("ood", "test", "jauh"), "Topik di luar bisnis, seperti resep atau sejarah."],
        ["OOD dekat", count("ood", "dev", "dekat"), count("ood", "test", "dekat"), "Terdengar seperti topik gudang, tetapi jawabannya tidak ada di korpus."],
    ], [2.4, 1.2, 1.2, 11.2])
    examples = [["Tipe", "Contoh Kueri", "Dokumen Target"]]
    for qid in ("LIT-02", "SIN-01", "SIN-08", "AMB-01", "OOD-01", "OOD-02"):
        q = next(x for x in queries if x["id"] == qid)
        examples.append([q["tipe"], escape(q["kueri"]), ", ".join(q["target_docs"]) or "(harus ditolak)"])
    rep.table("Tabel 5.2 Contoh kueri", examples, [1.8, 10.6, 3.6])
    rep.h2("5.2 Metrik")
    rep.bullets([
        "<b>Hit@k</b> dan <b>MRR</b> mengukur posisi dokumen target pada peringkat dokumen, setelah potongan dari dokumen yang sama digabung.",
        "<b>Answer@3</b> lebih ketat: salah satu dari tiga potongan teratas harus berasal dari dokumen target dan memuat frasa bukti jawaban. Metrik ini relevan karena RAG membaca potongan, bukan dokumen utuh.",
        "<b>Cosine similarity</b> dilaporkan per tipe kueri. Selisih skor dengan dokumen berikutnya dipakai untuk membaca ambiguitas.",
        "<b>Presisi penolakan</b> = OOD yang ditolak / seluruh kueri yang ditolak. <b>Recall penolakan</b> = OOD yang ditolak / seluruh OOD. <b>Salah tolak</b> = kueri domain yang ditolak / seluruh kueri domain.",
        "<b>AUC</b> mengukur peluang kueri domain memperoleh cosine lebih tinggi daripada kueri OOD, tanpa bergantung pada satu ambang.",
        "<b>Selang kepercayaan Wilson 95%</b> disertakan karena jumlah kueri kecil, agar perbedaan kecil tidak dibaca berlebihan.",
    ])
    rep.h2("5.3 Kalibrasi Ambang Penolakan")
    rep.p("Kueri ditolak bila cosine potongan teratas berada di bawah ambang τ. Nilai τ dipilih pada kueri dev dengan F1 penolakan tertinggi, dengan syarat salah tolak kueri domain maksimal 10%, karena menolak pertanyaan yang sah sama merugikannya dengan menjawab pertanyaan di luar cakupan. Nilai τ lalu dikunci sebelum evaluasi test.")

    rep.h1("6. Hasil dan Analisis")
    rep.h2("6.1 Akurasi Temu Balik")
    rows = [["Mode", "Tipe", "n", "Hit@1 (CI 95%)", "Hit@3", "MRR", "Answer@3"]]
    if r:
        for mode, label in (("vector", "Vektor"), ("bm25", "BM25"), ("hybrid", "Hybrid")):
            for kind in ("literal", "sinonim", "ambigu", "semua_domain"):
                s = r["evaluasi_test"]["ringkasan_per_mode"][mode][kind]
                rows.append([label, kind.replace("semua_domain", "<b>semua</b>"), s["n"], f"{s['hit_at_1']:.3f} ({s['hit_at_1_ci95'][0]:.2f}–{s['hit_at_1_ci95'][1]:.2f})", f"{s['hit_at_3']:.3f}", f"{s['mrr']:.3f}", f"{s['answer_at_3']:.3f}"])
    else:
        for label in ("Vektor", "BM25", "Hybrid"):
            rows.append([label, "literal, sinonim, ambigu, semua", PENDING, PENDING, PENDING, PENDING, PENDING])
    rep.table("Tabel 6.1 Kinerja temu balik pada kueri test", rows, [1.8, 3.6, 0.9, 3.8, 1.5, 1.5, 2.0], fontsize=8.8)
    rep.analysis_or_pending("akurasi")
    rep.h2("6.2 Analisis Cosine Similarity")
    rows = [["Tipe", "n", "Rata-rata", "Minimum", "Median", "Maksimum"]]
    for kind in ("literal", "sinonim", "ambigu", "ood"):
        rows.append([kind, *(rep.v("evaluasi_test", "statistik_cosine", kind, key, fmt=("{:d}" if key == "n" else "{:.3f}")) for key in ("n", "rata2", "min", "median", "maks"))])
    rep.table("Tabel 6.2 Cosine similarity potongan teratas pada kueri test", rows, [3.2, 1.3, 2.8, 2.8, 2.8, 2.8])
    if r:
        fig = rep.workdir / "cos.png"
        cosine_figure(r, fig)
        rep.figure(fig, 12.5, "Gambar 6.1 Sebaran cosine per tipe kueri. Lingkaran: kueri domain; persegi: OOD.")
    rep.analysis_or_pending("cosine")
    rep.h2("6.3 Kueri Ambigu")
    rep.p(f"Selisih rata-rata cosine antara dokumen teratas dan dokumen berikutnya adalah {rep.v('evaluasi_test', 'selisih_top_dokumen', 'ambigu')} pada kueri ambigu, dibandingkan {rep.v('evaluasi_test', 'selisih_top_dokumen', 'spesifik')} pada kueri spesifik. Rata-rata {rep.v('evaluasi_test', 'cakupan_target_ambigu', fmt='{:.2f}')} dokumen sah muncul dalam lima dokumen teratas.")
    rep.analysis_or_pending("ambigu")
    rep.h2("6.4 Presisi Penolakan Out-of-Domain")
    p = lambda key: rep.v("evaluasi_test", "penolakan_ood", key)
    dekat = (rep.v("evaluasi_test", "penolakan_ood", "per_jenis_ood", "dekat", "ditolak", fmt="{:d}"), rep.v("evaluasi_test", "penolakan_ood", "per_jenis_ood", "dekat", "n", fmt="{:d}"))
    jauh = (rep.v("evaluasi_test", "penolakan_ood", "per_jenis_ood", "jauh", "ditolak", fmt="{:d}"), rep.v("evaluasi_test", "penolakan_ood", "per_jenis_ood", "jauh", "n", fmt="{:d}"))
    rep.table("Tabel 6.3 Hasil penolakan pada kueri test dengan ambang hasil kalibrasi dev", [
        ["Ukuran", "Nilai", "Ukuran", "Nilai"],
        ["Ambang τ", rep.v("konfigurasi_terpilih", "threshold"), "AUC", p("auc")],
        ["Presisi penolakan", p("precision"), "Recall penolakan", p("recall")],
        ["F1 penolakan", p("f1"), "Salah tolak kueri domain", p("false_reject_rate")],
        ["OOD jauh ditolak", f"{jauh[0]} dari {jauh[1]}", "OOD dekat ditolak", f"{dekat[0]} dari {dekat[1]}"],
        ["Sukses end-to-end", rep.v("evaluasi_test", "sukses_end_to_end"), "Latensi median vektor / hybrid (ms)", f"{rep.v('evaluasi_test', 'latensi_ms', 'vector', fmt='{:.1f}')} / {rep.v('evaluasi_test', 'latensi_ms', 'hybrid', fmt='{:.1f}')}"],
    ], [4.6, 3.4, 5.0, 3.0])
    if r:
        fig = rep.workdir / "thr.png"
        threshold_figure(r, fig)
        rep.figure(fig, 12.5, "Gambar 6.2 Pertukaran presisi, recall, dan salah tolak terhadap ambang pada kueri test. Garis putus: ambang terpilih.")
    rep.analysis_or_pending("ood")
    rep.h2("6.5 Analisis Kesalahan")
    rep.analysis_or_pending("kesalahan")

    rep.h1("7. Pengujian Otomatis")
    if args.m12_tests:
        rep.p(f"Pengujian memakai pytest. Selain {args.m12_tests} pengujian M1 dan M2, Milestone 3 menambahkan {args.kb_tests} pengujian, yaitu {args.kb_tests - args.chroma_tests} pengujian unit dan {args.chroma_tests} pengujian integrasi dengan ChromaDB asli.")
    else:
        rep.p(f"Pengujian memakai pytest. Pada repositori ini tersedia {args.kb_tests} pengujian Milestone 3, yaitu {args.kb_tests - args.chroma_tests} pengujian unit dan {args.chroma_tests} pengujian integrasi dengan ChromaDB asli.")
    rep.table("Tabel 7.1 Cakupan pengujian Milestone 3", [
        ["Berkas", "Yang Diuji"],
        ["test_kb_preprocess_chunking.py", "Normalisasi, header dan footer, struktur bab, batas ukuran, keutuhan kalimat, overlap, tidak melintasi bab, kelengkapan korpus."],
        ["test_kb_retrieval.py", "Hit@k, MRR, Answer@3, Wilson, AUC, kalibrasi ambang, BM25, RRF, filter pada semua mode, kelengkapan metadata, validitas kueri terhadap korpus."],
        ["test_kb_chromadb.py", "Seluruh chunk terindeks, persistensi setelah dibuka ulang, skor sama dengan cosine eksak, filter metadata, pembangunan ulang idempoten."],
    ], [5.4, 10.6])
    rep.p(args.test_status)

    rep.h1("8. Pembaruan Repositori dan Pembagian Peran")
    rep.story.append(Preformatted("""smart-warehouse-agent/
|-- data/
|   |-- raw/corpus/             <- M3: 18 dokumen + manifest.json
|   |-- processed/              <- corpus_clean/, chunks.jsonl, kb_config.json
|   |-- benchmark/queries.json  <- M3: kueri dev dan test
|   `-- vectorstore/            <- M3: ChromaDB persisten
|-- src/
|   |-- warehouse_search.py, solver.py, data_loader.py   <- M1, M2
|   |-- kb_pipeline.py          <- M3: CLI
|   `-- kb/                     <- M3: modul pipeline
|-- tests/test_kb_*.py          <- M3
|-- results/benchmark_results.json
`-- pyproject.toml, requirements.txt, uv.lock, README.md""", CODE))
    rep.story.append(KeepTogether([Preformatted("""uv sync
uv run pytest tests/ -q
uv run python src/kb_pipeline.py all
uv run python src/kb_pipeline.py search "suhu ruang beku" --kategori "Rantai Dingin\"""", CODE)]))
    rep.p(f"Tautan repositori: {REPO_URL}. Tag rilis: v0.3-milestone3 (versi paket 0.3.0).")
    rep.table("Tabel 8.1 Pembagian peran Milestone 3", [
        ["Anggota", "Peran", "Tanggung Jawab"],
        ["Nicolas J Grace Butarbutar", "Pipeline Engineer &amp; Repository Maintainer", "Modul embedding, ChromaDB, retriever, CLI, dan rilis."],
        ["Indah Triyuni Siahaan", "Corpus &amp; Domain Analyst", "Korpus, kebenaran isi terhadap proses bisnis, dan penyusunan kueri uji."],
        ["Swasti Maristella Sihombing", "Evaluation &amp; Documentation", "Benchmark, pengujian, analisis hasil, dan laporan."],
    ], [5, 4.8, 6.2])

    rep.h1("9. Keterbatasan, Rencana Lanjutan, dan Kesimpulan")
    rep.h2("9.1 Keterbatasan")
    rep.bullets([
        "Korpus bersifat sintetis dan relatif kecil, sehingga skor belum tentu berlaku pada dokumen nyata yang lebih besar dan lebih tidak rapi.",
        "Kueri dan frasa bukti disusun oleh pihak yang sama dengan penulis korpus, sehingga ada risiko bias. Selang kepercayaan juga masih lebar karena jumlah kueri test terbatas.",
        "Ambang tunggal pada cosine tidak dapat membedakan pertanyaan yang satu topik dengan korpus tetapi jawabannya tidak tersedia. Pemeriksaan akhir pada tahap RAG tetap diperlukan.",
        "Answer@3 berbasis pencocokan frasa, sehingga jawaban benar dengan kata lain dapat terhitung gagal.",
        "PDF pada korpus adalah PDF berbasis teks. Hasil pindaian memerlukan OCR yang belum disediakan.",
    ])
    rep.h2("9.2 Rencana Lanjutan")
    rep.bullets([
        "Menghubungkan retriever ke model bahasa besar sebagai RAG dengan sitasi doc_id dan bab, serta jawaban “tidak ditemukan” bila kueri ditolak.",
        "Menambahkan cross-encoder reranker dan pemeriksaan keterjawaban untuk kueri OOD dekat.",
        "Memakai level_akses dan tanggal_berlaku sebagai filter wajib sesuai peran pengguna.",
        "Mengintegrasikan basis pengetahuan dengan modul M1 dan M2, misalnya untuk menjelaskan alasan aturan pada jadwal yang ditolak solver.",
    ])
    rep.h2("9.3 Kesimpulan")
    if rep.analysis.get("kesimpulan"):
        rep.analysis_or_pending("kesimpulan")
    else:
        rep.p(f"Milestone 3 menghasilkan korpus {len(docs)} dokumen yang bersih, pipeline chunking yang menjaga keutuhan kalimat, indeks ChromaDB persisten dengan {len(METADATA_FIELDS)} kolom metadata, dan benchmark yang memisahkan kueri pemilihan dari kueri evaluasi. <font backColor='#fff2a8'>[Kesimpulan kuantitatif ditulis setelah benchmark dijalankan.]</font>")

    rep.story.append(PageBreak())
    rep.h1("Daftar Pustaka")
    for ref in (
        "Cormack, G. V., Clarke, C. L. A., &amp; Büttcher, S. (2009). Reciprocal rank fusion outperforms Condorcet and individual rank learning methods. <i>Proceedings of SIGIR 2009</i>.",
        "Lewis, P., dkk. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. <i>Advances in Neural Information Processing Systems 33</i>.",
        "Malkov, Y. A., &amp; Yashunin, D. A. (2020). Efficient and robust approximate nearest neighbor search using hierarchical navigable small world graphs. <i>IEEE Transactions on Pattern Analysis and Machine Intelligence, 42</i>(4).",
        "Reimers, N., &amp; Gurevych, I. (2019). Sentence-BERT: Sentence embeddings using Siamese BERT-networks. <i>Proceedings of EMNLP-IJCNLP 2019</i>.",
        "Robertson, S., &amp; Zaragoza, H. (2009). The probabilistic relevance framework: BM25 and beyond. <i>Foundations and Trends in Information Retrieval, 3</i>(4).",
        "Peraturan Menteri Ketenagakerjaan Nomor 8 Tahun 2020 tentang Keselamatan dan Kesehatan Kerja Pesawat Angkat dan Pesawat Angkut.",
        "Peraturan Pemerintah Nomor 35 Tahun 2021 tentang Perjanjian Kerja Waktu Tertentu, Alih Daya, Waktu Kerja dan Waktu Istirahat, dan Pemutusan Hubungan Kerja.",
        "Undang-Undang Nomor 13 Tahun 2003 tentang Ketenagakerjaan, sebagaimana diubah melalui Undang-Undang Nomor 6 Tahun 2023 tentang Cipta Kerja.",
    ):
        rep.p(ref, ParagraphStyle("ref", parent=BODY, leftIndent=16, firstLineIndent=-16, fontSize=10, leading=13.5, spaceAfter=5))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "Grup19-Tugas03.pdf")
    parser.add_argument("--results", type=Path, default=RESULTS_PATH)
    parser.add_argument("--analysis", type=Path, default=ROOT / "docs" / "analisis_m3.json")
    parser.add_argument("--workdir", type=Path, default=ROOT / "docs" / "_report_build")
    parser.add_argument("--m12-tests", type=int, default=0)
    parser.add_argument("--kb-tests", type=int, default=55)
    parser.add_argument("--chroma-tests", type=int, default=6)
    parser.add_argument("--test-status", default="<font backColor='#fff2a8'>[Status akhir pytest pada lingkungan dengan ChromaDB asli diisi setelah dijalankan.]</font>")
    args = parser.parse_args()
    args.workdir.mkdir(parents=True, exist_ok=True)
    results = json.loads(args.results.read_text(encoding="utf-8")) if args.results.exists() else None
    analysis = json.loads(args.analysis.read_text(encoding="utf-8")) if args.analysis.exists() else {}
    rep = Report(results, analysis, args.workdir)
    build(rep, args)
    draft = results is None

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT, 8.5)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(2.5 * cm, 1.3 * cm, "Grup 19 – Tugas 3 (Milestone 3) – 10S3001 Kecerdasan Buatan")
        canvas.drawRightString(A4[0] - 2.5 * cm, 1.3 * cm, f"Halaman {doc.page}")
        if draft:
            canvas.setFillColor(colors.HexColor("#a35b00"))
            canvas.drawCentredString(A4[0] / 2, A4[1] - 1.2 * cm, "DRAF – bagian kuning menunggu hasil benchmark asli")
        canvas.restoreState()

    SimpleDocTemplate(str(args.output), pagesize=A4, leftMargin=2.5 * cm, rightMargin=2.5 * cm, topMargin=2.0 * cm, bottomMargin=2.0 * cm,
                      title="Grup19-Tugas03", author="Kelompok 19").build(rep.story, onFirstPage=decorate, onLaterPages=decorate)
    print(args.output)


if __name__ == "__main__":
    main()
