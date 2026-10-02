"""
generate_datasets.py
--------------------
Script pembuat dataset dummy Smart Warehouse Agent dalam format CSV & Excel.

Jalankan dari root repository:
    uv run python data/generate_datasets.py

File yang dihasilkan:
  data/
  ├── raw/
  │   ├── staff_data.csv
  │   ├── items_inventory.csv
  │   ├── orders.csv
  │   └── warehouse_nodes.csv
  └── processed/
      └── smart_warehouse_dataset.xlsx  ← semua sheet dalam 1 file Excel
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

try:
    import openpyxl
    from openpyxl import Workbook
    from openpyxl.styles import (
        Alignment, Border, Font, PatternFill, Side
    )
    from openpyxl.utils import get_column_letter
except ModuleNotFoundError:
    print("[ERROR] openpyxl belum terpasang. Jalankan: uv add openpyxl")
    sys.exit(1)

# ─────────────────────────────────────────────
# Lokasi output
# ─────────────────────────────────────────────
ROOT      = Path(__file__).resolve().parent.parent
RAW_DIR   = ROOT / "data" / "raw"
PROC_DIR  = ROOT / "data" / "processed"
RAW_DIR.mkdir(parents=True, exist_ok=True)
PROC_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# DATA DUMMY
# ══════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────
# 1. STAF GUDANG
# ─────────────────────────────────────────────
STAFF_HEADERS = [
    "id_staf", "nama", "jabatan", "departemen",
    "tanggal_bergabung", "status",
    "hari_libur_senin", "hari_libur_selasa", "hari_libur_rabu",
    "hari_libur_kamis", "hari_libur_jumat", "hari_libur_sabtu",
    "hari_libur_minggu",
    "preferensi_shift", "max_jam_per_minggu", "catatan",
]

STAFF_ROWS = [
    ["S01","Andi Kurniawan",         "Operator Gudang Senior","Operasional","2021-03-15","Aktif", 0,0,0,0,0,0,0,"Pagi, Siang",   40,""],
    ["S02","Budi Santoso",           "Operator Gudang",        "Operasional","2022-07-01","Aktif", 1,1,0,0,0,0,0,"Siang, Malam",  40,"Libur Senin & Selasa"],
    ["S03","Citra Dewi Nainggolan",  "Operator Gudang",        "Operasional","2023-01-10","Aktif", 0,0,0,0,1,0,0,"Pagi",          40,"Tidak tersedia Jumat"],
    ["S04","Dewi Rahayu Sihotang",   "Supervisor Gudang",      "Operasional","2020-09-20","Aktif", 0,0,0,0,0,0,0,"Pagi, Siang",   40,"Diutamakan shift pagi"],
    ["S05","Eko Prasetyo",           "Operator Gudang",        "Operasional","2022-11-05","Aktif", 0,0,0,0,0,0,0,"Malam, Siang",  40,"Bersedia shift malam"],
    ["S06","Fitri Ayu Simbolon",     "Operator Gudang",        "Operasional","2023-06-15","Aktif", 0,0,0,0,0,1,1,"Pagi, Siang",   40,"Tidak tersedia akhir pekan"],
    ["S07","Galih Wibowo Tambunan",  "Operator Forklift",      "Operasional","2021-08-30","Aktif", 0,0,1,0,0,0,0,"Pagi, Malam",   40,"Libur Rabu (pelatihan rutin)"],
    ["S08","Hesti Permata Sinaga",   "Operator Gudang",        "Operasional","2024-02-20","Aktif", 0,0,0,1,0,0,0,"Siang",         40,"Baru bergabung, libur Kamis"],
    ["S09","Ivan Saputra Manurung",  "Operator Gudang",        "Operasional","2023-09-01","Aktif", 0,0,0,0,0,0,0,"Pagi, Siang",   40,""],
    ["S10","Jeni Lestari Hutabarat", "Admin Gudang",           "Administrasi","2022-04-12","Aktif",0,0,0,0,0,1,1,"Pagi",          40,"Hanya shift pagi & hari kerja"],
    ["S11","Kurniadi Simbolon",      "Operator Gudang",        "Operasional","2021-12-01","Aktif", 1,0,0,0,0,0,0,"Siang, Malam",  40,"Libur Senin"],
    ["S12","Linda Sari Nababan",     "QC Inspector",           "Kualitas",   "2022-08-20","Aktif", 0,0,0,0,0,1,1,"Pagi, Siang",   40,"Hanya weekday"],
    ["S13","Muhammad Rizki",         "Operator Forklift",      "Operasional","2020-05-10","Aktif", 0,0,0,0,0,0,0,"Pagi, Malam",   48,"Bersedia lembur s/d 48 jam"],
    ["S14","Nadia Puspita Sari",     "Operator Gudang",        "Operasional","2024-06-01","Aktif", 0,0,0,0,0,0,0,"Siang",         40,"Baru bergabung"],
    ["S15","Oscar Tambunan",         "Kepala Gudang",          "Manajemen",  "2019-01-15","Aktif", 0,0,0,0,0,0,0,"Pagi",          40,"Hanya shift pagi"],
]

# ─────────────────────────────────────────────
# 2. INVENTORI BARANG (SKU)
# ─────────────────────────────────────────────
INVENTORY_HEADERS = [
    "sku", "nama_barang", "kategori", "sub_kategori",
    "berat_kg", "panjang_cm", "lebar_cm", "tinggi_cm",
    "harga_satuan_rp", "turnover", "lokasi_rak",
    "stok_saat_ini", "stok_minimum",
    "cold_storage", "fragile", "tanggal_kadaluarsa",
]

INVENTORY_ROWS = [
    ["SKU-E001","Laptop Gaming 15.6\"",           "Elektronik",         "Komputer",         2.5,  38, 26, 4,  12500000,"lambat", "R01",15, 3, "Tidak","Ya",  ""],
    ["SKU-E002","Smartphone Android 5G",           "Elektronik",         "Handphone",        0.2,  16,  8, 1,   4500000,"cepat",  "R09",60,10, "Tidak","Ya",  ""],
    ["SKU-E003","Headphone Wireless ANC",          "Elektronik",         "Audio",            0.35, 20, 18, 9,   1200000,"sedang", "R01",30, 5, "Tidak","Tidak",""],
    ["SKU-E004","Tablet 10 inch 256GB",            "Elektronik",         "Komputer",         0.55, 25, 17, 1,   3800000,"sedang", "R02",20, 4, "Tidak","Ya",  ""],
    ["SKU-E005","Smart TV 55 inch 4K",             "Elektronik",         "Televisi",         18.0,124, 72, 9,   8900000,"lambat", "R11", 8, 2, "Tidak","Ya",  ""],
    ["SKU-E006","Kulkas 2 Pintu 200L",             "Elektronik",         "Appliances",       48.0, 55, 57,145,  4200000,"lambat", "R12", 5, 1, "Tidak","Tidak",""],
    ["SKU-E007","Mesin Cuci Front Loading 7kg",    "Elektronik",         "Appliances",       62.0, 60, 55, 85,  5800000,"lambat", "R12", 4, 1, "Tidak","Tidak",""],
    ["SKU-P001","Kemeja Batik Pria L",             "Pakaian",            "Atasan Pria",      0.3,  35, 25, 3,    185000,"sedang", "R03",50,10, "Tidak","Tidak",""],
    ["SKU-P002","Celana Jeans Wanita M",           "Pakaian",            "Bawahan Wanita",   0.45, 32, 28, 4,    220000,"cepat",  "R09",80,15, "Tidak","Tidak",""],
    ["SKU-P003","Sepatu Sneakers Unisex 42",       "Pakaian",            "Alas Kaki",        0.7,  32, 20,14,    350000,"cepat",  "R10",45, 8, "Tidak","Tidak",""],
    ["SKU-P004","Jaket Outdoor Waterproof L",      "Pakaian",            "Jaket",            0.9,  40, 30, 5,    480000,"lambat", "R04",25, 5, "Tidak","Tidak",""],
    ["SKU-P005","Kaos Polos Cotton Pria XL",       "Pakaian",            "Atasan Pria",      0.2,  30, 22, 2,     89000,"cepat",  "R09",100,20,"Tidak","Tidak",""],
    ["SKU-M001","Mie Instan Goreng (kardus 40pcs)","Makanan & Minuman",  "Makanan Instan",   4.0,  50, 35,25,     95000,"cepat",  "R05",200,50, "Tidak","Tidak","2027-06-30"],
    ["SKU-M002","Air Mineral 600ml (dus 24pcs)",   "Makanan & Minuman",  "Minuman",          15.0, 45, 30,30,     40000,"cepat",  "R05",300,80, "Tidak","Tidak","2028-01-15"],
    ["SKU-M003","Susu UHT Full Cream 1L (dus 12)","Makanan & Minuman",  "Minuman",          12.5, 40, 28,22,    120000,"sedang", "R15",100,20, "Ya",   "Tidak","2026-11-30"],
    ["SKU-M004","Yogurt Stroberi 150ml (pak 6pcs)","Makanan & Minuman", "Dairy",             0.9,  20, 15, 8,     48000,"cepat",  "R15", 80,25, "Ya",   "Tidak","2026-10-20"],
    ["SKU-M005","Coklat Batangan Premium 100g",    "Makanan & Minuman",  "Snack",            0.1,  16,  8, 2,     32000,"sedang", "R06",150,30, "Tidak","Tidak","2027-03-31"],
    ["SKU-M006","Kopi Sachet (dos 100pcs)",        "Makanan & Minuman",  "Minuman",          1.2,  28, 18,12,     85000,"cepat",  "R06", 90,20, "Tidak","Tidak","2027-09-30"],
    ["SKU-R001","Blender Rumah Tangga 600W",       "Perlengkapan RT",    "Peralatan Dapur",  2.2,  22, 22,38,    350000,"lambat", "R07", 20, 4, "Tidak","Tidak",""],
    ["SKU-R002","Panci Set Stainless 5-in-1",      "Perlengkapan RT",    "Peralatan Dapur",  5.5,  35, 35,40,    275000,"lambat", "R07", 15, 3, "Tidak","Tidak",""],
    ["SKU-R003","Sabun Mandi Batang (1 lusin)",    "Perlengkapan RT",    "Kebersihan",       1.0,  28, 12, 8,     36000,"cepat",  "R10",120,30, "Tidak","Tidak","2028-12-31"],
    ["SKU-R004","Deterjen Bubuk 2kg",              "Perlengkapan RT",    "Kebersihan",       2.1,  28, 10,38,     52000,"cepat",  "R09", 90,20, "Tidak","Tidak",""],
    ["SKU-R005","Vas Bunga Keramik Besar",         "Perlengkapan RT",    "Dekorasi",         1.8,  20, 20,35,    125000,"lambat", "R13", 18, 3, "Tidak","Ya",  ""],
    ["SKU-G001","Cermin Dinding 60x90cm",          "Perlengkapan RT",    "Dekorasi",         3.5,  92, 62, 5,    195000,"lambat", "R13", 12, 2, "Tidak","Ya",  ""],
    ["SKU-G002","Gelas Kristal Set isi 6",         "Perlengkapan RT",    "Peralatan Makan",  1.2,  22, 18,15,    145000,"sedang", "R14", 28, 5, "Tidak","Ya",  ""],
    ["SKU-C001","Daging Sapi Beku 500g",           "Makanan & Minuman",  "Daging Segar",     0.52, 22, 15, 4,     75000,"cepat",  "R16", 60,15, "Ya",   "Tidak","2026-10-31"],
    ["SKU-C002","Ayam Potong Beku 1kg",            "Makanan & Minuman",  "Daging Segar",     1.05, 24, 18, 6,     42000,"cepat",  "R16", 90,25, "Ya",   "Tidak","2026-10-15"],
    ["SKU-C003","Es Krim Vanilla 750ml",           "Makanan & Minuman",  "Frozen Dessert",   0.8,  14, 14,18,     55000,"sedang", "R15", 40,10, "Ya",   "Tidak","2027-02-28"],
    ["SKU-O001","Rak Besi Serbaguna 5 Susun",      "Perlengkapan RT",    "Furnitur",         14.0, 90, 40,180,   320000,"lambat", "R11", 10, 2, "Tidak","Tidak",""],
    ["SKU-O002","Kasur Busa 160x200cm",            "Perlengkapan RT",    "Furnitur",         22.0,200,160, 20,   850000,"lambat", "R12",  6, 1, "Tidak","Tidak",""],
    ["SKU-O003","Meja Kerja Lipat Portable",       "Perlengkapan RT",    "Furnitur",          7.5,100, 50, 10,   420000,"sedang", "R11", 14, 3, "Tidak","Tidak",""],
    ["SKU-O004","Karpet Bulu 150x200cm",           "Perlengkapan RT",    "Dekorasi",          5.0,200,150,  8,   380000,"lambat", "R08", 10, 2, "Tidak","Tidak",""],
]

# ─────────────────────────────────────────────
# 3. PESANAN (ORDERS)
# ─────────────────────────────────────────────
ORDERS_HEADERS = [
    "id_pesanan", "tipe", "tanggal", "waktu",
    "sku", "nama_barang", "jumlah",
    "node_asal", "node_tujuan",
    "biaya_rute_m", "status", "catatan",
]

ORDERS_ROWS = [
    ["ORD-20261001-001","MASUK", "2026-10-01","08:15","SKU-M001","Mie Instan Goreng (kardus 40pcs)",    20,"DOCK_IN","R05",  20.5,"selesai","Pengiriman reguler dari supplier"],
    ["ORD-20261001-002","KELUAR","2026-10-01","09:30","SKU-E002","Smartphone Android 5G",               5, "R09",    "DOCK_OUT",24.0,"selesai","Pesanan online ekspres"],
    ["ORD-20261001-003","KELUAR","2026-10-01","10:00","SKU-P002","Celana Jeans Wanita M",               10,"R09",    "DOCK_OUT",24.0,"selesai","Pesanan grosir toko mitra"],
    ["ORD-20261001-004","MASUK", "2026-10-01","13:45","SKU-C001","Daging Sapi Beku 500g",               30,"DOCK_IN","R16",  27.5,"selesai","Cold chain — prioritas tinggi"],
    ["ORD-20261002-001","KELUAR","2026-10-02","07:50","SKU-M002","Air Mineral 600ml (dus 24pcs)",        50,"R05",    "DOCK_OUT",12.5,"selesai","Restok minimarket mitra"],
    ["ORD-20261002-002","MASUK", "2026-10-02","09:20","SKU-E005","Smart TV 55 inch 4K",                  3,"DOCK_IN","R11",  19.5,"selesai","Oversize — butuh forklift"],
    ["ORD-20261002-003","KELUAR","2026-10-02","11:00","SKU-E001","Laptop Gaming 15.6\"",                  2,"R01",    "DOCK_OUT",15.0,"selesai","Pesanan korporat"],
    ["ORD-20261002-004","KELUAR","2026-10-02","14:30","SKU-M004","Yogurt Stroberi 150ml (pak 6pcs)",    20,"R15",    "DOCK_OUT",10.5,"selesai","Hampir kadaluarsa — prioritas keluar"],
    ["ORD-20261003-001","MASUK", "2026-10-03","08:00","SKU-P003","Sepatu Sneakers Unisex 42",            15,"DOCK_IN","R10",  14.0,"selesai","Supplier baru — cek kualitas di staging"],
    ["ORD-20261003-002","KELUAR","2026-10-03","10:15","SKU-R003","Sabun Mandi Batang (1 lusin)",         30,"R10",    "DOCK_OUT",26.5,"selesai","Pesanan grosir toko kelontong"],
    ["ORD-20261003-003","MASUK", "2026-10-03","13:00","SKU-G001","Cermin Dinding 60x90cm",               5,"DOCK_IN","R13",  23.5,"proses", "Fragile — penanganan hati-hati"],
    ["ORD-20261004-001","KELUAR","2026-10-04","09:00","SKU-C002","Ayam Potong Beku 1kg",                40,"R16",    "DOCK_OUT",10.5,"selesai","Pengiriman harian ke restoran mitra"],
    ["ORD-20261004-002","MASUK", "2026-10-04","10:30","SKU-R004","Deterjen Bubuk 2kg",                  25,"DOCK_IN","R09",  13.5,"selesai","Restok rutin"],
    ["ORD-20261004-003","KELUAR","2026-10-04","15:45","SKU-E003","Headphone Wireless ANC",               8,"R01",    "DOCK_OUT",15.0,"selesai","Pesanan e-commerce"],
    ["ORD-20261005-001","MASUK", "2026-10-05","08:30","SKU-M003","Susu UHT Full Cream 1L (dus 12)",     40,"DOCK_IN","R15",  28.0,"selesai","Cold chain — langsung ke cold storage"],
    ["ORD-20261005-002","KELUAR","2026-10-05","10:00","SKU-P001","Kemeja Batik Pria L",                  12,"R03",    "DOCK_OUT",11.0,"selesai","Pesanan event perusahaan"],
    ["ORD-20261005-003","KELUAR","2026-10-05","14:00","SKU-O001","Rak Besi Serbaguna 5 Susun",           4,"R11",    "DOCK_OUT",20.5,"selesai","Oversize — sewa truk besar"],
    ["ORD-20261006-001","MASUK", "2026-10-06","09:00","SKU-E004","Tablet 10 inch 256GB",                10,"DOCK_IN","R02",  18.0,"menunggu","Belum dijadwalkan tim operasional"],
    ["ORD-20261006-002","KELUAR","2026-10-06","11:30","SKU-M005","Coklat Batangan Premium 100g",         50,"R06",    "DOCK_OUT",14.5,"menunggu","Pesanan hamper Lebaran awal"],
    ["ORD-20261007-001","MASUK", "2026-10-07","10:00","SKU-E006","Kulkas 2 Pintu 200L",                  2,"DOCK_IN","R12",  20.0,"menunggu","Oversize — perlu forklift & 2 operator"],
    ["ORD-20261007-002","KELUAR","2026-10-07","13:00","SKU-P005","Kaos Polos Cotton Pria XL",            25,"R09",    "DOCK_OUT",24.0,"menunggu","Pesanan regular e-commerce"],
    ["ORD-20261007-003","MASUK", "2026-10-07","14:30","SKU-M006","Kopi Sachet (dos 100pcs)",             15,"DOCK_IN","R06",  20.5,"menunggu","Restok mingguan"],
]

# ─────────────────────────────────────────────
# 4. NODE GUDANG (layout ringkas)
# ─────────────────────────────────────────────
NODES_HEADERS = [
    "id_node","label","tipe","koordinat_x","koordinat_y",
    "kapasitas_slot","terisi_slot","keterangan",
]

NODES_ROWS = [
    ["DOCK_IN",  "Pintu Penerimaan Barang",    "dock",      0,  0,  "-","-","Entry point barang masuk"],
    ["DOCK_OUT", "Pintu Pengiriman Barang",     "dock",      0, 10,  "-","-","Exit point barang keluar"],
    ["STAGING",  "Area Staging / QC",           "staging",   1,  0,  "-","-","Pemeriksaan kualitas barang"],
    ["J1",       "Persimpangan Lorong 1A",      "junction",  2,  0,  "-","-",""],
    ["J2",       "Persimpangan Lorong 1B",      "junction",  2,  3,  "-","-",""],
    ["J3",       "Persimpangan Lorong 2A",      "junction",  4,  0,  "-","-",""],
    ["J4",       "Persimpangan Lorong 2B",      "junction",  4,  3,  "-","-",""],
    ["J5",       "Persimpangan Lorong 3A",      "junction",  6,  0,  "-","-",""],
    ["J6",       "Persimpangan Lorong 3B",      "junction",  6,  3,  "-","-",""],
    ["J7",       "Persimpangan Lorong 4A",      "junction",  8,  0,  "-","-",""],
    ["J8",       "Persimpangan Lorong 4B",      "junction",  8,  3,  "-","-",""],
    ["R01",      "Rak A1 — Elektronik",         "rack",      3,  1,  50, 45,"SKU-E001, SKU-E003"],
    ["R02",      "Rak A2 — Elektronik",         "rack",      3,  2,  50, 20,"SKU-E004"],
    ["R03",      "Rak B1 — Pakaian",            "rack",      5,  1,  60, 50,"SKU-P001"],
    ["R04",      "Rak B2 — Pakaian",            "rack",      5,  2,  60, 25,"SKU-P004"],
    ["R05",      "Rak C1 — Makanan & Minuman",  "rack",      7,  1,  80, 75,"SKU-M001, SKU-M002"],
    ["R06",      "Rak C2 — Makanan & Minuman",  "rack",      7,  2,  80, 60,"SKU-M005, SKU-M006"],
    ["R07",      "Rak D1 — Perlengkapan RT",    "rack",      9,  1,  40, 35,"SKU-R001, SKU-R002"],
    ["R08",      "Rak D2 — Perlengkapan RT",    "rack",      9,  2,  40, 10,"SKU-O004"],
    ["R09",      "Rak E1 — Fast-Moving",        "rack",      3,  4, 100, 85,"SKU-E002, SKU-P002, SKU-P005, SKU-R004"],
    ["R10",      "Rak E2 — Fast-Moving",        "rack",      3,  5, 100, 70,"SKU-P003, SKU-R003"],
    ["R11",      "Rak F1 — Oversize",           "rack",      5,  4,  20, 14,"SKU-E005, SKU-O001, SKU-O003"],
    ["R12",      "Rak F2 — Oversize",           "rack",      5,  5,  20, 15,"SKU-E006, SKU-E007, SKU-O002"],
    ["R13",      "Rak G1 — Fragile",            "rack",      7,  4,  30, 18,"SKU-R005, SKU-G001"],
    ["R14",      "Rak G2 — Fragile",            "rack",      7,  5,  30, 28,"SKU-G002"],
    ["R15",      "Rak H1 — Cold Storage",       "rack_cold", 9,  4,  40, 38,"SKU-M003, SKU-M004, SKU-C003"],
    ["R16",      "Rak H2 — Cold Storage",       "rack_cold", 9,  5,  40, 35,"SKU-C001, SKU-C002"],
]


# ══════════════════════════════════════════════════════════════════════════════
# WRITER — CSV
# ══════════════════════════════════════════════════════════════════════════════

def write_csv(path: Path, headers: list, rows: list) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    print(f"  [OK] CSV  -> {path.relative_to(ROOT)}")


# ══════════════════════════════════════════════════════════════════════════════
# WRITER — Excel (dengan styling profesional)
# ══════════════════════════════════════════════════════════════════════════════

# Palet warna per sheet
SHEET_COLORS = {
    "Staf Gudang":       {"header_fill": "1B4F72", "alt_fill": "D6EAF8"},
    "Inventori Barang":  {"header_fill": "145A32", "alt_fill": "D5F5E3"},
    "Pesanan":           {"header_fill": "6E2F1A", "alt_fill": "FDEBD0"},
    "Node Gudang":       {"header_fill": "4A235A", "alt_fill": "E8DAEF"},
    "Ringkasan":         {"header_fill": "212F3C", "alt_fill": "D5D8DC"},
}

THIN = Side(style="thin", color="CCCCCC")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _style_header_row(ws, row_num: int, ncols: int, hex_color: str) -> None:
    fill = PatternFill("solid", fgColor=hex_color)
    for col in range(1, ncols + 1):
        cell = ws.cell(row=row_num, column=col)
        cell.fill = fill
        cell.font = Font(bold=True, color="FFFFFF", size=10)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER


def _style_data_row(ws, row_num: int, ncols: int, alt_fill_hex: str, is_alt: bool) -> None:
    fill_color = alt_fill_hex if is_alt else "FFFFFF"
    fill = PatternFill("solid", fgColor=fill_color)
    for col in range(1, ncols + 1):
        cell = ws.cell(row=row_num, column=col)
        cell.fill = fill
        cell.alignment = Alignment(vertical="center", wrap_text=False)
        cell.border = BORDER
        cell.font = Font(size=9)


def _auto_column_width(ws, min_w: int = 10, max_w: int = 40) -> None:
    for col_cells in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col_cells[0].column)
        for cell in col_cells:
            try:
                max_len = max(max_len, len(str(cell.value or "")))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max(max_len + 2, min_w), max_w)


def _freeze_and_filter(ws, freeze_cell: str = "A2") -> None:
    ws.freeze_panes = freeze_cell
    ws.auto_filter.ref = ws.dimensions


def add_sheet(wb: Workbook, sheet_name: str, headers: list, rows: list) -> None:
    colors = SHEET_COLORS.get(sheet_name, {"header_fill": "333333", "alt_fill": "F5F5F5"})
    ws = wb.create_sheet(title=sheet_name)
    ws.row_dimensions[1].height = 30

    # Header
    ws.append(headers)
    _style_header_row(ws, 1, len(headers), colors["header_fill"])

    # Data rows
    for i, row in enumerate(rows, start=2):
        ws.append(row)
        _style_data_row(ws, i, len(headers), colors["alt_fill"], is_alt=(i % 2 == 0))

    _auto_column_width(ws)
    _freeze_and_filter(ws)
    print(f"  [OK] Sheet -> '{sheet_name}' ({len(rows)} baris)")


def add_summary_sheet(wb: Workbook) -> None:
    """Tambahkan sheet Ringkasan sebagai halaman depan Excel."""
    ws = wb.create_sheet(title="Ringkasan", index=0)
    colors = SHEET_COLORS["Ringkasan"]

    # Judul utama
    ws.merge_cells("A1:F1")
    title_cell = ws["A1"]
    title_cell.value = "Smart Warehouse Agent — Dataset Dummy"
    title_cell.font = Font(bold=True, size=16, color="FFFFFF")
    title_cell.fill = PatternFill("solid", fgColor=colors["header_fill"])
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 40

    ws.merge_cells("A2:F2")
    sub_cell = ws["A2"]
    sub_cell.value = "Gudang Nusantara Logistik — Cabang Medan  |  Periode: Oktober 2026"
    sub_cell.font = Font(italic=True, size=10, color="555555")
    sub_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20

    # Tabel ringkasan
    ws.append([])  # baris kosong
    headers_sum = ["Sheet", "Deskripsi", "Jumlah Baris", "Kolom Utama"]
    ws.append(headers_sum)
    _style_header_row(ws, 4, 4, colors["header_fill"])

    summary_rows = [
        ["Staf Gudang",      "Data 15 staf aktif beserta jabatan, jadwal libur & preferensi shift",  15, "id_staf, nama, jabatan, hari_libur_*, preferensi_shift"],
        ["Inventori Barang", "Katalog 32 SKU dari 5 kategori utama + atribut fisik & lokasi rak",    32, "sku, nama_barang, kategori, turnover, lokasi_rak, stok"],
        ["Pesanan",          "22 pesanan MASUK/KELUAR selama 1 minggu + rute & status",              22, "id_pesanan, tipe, sku, node_asal, node_tujuan, biaya_rute_m"],
        ["Node Gudang",      "27 node denah gudang (dock, staging, junction, rack)",                  27, "id_node, tipe, koordinat_x, koordinat_y, kapasitas_slot"],
    ]
    for i, row in enumerate(summary_rows, start=5):
        ws.append(row)
        _style_data_row(ws, i, 4, colors["alt_fill"], is_alt=(i % 2 == 0))

    # Catatan penggunaan
    ws.append([])
    ws.append(["Catatan Penggunaan"])
    ws.cell(row=10, column=1).font = Font(bold=True, size=10)
    notes = [
        ["→ Sheet 'Staf Gudang'",      "Dipakai oleh solver.py (build_shift_scheduling_csp) untuk CSP Scheduler"],
        ["→ Sheet 'Node Gudang'",      "Dipakai oleh warehouse_search.py (UCS & A*) sebagai graph berbobot"],
        ["→ Sheet 'Inventori Barang'", "Referensi SKU untuk modul put-away & slotting (Milestone 3+)"],
        ["→ Sheet 'Pesanan'",          "Log transaksi harian untuk analisis rute & optimasi throughput"],
    ]
    for i, note_row in enumerate(notes, start=11):
        ws.append(note_row)
        ws.cell(row=i, column=1).font = Font(bold=True, color="1B4F72", size=9)
        ws.cell(row=i, column=2).font = Font(size=9, color="333333")

    _auto_column_width(ws, min_w=18, max_w=70)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print("=" * 62)
    print("  Smart Warehouse Agent -- Dataset Generator")
    print("=" * 62)

    # -- CSV --
    print("\n[CSV] Membuat file CSV ...")
    write_csv(RAW_DIR / "staff_data.csv",       STAFF_HEADERS,     STAFF_ROWS)
    write_csv(RAW_DIR / "items_inventory.csv",  INVENTORY_HEADERS, INVENTORY_ROWS)
    write_csv(RAW_DIR / "orders.csv",           ORDERS_HEADERS,    ORDERS_ROWS)
    write_csv(RAW_DIR / "warehouse_nodes.csv",  NODES_HEADERS,     NODES_ROWS)

    # -- Excel --
    print("\n[XLSX] Membuat file Excel ...")
    wb = Workbook()
    # Hapus sheet default kosong
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    add_summary_sheet(wb)
    add_sheet(wb, "Staf Gudang",      STAFF_HEADERS,     STAFF_ROWS)
    add_sheet(wb, "Inventori Barang", INVENTORY_HEADERS, INVENTORY_ROWS)
    add_sheet(wb, "Pesanan",          ORDERS_HEADERS,    ORDERS_ROWS)
    add_sheet(wb, "Node Gudang",      NODES_HEADERS,     NODES_ROWS)

    excel_path = PROC_DIR / "smart_warehouse_dataset.xlsx"
    wb.save(excel_path)
    print(f"  [OK] Excel -> {excel_path.relative_to(ROOT)}")

    # -- Ringkasan akhir --
    print(f"\n{'=' * 62}")
    print("  Dataset berhasil dibuat!")
    print(f"{'=' * 62}")
    print(f"\n  data/raw/")
    print(f"     +-- staff_data.csv         ({len(STAFF_ROWS)} baris)")
    print(f"     +-- items_inventory.csv    ({len(INVENTORY_ROWS)} baris)")
    print(f"     +-- orders.csv             ({len(ORDERS_ROWS)} baris)")
    print(f"     +-- warehouse_nodes.csv    ({len(NODES_ROWS)} baris)")
    print(f"\n  data/processed/")
    print(f"     +-- smart_warehouse_dataset.xlsx  (5 sheet)")
    print()


if __name__ == "__main__":
    main()
