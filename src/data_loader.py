"""
data_loader.py
--------------
Modul pemuat dataset dummy untuk Smart Warehouse Agent.

Memuat file JSON dari data/raw/ dan mengonversinya ke format
yang langsung bisa dipakai oleh:
  - warehouse_search.py  → Graph & Coordinates
  - solver.py            → WarehouseCSP via build_shift_scheduling_csp()

Struktur file dataset:
  data/raw/warehouse_layout.json   → denah gudang (nodes & edges)
  data/raw/staff_data.json         → data staf & konfigurasi shift
  data/raw/items_inventory.json    → data inventori SKU
  data/raw/orders.json             → data pesanan inbound/outbound

Cara pakai:
    from src.data_loader import (
        load_warehouse_graph,
        load_staff_for_csp,
        load_inventory,
        load_orders,
        print_dataset_summary,
    )

Atau jalankan langsung untuk melihat ringkasan dataset:
    uv run python src/data_loader.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Tipe alias (sama dengan yang dipakai warehouse_search.py)
# ---------------------------------------------------------------------------
Graph       = Dict[str, List[Tuple[str, float]]]
Coordinates = Dict[str, Tuple[float, float]]

# ---------------------------------------------------------------------------
# Lokasi dataset
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent   # root repo
_RAW  = _ROOT / "data" / "raw"

LAYOUT_FILE    = _RAW / "warehouse_layout.json"
STAFF_FILE     = _RAW / "staff_data.json"
INVENTORY_FILE = _RAW / "items_inventory.json"
ORDERS_FILE    = _RAW / "orders.json"


# ---------------------------------------------------------------------------
# Helper internal
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Any:
    """Muat file JSON; raise FileNotFoundError jika tidak ditemukan."""
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset tidak ditemukan: {path}\n"
            f"Pastikan file ada di direktori data/raw/."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 1. Warehouse Graph & Coordinates  (untuk warehouse_search.py)
# ---------------------------------------------------------------------------

def load_warehouse_graph(
    path: Optional[Path] = None,
) -> Tuple[Graph, Coordinates]:
    """
    Muat denah gudang dari warehouse_layout.json dan kembalikan sebagai
    (Graph, Coordinates) yang langsung bisa dipakai oleh UCS / A*.

    Parameters
    ----------
    path : opsional; gunakan LAYOUT_FILE jika None.

    Returns
    -------
    graph       : Dict[node_id, List[(neighbor_id, weight)]]
    coordinates : Dict[node_id, (x, y)]
    """
    data: Dict[str, Any] = _load_json(path or LAYOUT_FILE)

    coordinates: Coordinates = {
        node["id"]: (float(node["x"]), float(node["y"]))
        for node in data["nodes"]
    }

    graph: Graph = {node["id"]: [] for node in data["nodes"]}
    for edge in data["edges"]:
        graph[edge["from"]].append((edge["to"], float(edge["bobot"])))

    return graph, coordinates


def get_all_rack_ids(path: Optional[Path] = None) -> List[str]:
    """Kembalikan daftar ID semua node bertipe 'rack' atau 'rack_cold'."""
    data: Dict[str, Any] = _load_json(path or LAYOUT_FILE)
    return [
        n["id"] for n in data["nodes"]
        if n.get("tipe", "").startswith("rack")
    ]


# ---------------------------------------------------------------------------
# 2. Staff Data  (untuk solver.py)
# ---------------------------------------------------------------------------

def load_staff_for_csp(
    path: Optional[Path] = None,
) -> Tuple[List[str], Dict[str, Set[int]], int, int]:
    """
    Muat data staf dari staff_data.json dan kembalikan parameter siap
    dipakai oleh build_shift_scheduling_csp().

    Returns
    -------
    staff_names         : List[str]  — nama lengkap staf
    unavailable         : Dict[str, Set[int]]  — {nama: {hari_libur, ...}}
    n_days              : int — jumlah hari kerja yang dijadwalkan
    max_hours_per_week  : int
    """
    data: Dict[str, Any] = _load_json(path or STAFF_FILE)

    staf_aktif = [s for s in data["staf"] if s["status"] == "aktif"]

    staff_names: List[str] = [s["nama"] for s in staf_aktif]

    unavailable: Dict[str, Set[int]] = {
        s["nama"]: set(s.get("hari_tidak_tersedia", []))
        for s in staf_aktif
    }

    cfg = data.get("konfigurasi_penjadwalan", {})
    n_days             = int(cfg.get("n_hari", 5))
    max_hours_per_week = int(cfg.get("maks_jam_per_minggu", 40))

    return staff_names, unavailable, n_days, max_hours_per_week


def load_staff_raw(path: Optional[Path] = None) -> Dict[str, Any]:
    """Muat seluruh isi staff_data.json mentah (dict)."""
    return _load_json(path or STAFF_FILE)


# ---------------------------------------------------------------------------
# 3. Inventory  (untuk modul Milestone berikutnya)
# ---------------------------------------------------------------------------

def load_inventory(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Muat daftar SKU dari items_inventory.json.

    Returns
    -------
    List of dicts, satu dict per SKU.
    """
    data: Dict[str, Any] = _load_json(path or INVENTORY_FILE)
    return data.get("items", [])


def get_fast_moving_items(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Filter item dengan turnover == 'fast'."""
    return [i for i in load_inventory(path) if i.get("turnover") == "fast"]


def get_cold_storage_items(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Filter item yang membutuhkan cold storage."""
    return [i for i in load_inventory(path) if i.get("membutuhkan_cold_storage")]


def get_items_by_rack(
    rack_id: str,
    path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Filter item yang disimpan di rak tertentu."""
    return [i for i in load_inventory(path) if i.get("lokasi_rak") == rack_id]


# ---------------------------------------------------------------------------
# 4. Orders  (untuk modul Milestone berikutnya)
# ---------------------------------------------------------------------------

def load_orders(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Muat daftar pesanan dari orders.json.

    Returns
    -------
    List of dicts, satu dict per pesanan.
    """
    data: Dict[str, Any] = _load_json(path or ORDERS_FILE)
    return data.get("pesanan", [])


def get_pending_orders(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Filter pesanan yang masih menunggu atau dalam proses."""
    return [
        o for o in load_orders(path)
        if o.get("status") in ("menunggu", "proses")
    ]


def get_inbound_orders(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Filter pesanan tipe INBOUND."""
    return [o for o in load_orders(path) if o.get("tipe") == "INBOUND"]


def get_outbound_orders(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Filter pesanan tipe OUTBOUND."""
    return [o for o in load_orders(path) if o.get("tipe") == "OUTBOUND"]


# ---------------------------------------------------------------------------
# 5. Ringkasan dataset  (helper tampilan)
# ---------------------------------------------------------------------------

def print_dataset_summary() -> None:  # pragma: no cover
    """Cetak ringkasan semua dataset yang tersedia ke stdout."""
    sep = "=" * 62

    print(sep)
    print("  Smart Warehouse Agent -- Ringkasan Dataset Dummy")
    print(sep)

    # --- Warehouse Graph ---
    try:
        graph, coords = load_warehouse_graph()
        n_nodes = len(coords)
        n_edges = sum(len(v) for v in graph.values())
        print(f"\n[Denah Gudang]  {LAYOUT_FILE.name}")
        print(f"    Node  : {n_nodes}")
        print(f"    Edge  : {n_edges} (directed)")
        node_types: Dict[str, int] = {}
        raw_layout = _load_json(LAYOUT_FILE)
        for n in raw_layout["nodes"]:
            t = n.get("tipe", "?")
            node_types[t] = node_types.get(t, 0) + 1
        for tipe, cnt in sorted(node_types.items()):
            print(f"           {tipe:<15}: {cnt} node")
    except FileNotFoundError as e:
        print(f"\n[!] {e}")

    # --- Staff ---
    try:
        staff_names, unavailable, n_days, max_hours = load_staff_for_csp()
        print(f"\n[Data Staf]  {STAFF_FILE.name}")
        print(f"    Jumlah staf aktif    : {len(staff_names)}")
        print(f"    Hari dijadwalkan     : {n_days}")
        print(f"    Maks jam/minggu      : {max_hours}")
        libur = {n: d for n, d in unavailable.items() if d}
        if libur:
            hari = ["Sen","Sel","Rab","Kam","Jum","Sab","Min"]
            print("    Staf dengan hari libur:")
            for nama, hari_set in libur.items():
                label = ", ".join(hari[d] for d in sorted(hari_set) if d < 7)
                print(f"      - {nama:<30} -> libur: {label}")
    except FileNotFoundError as e:
        print(f"\n[!] {e}")

    # --- Inventory ---
    try:
        items = load_inventory()
        kategoris: Dict[str, int] = {}
        for it in items:
            k = it.get("kategori", "?")
            kategoris[k] = kategoris.get(k, 0) + 1
        fast  = len(get_fast_moving_items())
        cold  = len(get_cold_storage_items())
        print(f"\n[Inventori SKU]  {INVENTORY_FILE.name}")
        print(f"    Total SKU            : {len(items)}")
        print(f"    Fast-moving          : {fast}")
        print(f"    Butuh cold storage   : {cold}")
        print("    Per kategori:")
        for kat, cnt in sorted(kategoris.items()):
            print(f"      - {kat:<30}: {cnt} SKU")
    except FileNotFoundError as e:
        print(f"\n[!] {e}")

    # --- Orders ---
    try:
        orders  = load_orders()
        inbound  = len(get_inbound_orders())
        outbound = len(get_outbound_orders())
        pending  = len(get_pending_orders())
        total_cost = sum(o.get("biaya_rute", 0) for o in orders)
        print(f"\n[Pesanan 1 minggu]  {ORDERS_FILE.name}")
        print(f"    Total pesanan        : {len(orders)}")
        print(f"    INBOUND              : {inbound}")
        print(f"    OUTBOUND             : {outbound}")
        print(f"    Masih pending/proses : {pending}")
        print(f"    Total biaya rute     : {total_cost:.1f} m")
    except FileNotFoundError as e:
        print(f"\n[!] {e}")

    print(f"\n{sep}")


# ---------------------------------------------------------------------------
# Demo / Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    print_dataset_summary()

    # Contoh: integrasikan dataset ke solver
    print("\n[Demo] Memuat data staf ke solver.py ...")
    try:
        from solver import build_shift_scheduling_csp, ShiftType

        staff_names, unavailable, n_days, max_hours = load_staff_for_csp()
        print(f"  Staf  : {staff_names}")
        print(f"  n_days: {n_days}  |  max_hours: {max_hours}")

        csp = build_shift_scheduling_csp(
            staff=staff_names,
            n_days=n_days,
            slots_per_shift=1,    # 1 staf per shift (dataset mendukung 2)
            unavailable=unavailable,
            max_hours_per_week=max_hours,
        )
        solution, stats = csp.solve()
        if solution:
            print(f"  [OK] Solusi ditemukan! "
                  f"({stats['nodes_explored']} nodes, "
                  f"{stats['elapsed_s']*1000:.1f} ms)")
        else:
            print("  [GAGAL] Tidak ada solusi ditemukan.")
    except ImportError:
        print("  (Jalankan dari direktori src/ atau tambahkan src/ ke PYTHONPATH)")

    # Contoh: integrasikan dataset ke warehouse_search
    print("\n[Demo] Memuat denah gudang ke warehouse_search.py ...")
    try:
        from warehouse_search import uniform_cost_search, a_star_search

        graph, coords = load_warehouse_graph()
        start, goal = "DOCK_IN", "R16"
        ucs  = uniform_cost_search(graph, start, goal)
        astar = a_star_search(graph, start, goal, coords)
        print(f"  UCS  : cost={ucs.cost:.1f}, nodes={ucs.nodes_expanded}")
        print(f"  A*   : cost={astar.cost:.1f}, nodes={astar.nodes_expanded}")
    except ImportError:
        print("  (Jalankan dari direktori src/ atau tambahkan src/ ke PYTHONPATH)")
