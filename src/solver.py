"""
solver.py
---------
Milestone 2 – Smart Warehouse Agent
Modul Solver CSP (Constraint Satisfaction Problem) untuk Penjadwalan Shift Staf Gudang.

Pemodelan Matematis Formal
==========================

  Variabel  X = { X_{d,t,k} | d ∈ Days, t ∈ ShiftType, k ∈ {1..slots_per_shift} }
              Setiap X_{d,t,k} mewakili satu kursi staf pada hari d, tipe-shift t, slot ke-k.

  Domain    D_{d,t,k} ⊆ Staff
              Himpunan staf yang tersedia pada slot tersebut (belum tentu seluruh Staff).

  Batasan   C = { C1, C2, C3, C4 }
    C1 (AllDiff/hari)  : ∀ d, ∀ i ≠ j dengan slot i,j pada hari d → X_i ≠ X_j
                         (satu staf tidak boleh mengisi lebih dari satu slot pada hari yang sama)
    C2 (Istirahat)     : ∀ staf s — jika s bekerja NIGHT pada hari d,
                         maka s TIDAK BOLEH bekerja MORNING pada hari d+1
                         (min. 8 jam istirahat antar shift)
    C3 (Kapasitas)     : ∀ (d,t) — jumlah slot (d,t) ∈ [min_cap, max_cap]
                         (terpenuhi secara struktural melalui jumlah variabel per shift)
    C4 (Batas Jam)     : ∀ s ∈ Staff — Σ_{X=s} jam(shift) ≤ max_hours_per_week
                         (total jam kerja staf s dalam satu minggu ≤ batas)

Algoritma
=========
  Fase 1 — AC-3 (Arc Consistency 3)
    Untuk setiap arc (Xi, Xj): hapus nilai di D(Xi) yang tidak punya nilai legal di D(Xj).
    Jika suatu domain kosong → masalah tidak mungkin (infeasible).

  Fase 2 — Backtracking + MRV + LCV + Forward Checking
    MRV (Minimum Remaining Values): pilih variabel belum-assigned dengan domain terkecil.
    LCV (Least Constraining Value): urutkan nilai yang paling sedikit memangkas domain tetangga.
    Forward Checking: setiap kali assign, langsung pangkas domain tetangga yang belum di-assign.

Jalankan langsung:
    python src/solver.py
atau via uv:
    uv run python src/solver.py
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Konstanta & Enum
# ---------------------------------------------------------------------------

class ShiftType(Enum):
    """Tipe shift yang berlaku di gudang."""
    MORNING   = "M"   # 06:00 – 14:00
    AFTERNOON = "A"   # 14:00 – 22:00
    NIGHT     = "N"   # 22:00 – 06:00

#: Jam kerja per shift (dipakai untuk menghitung C4)
SHIFT_HOURS: Dict[ShiftType, int] = {
    ShiftType.MORNING:   8,
    ShiftType.AFTERNOON: 8,
    ShiftType.NIGHT:     8,
}

#: Nama hari kerja (0 = Senin)
DAY_NAMES = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]


# ---------------------------------------------------------------------------
# Representasi Variabel
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ShiftSlot:
    """
    Satu kursi/slot staf yang perlu diisi.
    Merupakan variabel CSP: nilainya adalah nama staf yang ditugaskan.

    Attributes
    ----------
    day   : indeks hari (0 = Senin, ..., 6 = Minggu)
    shift : tipe shift (MORNING / AFTERNOON / NIGHT)
    slot  : indeks slot dalam shift tersebut (untuk kasus multi-staf per shift)
    """
    day:   int
    shift: ShiftType
    slot:  int = 0

    def __str__(self) -> str:  # pragma: no cover
        day_label = DAY_NAMES[self.day] if self.day < len(DAY_NAMES) else f"D{self.day}"
        return f"{day_label}-{self.shift.value}{self.slot + 1}"

    def __repr__(self) -> str:  # pragma: no cover
        return str(self)


#: Tipe assignment lengkap: ShiftSlot → nama staf
Assignment = Dict[ShiftSlot, str]


# ---------------------------------------------------------------------------
# Kelas CSP Utama
# ---------------------------------------------------------------------------

class WarehouseCSP:
    """
    CSP Penjadwalan Shift Staf Gudang.

    Memodelkan:
      - Variabel : setiap ShiftSlot yang perlu diisi
      - Domain   : staf yang boleh mengisi slot tersebut
      - Batasan  : C1 (AllDiff/hari), C2 (Istirahat), C4 (Batas Jam)

    Solver menjalankan AC-3 (propagasi batasan) lalu Backtracking MRV+LCV.
    """

    def __init__(
        self,
        variables: List[ShiftSlot],
        domains: Dict[ShiftSlot, Set[str]],
        staff_list: List[str],
        max_hours_per_week: int = 40,
    ) -> None:
        if not variables:
            raise ValueError("Daftar variabel tidak boleh kosong.")

        self.variables:           List[ShiftSlot]         = list(variables)
        self.domains:             Dict[ShiftSlot, Set[str]] = {v: set(d) for v, d in domains.items()}
        self.staff_list:          List[str]               = list(staff_list)
        self.max_hours_per_week:  int                     = max_hours_per_week

        # Statistik terakhir setelah solve()
        self.stats: Dict[str, Any] = {}
        self._nodes_explored: int = 0

        # Pra-hitung tetangga untuk AC-3 & forward checking
        self._neighbors: Dict[ShiftSlot, List[ShiftSlot]] = self._build_neighbors()

    # ------------------------------------------------------------------
    # Pra-hitung struktur batasan
    # ------------------------------------------------------------------

    def _build_neighbors(self) -> Dict[ShiftSlot, List[ShiftSlot]]:
        """Dua variabel adalah tetangga jika ada batasan biner di antara keduanya."""
        neighbors: Dict[ShiftSlot, List[ShiftSlot]] = {v: [] for v in self.variables}
        for i, vi in enumerate(self.variables):
            for j, vj in enumerate(self.variables):
                if i >= j:
                    continue
                if self._has_binary_constraint(vi, vj):
                    neighbors[vi].append(vj)
                    neighbors[vj].append(vi)
        return neighbors

    @staticmethod
    def _has_binary_constraint(vi: ShiftSlot, vj: ShiftSlot) -> bool:
        """Kembalikan True jika vi dan vj berbagi setidaknya satu batasan biner."""
        # C1: Slot berbeda pada hari yang sama
        if vi.day == vj.day:
            return True
        # C2: Night hari d → Morning hari d+1 tidak boleh staf yang sama
        if (vi.shift is ShiftType.NIGHT and vj.shift is ShiftType.MORNING
                and vj.day == vi.day + 1):
            return True
        if (vj.shift is ShiftType.NIGHT and vi.shift is ShiftType.MORNING
                and vi.day == vj.day + 1):
            return True
        return False

    def _binary_ok(self, vi: ShiftSlot, si: str, vj: ShiftSlot, sj: str) -> bool:
        """
        Periksa apakah assign si → vi dan sj → vj tidak melanggar batasan biner.

        Batasan yang dicek:
          C1: Tidak boleh staf yang sama pada hari yang sama
          C2: Tidak boleh staf yang sama pada Night-hari-d dan Morning-hari-(d+1)
        """
        if si == sj:
            # C1
            if vi.day == vj.day:
                return False
            # C2
            if (vi.shift is ShiftType.NIGHT and vj.shift is ShiftType.MORNING
                    and vj.day == vi.day + 1):
                return False
            if (vj.shift is ShiftType.NIGHT and vi.shift is ShiftType.MORNING
                    and vi.day == vj.day + 1):
                return False
        return True

    # ------------------------------------------------------------------
    # AC-3 (Arc Consistency 3)
    # ------------------------------------------------------------------

    def arc_consistency_ac3(self) -> bool:
        """
        Terapkan Arc Consistency (AC-3) pada seluruh arc.

        Memangkas domain secara in-place.
        Kembalikan False jika ada domain yang kosong (masalah infeasible).

        Kompleksitas: O(e · d²) di mana e = jumlah arc, d = ukuran domain terbesar.
        """
        # Antrian berisi semua arc (Xi, Xj) dan baliknya (Xj, Xi)
        queue: deque[Tuple[ShiftSlot, ShiftSlot]] = deque()
        for vi in self.variables:
            for vj in self._neighbors[vi]:
                queue.append((vi, vj))

        while queue:
            xi, xj = queue.popleft()
            if self._revise(xi, xj):
                if not self.domains[xi]:
                    return False  # domain kosong → infeasible
                # Tambahkan kembali arc tetangga ke antrian
                for xk in self._neighbors[xi]:
                    if xk is not xj:
                        queue.append((xk, xi))
        return True

    def _revise(self, xi: ShiftSlot, xj: ShiftSlot) -> bool:
        """
        Hapus nilai dari domain(xi) yang tidak memiliki nilai legal di domain(xj).
        Kembalikan True jika domain(xi) berubah.
        """
        revised = False
        for si in list(self.domains[xi]):
            # Apakah ada setidaknya satu sj ∈ D(xj) yang konsisten dengan si?
            if not any(self._binary_ok(xi, si, xj, sj) for sj in self.domains[xj]):
                self.domains[xi].discard(si)
                revised = True
        return revised

    # ------------------------------------------------------------------
    # Backtracking + MRV + LCV + Forward Checking
    # ------------------------------------------------------------------

    def _hours_assigned(self, staff: str, assignment: Assignment) -> int:
        """Hitung total jam kerja staf dalam assignment saat ini."""
        return sum(
            SHIFT_HOURS[var.shift]
            for var, assigned_staff in assignment.items()
            if assigned_staff == staff
        )

    def _is_consistent(self, var: ShiftSlot, value: str, assignment: Assignment) -> bool:
        """
        Periksa apakah assign value ke var konsisten dengan assignment yang ada.

        Batasan yang dicek:
          C4: Batas jam kerja per minggu (unary atas assignment saat ini)
          C1/C2: Batasan biner dengan variabel yang sudah di-assign
        """
        # C4: Batas jam kerja
        used = self._hours_assigned(value, assignment) + SHIFT_HOURS[var.shift]
        if used > self.max_hours_per_week:
            return False

        # C1, C2: Batasan biner dengan tetangga yang sudah di-assign
        for neighbor in self._neighbors[var]:
            if neighbor in assignment:
                if not self._binary_ok(var, value, neighbor, assignment[neighbor]):
                    return False
        return True

    def _select_unassigned_mrv(self, assignment: Assignment) -> Optional[ShiftSlot]:
        """
        MRV Heuristic: pilih variabel belum-assign dengan domain tersisa terkecil.
        Tie-breaking: pilih variabel dengan jumlah tetangga terbanyak (degree heuristic).
        """
        unassigned = [v for v in self.variables if v not in assignment]
        if not unassigned:
            return None
        return min(
            unassigned,
            key=lambda v: (len(self.domains[v]), -len(self._neighbors[v])),
        )

    def _order_values_lcv(self, var: ShiftSlot, assignment: Assignment) -> List[str]:
        """
        LCV Heuristic: urutkan nilai domain dengan yang paling sedikit memangkas
        domain tetangga yang belum di-assign.
        """
        def ruled_out(value: str) -> int:
            total = 0
            for nb in self._neighbors[var]:
                if nb not in assignment:
                    for nval in self.domains[nb]:
                        if not self._binary_ok(var, value, nb, nval):
                            total += 1
            return total

        return sorted(self.domains[var], key=ruled_out)

    def _forward_check(
        self,
        var: ShiftSlot,
        value: str,
        assignment: Assignment,
        saved_domains: Dict[ShiftSlot, Set[str]],
    ) -> bool:
        """
        Forward Checking: pangkas domain tetangga belum-assign setelah meng-assign value ke var.
        Kembalikan False jika ada domain tetangga yang menjadi kosong.
        Modifikasi self.domains in-place; saved_domains dipakai untuk rollback.
        """
        for neighbor in self._neighbors[var]:
            if neighbor not in assignment:
                for nval in list(self.domains[neighbor]):
                    if not self._binary_ok(var, value, neighbor, nval):
                        self.domains[neighbor].discard(nval)
                if not self.domains[neighbor]:
                    return False  # domain kosong → dead end
        return True

    def _backtrack(self, assignment: Assignment) -> Optional[Assignment]:
        """Rekursi backtracking: kembalikan assignment lengkap atau None."""
        if len(assignment) == len(self.variables):
            return dict(assignment)  # solusi ditemukan

        var = self._select_unassigned_mrv(assignment)
        if var is None:
            return None  # seharusnya tidak terjadi

        self._nodes_explored += 1

        for value in self._order_values_lcv(var, assignment):
            if not self._is_consistent(var, value, assignment):
                continue

            # Simpan domain saat ini untuk rollback
            saved: Dict[ShiftSlot, Set[str]] = {v: set(d) for v, d in self.domains.items()}

            assignment[var] = value

            if self._forward_check(var, value, assignment, saved):
                result = self._backtrack(assignment)
                if result is not None:
                    return result

            # Rollback
            self.domains = saved
            del assignment[var]

        return None  # backtrack

    # ------------------------------------------------------------------
    # API Publik
    # ------------------------------------------------------------------

    def solve(self) -> Tuple[Optional[Assignment], Dict[str, Any]]:
        """
        Selesaikan CSP: jalankan AC-3 lalu Backtracking MRV+LCV.

        Returns
        -------
        assignment : dict {ShiftSlot → staff_name} atau None jika tidak ada solusi.
        stats      : dict statistik {feasible_after_ac3, nodes_explored, elapsed_s, ...}
        """
        self._nodes_explored = 0
        t0 = time.perf_counter()

        # Deteksi awal: jika ada domain kosong langsung → infeasible
        for var in self.variables:
            if not self.domains[var]:
                self.stats = {
                    "feasible_after_ac3": False,
                    "nodes_explored":     0,
                    "elapsed_s":          0.0,
                    "ac3_time_s":         0.0,
                    "backtrack_time_s":   0.0,
                }
                return None, self.stats

        # Fase 1: AC-3
        ac3_ok = self.arc_consistency_ac3()
        t_ac3 = time.perf_counter() - t0

        if not ac3_ok:
            self.stats = {
                "feasible_after_ac3": False,
                "nodes_explored":     0,
                "elapsed_s":          t_ac3,
                "ac3_time_s":         t_ac3,
                "backtrack_time_s":   0.0,
            }
            return None, self.stats

        # Fase 2: Backtracking
        t_bt = time.perf_counter()
        result = self._backtrack({})
        t_end = time.perf_counter()

        self.stats = {
            "feasible_after_ac3": True,
            "nodes_explored":     self._nodes_explored,
            "elapsed_s":          t_end - t0,
            "ac3_time_s":         t_ac3,
            "backtrack_time_s":   t_end - t_bt,
            "solution_found":     result is not None,
        }
        return result, self.stats

    def verify_solution(self, assignment: Assignment) -> Dict[str, List[str]]:
        """
        Verifikasi bahwa assignment memenuhi semua batasan.

        Returns
        -------
        Sebuah dict berisi daftar pelanggaran per kategori batasan.
        Dict kosong berarti solusi valid.
        """
        violations: Dict[str, List[str]] = {
            "C1_same_day": [],
            "C2_rest":     [],
            "C4_hours":    [],
        }

        # C1 & C2 — cek setiap pasang slot
        slots = list(assignment.items())
        for i, (vi, si) in enumerate(slots):
            for j, (vj, sj) in enumerate(slots):
                if i >= j:
                    continue
                # C1
                if vi.day == vj.day and si == sj:
                    violations["C1_same_day"].append(
                        f"{si} bekerja dua kali pada hari {DAY_NAMES[vi.day]}"
                        f" (slot {vi} dan {vj})"
                    )
                # C2
                if (si == sj
                        and vi.shift is ShiftType.NIGHT
                        and vj.shift is ShiftType.MORNING
                        and vj.day == vi.day + 1):
                    violations["C2_rest"].append(
                        f"{si} NIGHT→MORNING berurutan: {vi} → {vj}"
                    )

        # C4 — jam kerja per staf
        hours: Dict[str, int] = {}
        for var, staf in assignment.items():
            hours[staf] = hours.get(staf, 0) + SHIFT_HOURS[var.shift]
        for staf, h in hours.items():
            if h > self.max_hours_per_week:
                violations["C4_hours"].append(
                    f"{staf} bekerja {h} jam (batas {self.max_hours_per_week} jam)"
                )

        return {k: v for k, v in violations.items() if v}


# ---------------------------------------------------------------------------
# Factory — Pembuat CSP Jadwal Shift
# ---------------------------------------------------------------------------

def build_shift_scheduling_csp(
    staff: List[str],
    n_days: int = 5,
    shift_types: Optional[List[ShiftType]] = None,
    slots_per_shift: int = 1,
    unavailable: Optional[Dict[str, Set[int]]] = None,
    max_hours_per_week: int = 40,
) -> WarehouseCSP:
    """
    Bangun WarehouseCSP untuk penjadwalan shift staf gudang.

    Parameters
    ----------
    staff              : daftar nama staf
    n_days             : jumlah hari (0 = Senin, dst.; default 5 = Senin–Jumat)
    shift_types        : daftar tipe shift yang dipakai (default: semua tiga shift)
    slots_per_shift    : jumlah staf yang dibutuhkan per shift per hari (default 1)
    unavailable        : {nama_staf: {hari_tidak_tersedia, ...}} (opsional)
    max_hours_per_week : batas total jam kerja staf per minggu (default 40)

    Returns
    -------
    WarehouseCSP siap di-solve.
    """
    if not staff:
        raise ValueError("Daftar staf tidak boleh kosong.")
    if n_days < 1:
        raise ValueError("n_days harus ≥ 1.")
    if slots_per_shift < 1:
        raise ValueError("slots_per_shift harus ≥ 1.")

    if shift_types is None:
        shift_types = [ShiftType.MORNING, ShiftType.AFTERNOON, ShiftType.NIGHT]
    if unavailable is None:
        unavailable = {}

    variables: List[ShiftSlot] = []
    domains:   Dict[ShiftSlot, Set[str]] = {}

    for day in range(n_days):
        for shift in shift_types:
            for slot in range(slots_per_shift):
                var = ShiftSlot(day=day, shift=shift, slot=slot)
                variables.append(var)
                # Domain: staf yang TERSEDIA pada hari ini
                domains[var] = {
                    s for s in staff
                    if day not in unavailable.get(s, set())
                }

    return WarehouseCSP(
        variables=variables,
        domains=domains,
        staff_list=staff,
        max_hours_per_week=max_hours_per_week,
    )


# ---------------------------------------------------------------------------
# Analisis Sensitivitas
# ---------------------------------------------------------------------------

def sensitivity_analysis(
    configs: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Jalankan benchmark solver pada berbagai konfigurasi masalah.

    Parameters
    ----------
    configs : daftar dict konfigurasi. Setiap dict boleh berisi kunci:
              n_staff, n_days, slots_per_shift, max_hours_per_week.
              Jika None, gunakan konfigurasi default (skala kecil → sedang → besar).

    Returns
    -------
    Daftar dict hasil: satu per konfigurasi, mencakup parameter + stats.
    """
    if configs is None:
        configs = [
            {"n_staff": 3,  "n_days": 1, "slots_per_shift": 1, "max_hours_per_week": 24},
            {"n_staff": 4,  "n_days": 3, "slots_per_shift": 1, "max_hours_per_week": 40},
            {"n_staff": 5,  "n_days": 5, "slots_per_shift": 1, "max_hours_per_week": 40},
            {"n_staff": 6,  "n_days": 5, "slots_per_shift": 1, "max_hours_per_week": 40},
            {"n_staff": 8,  "n_days": 5, "slots_per_shift": 2, "max_hours_per_week": 40},
            {"n_staff": 10, "n_days": 7, "slots_per_shift": 2, "max_hours_per_week": 48},
        ]

    results: List[Dict[str, Any]] = []

    for cfg in configs:
        n_staff     = cfg.get("n_staff",     5)
        n_days      = cfg.get("n_days",      5)
        sps         = cfg.get("slots_per_shift", 1)
        max_hours   = cfg.get("max_hours_per_week", 40)
        n_vars      = n_days * 3 * sps   # 3 tipe shift

        staf_list = [f"S{i+1:02d}" for i in range(n_staff)]
        csp = build_shift_scheduling_csp(
            staff=staf_list,
            n_days=n_days,
            slots_per_shift=sps,
            max_hours_per_week=max_hours,
        )

        _, stats = csp.solve()

        row = {
            "n_staff":          n_staff,
            "n_days":           n_days,
            "slots_per_shift":  sps,
            "n_variables":      n_vars,
            "max_hours":        max_hours,
            "feasible_ac3":     stats.get("feasible_after_ac3"),
            "solution_found":   stats.get("solution_found"),
            "nodes_explored":   stats.get("nodes_explored", 0),
            "elapsed_ms":       round(stats.get("elapsed_s", 0) * 1000, 3),
            "ac3_ms":           round(stats.get("ac3_time_s", 0) * 1000, 3),
            "backtrack_ms":     round(stats.get("backtrack_time_s", 0) * 1000, 3),
        }
        results.append(row)

    return results


def _print_sensitivity_table(results: List[Dict[str, Any]]) -> None:  # pragma: no cover
    """Cetak tabel analisis sensitivitas ke stdout."""
    hdr = (
        f"{'Staf':>5} {'Hari':>5} {'Slt':>4} {'Var':>5} "
        f"{'Nodes':>8} {'AC3 ms':>8} {'BT ms':>8} {'Total ms':>9} {'Solusi':>7}"
    )
    sep = "-" * len(hdr)
    print(sep)
    print(hdr)
    print(sep)
    for r in results:
        sol = "[OK]" if r["solution_found"] else ("[X] AC3" if not r["feasible_ac3"] else "[X] BT")
        print(
            f"{r['n_staff']:>5} {r['n_days']:>5} {r['slots_per_shift']:>4} {r['n_variables']:>5} "
            f"{r['nodes_explored']:>8} {r['ac3_ms']:>8.2f} {r['backtrack_ms']:>8.2f} "
            f"{r['elapsed_ms']:>9.2f} {sol:>7}"
        )
    print(sep)


def _print_assignment(assignment: Assignment) -> None:  # pragma: no cover
    """Cetak jadwal shift ke stdout dalam format tabel harian."""
    if not assignment:
        return
    # Kelompokkan per hari
    per_day: Dict[int, list] = {}
    # Urut berdasarkan (hari, urutan logis shift M→A→N, nomor slot)
    _shift_order = {ShiftType.MORNING: 0, ShiftType.AFTERNOON: 1, ShiftType.NIGHT: 2}
    _slot_key = lambda item: (item[0].day, _shift_order[item[0].shift], item[0].slot)
    for slot, staf in sorted(assignment.items(), key=_slot_key):
        per_day.setdefault(slot.day, []).append((slot, staf))

    print(f"\n{'Hari':<6} {'Shift':<11} {'Slot':>5}  {'Staf'}")
    print("-" * 36)
    for day in sorted(per_day):
        day_label = DAY_NAMES[day] if day < len(DAY_NAMES) else f"D{day}"
        for slot, staf in sorted(per_day[day], key=lambda x: (x[0].shift.value, x[0].slot)):
            shift_label = {
                ShiftType.MORNING:   "Pagi  (06–14)",
                ShiftType.AFTERNOON: "Siang (14–22)",
                ShiftType.NIGHT:     "Malam (22–06)",
            }[slot.shift]
            print(f"{day_label:<6} {shift_label:<11}  #{slot.slot+1:>2}   {staf}")


# ---------------------------------------------------------------------------
# Demo Utama
# ---------------------------------------------------------------------------

def main() -> None:  # pragma: no cover
    """
    Demonstrasi solver CSP pada kasus studi gudang nyata + analisis sensitivitas.
    """
    print("=" * 60)
    print("  Smart Warehouse Agent — Milestone 2: CSP Solver")
    print("=" * 60)

    # ------------------------------------------------------------------
    # Kasus 1: Jadwal normal (5 staf, 5 hari, 1 staf/shift)
    # ------------------------------------------------------------------
    print("\n[KASUS 1] Jadwal Shift Normal — 5 Staf, 5 Hari, 1 Slot/Shift")
    print("-" * 60)
    staf_normal = ["Andi", "Budi", "Citra", "Dewi", "Eko"]
    csp1 = build_shift_scheduling_csp(
        staff=staf_normal,
        n_days=5,
        slots_per_shift=1,
        max_hours_per_week=40,
    )
    sol1, stats1 = csp1.solve()
    if sol1:
        _print_assignment(sol1)
        print(f"\nNodes dijelajahi : {stats1['nodes_explored']}")
        print(f"Waktu total      : {stats1['elapsed_s']*1000:.2f} ms")
        violations = csp1.verify_solution(sol1)
        if not violations:
            print("[OK] Semua batasan terpenuhi (solusi valid).")
        else:  # seharusnya tidak terjadi
            print(f"[X] Pelanggaran: {violations}")
    else:
        print("[X] Tidak ditemukan solusi.")

    # ------------------------------------------------------------------
    # Kasus 2: Staf dengan hari tidak tersedia (unavailability)
    # ------------------------------------------------------------------
    print("\n\n[KASUS 2] Staf dengan Hari Libur / Tidak Tersedia")
    print("-" * 60)
    csp2 = build_shift_scheduling_csp(
        staff=staf_normal,
        n_days=5,
        slots_per_shift=1,
        unavailable={
            "Andi":  {0, 1},   # Andi libur Senin & Selasa
            "Citra": {4},      # Citra libur Jumat
        },
        max_hours_per_week=40,
    )
    sol2, stats2 = csp2.solve()
    if sol2:
        _print_assignment(sol2)
        violations2 = csp2.verify_solution(sol2)
        status = "[OK] Valid" if not violations2 else f"[X] {violations2}"
        print(f"\nNodes dijelajahi : {stats2['nodes_explored']} | {status}")
    else:
        print("[X] Tidak ditemukan solusi (mungkin staf tidak mencukupi).")

    # ------------------------------------------------------------------
    # Kasus 3: Multi-slot (2 staf per shift, 8 staf total)
    # ------------------------------------------------------------------
    print("\n\n[KASUS 3] Multi-Slot — 2 Staf per Shift, 8 Staf, 3 Hari")
    print("-" * 60)
    staf_besar = ["A1","A2","B1","B2","C1","C2","D1","D2"]
    csp3 = build_shift_scheduling_csp(
        staff=staf_besar,
        n_days=3,
        slots_per_shift=2,
        max_hours_per_week=40,
    )
    sol3, stats3 = csp3.solve()
    if sol3:
        _print_assignment(sol3)
        violations3 = csp3.verify_solution(sol3)
        status = "[OK] Valid" if not violations3 else f"[X] {violations3}"
        print(f"\nNodes dijelajahi : {stats3['nodes_explored']} | {status}")
    else:
        print("[X] Tidak ditemukan solusi.")

    # ------------------------------------------------------------------
    # Analisis Sensitivitas
    # ------------------------------------------------------------------
    print("\n\n[ANALISIS SENSITIVITAS] Kinerja Solver vs Ukuran Masalah")
    print("-" * 60)
    results = sensitivity_analysis()
    _print_sensitivity_table(results)

    print("\nKeterangan kolom:")
    print("  Staf = jumlah staf | Hari = jumlah hari | Slt = slot/shift")
    print("  Var  = total variabel CSP | Nodes = node dieksplorasi backtracking")
    print("  AC3  = waktu propagasi batasan | BT = waktu backtracking")


if __name__ == "__main__":
    main()
