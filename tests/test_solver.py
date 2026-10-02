"""
test_solver.py
--------------
Unit tests untuk src/solver.py (Milestone 2 — CSP Shift Scheduling Solver).

Mencakup:
  - Uji fungsional dasar (AC-3 dan backtracking)
  - Verifikasi semua batasan C1/C2/C4
  - Kasus-kasus ekstrem (edge cases)

Jalankan dengan:
    uv run pytest tests/test_solver.py -v
atau:
    pytest tests/test_solver.py -v
"""

import sys
from pathlib import Path

# Pastikan 'src/' dapat di-import tanpa instalasi paket tambahan
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from solver import (
    ShiftSlot,
    ShiftType,
    WarehouseCSP,
    build_shift_scheduling_csp,
    sensitivity_analysis,
    SHIFT_HOURS,
)


# ===========================================================================
# Fixture umum
# ===========================================================================

@pytest.fixture
def five_staff():
    """5 staf standar untuk kasus normal."""
    return ["Andi", "Budi", "Citra", "Dewi", "Eko"]


@pytest.fixture
def simple_csp(five_staff):
    """CSP sederhana: 5 staf, 1 hari, 3 shift, 1 slot/shift → harus selalu ada solusi."""
    return build_shift_scheduling_csp(
        staff=five_staff,
        n_days=1,
        slots_per_shift=1,
        max_hours_per_week=40,
    )


@pytest.fixture
def week_csp(five_staff):
    """CSP mingguan: 5 staf, 5 hari, 3 shift, 1 slot/shift."""
    return build_shift_scheduling_csp(
        staff=five_staff,
        n_days=5,
        slots_per_shift=1,
        max_hours_per_week=40,
    )


# ===========================================================================
# 1. Uji Konstruksi & Validasi Input
# ===========================================================================

class TestConstruction:

    def test_variables_count_matches_config(self):
        """Jumlah variabel = n_days × n_shifts × slots_per_shift."""
        csp = build_shift_scheduling_csp(staff=["A","B","C"], n_days=3,
                                         slots_per_shift=2, max_hours_per_week=48)
        assert len(csp.variables) == 3 * 3 * 2  # 3 hari × 3 shift × 2 slot = 18

    def test_domain_excludes_unavailable_staff(self):
        """Staf yang libur pada hari tertentu tidak boleh masuk domain hari itu."""
        csp = build_shift_scheduling_csp(
            staff=["A","B","C"],
            n_days=2,
            unavailable={"A": {0}},   # A libur hari pertama (index 0)
            max_hours_per_week=40,
        )
        for var in csp.variables:
            if var.day == 0:
                assert "A" not in csp.domains[var], \
                    f"A seharusnya tidak tersedia pada {var}"
            else:
                assert "A" in csp.domains[var], \
                    f"A seharusnya tersedia pada {var}"

    def test_empty_staff_raises(self):
        """Daftar staf kosong harus memunculkan ValueError."""
        with pytest.raises(ValueError, match="staf"):
            build_shift_scheduling_csp(staff=[], n_days=1)

    def test_invalid_n_days_raises(self):
        """n_days = 0 harus memunculkan ValueError."""
        with pytest.raises(ValueError, match="n_days"):
            build_shift_scheduling_csp(staff=["A"], n_days=0)

    def test_invalid_slots_raises(self):
        """slots_per_shift = 0 harus memunculkan ValueError."""
        with pytest.raises(ValueError, match="slots_per_shift"):
            build_shift_scheduling_csp(staff=["A"], n_days=1, slots_per_shift=0)

    def test_empty_variables_raises(self):
        """WarehouseCSP dengan daftar variabel kosong harus memunculkan ValueError."""
        with pytest.raises(ValueError, match="variabel"):
            WarehouseCSP(variables=[], domains={}, staff_list=["A"])

    def test_custom_shift_types(self):
        """CSP dengan hanya shift pagi dan siang (tanpa malam)."""
        csp = build_shift_scheduling_csp(
            staff=["A","B"],
            n_days=2,
            shift_types=[ShiftType.MORNING, ShiftType.AFTERNOON],
        )
        assert len(csp.variables) == 2 * 2  # 2 hari × 2 shift
        for var in csp.variables:
            assert var.shift in (ShiftType.MORNING, ShiftType.AFTERNOON)


# ===========================================================================
# 2. Uji AC-3 (Propagasi Batasan)
# ===========================================================================

class TestAC3:

    def test_ac3_detects_infeasible_empty_domain(self):
        """
        EDGE CASE: Domain salah satu slot kosong sejak awal.
        AC-3 harus mengembalikan False sebelum backtracking.
        """
        csp = build_shift_scheduling_csp(staff=["A","B"], n_days=1, slots_per_shift=1)
        # Kosongkan domain satu variabel secara paksa
        csp.domains[csp.variables[0]] = set()
        ok = csp.arc_consistency_ac3()
        assert ok is False

    def test_ac3_prunes_domain(self):
        """AC-3 harus memangkas domain yang tidak konsisten dengan tetangganya."""
        # Hanya ada 1 staf, 1 hari, 3 shift → mustahil (C1: staf sama tidak bisa 3 shift/hari)
        csp = build_shift_scheduling_csp(staff=["A"], n_days=1, slots_per_shift=1)
        ok = csp.arc_consistency_ac3()
        # Dengan 1 staf dan 3 slot pada hari yang sama, AC-3 harus mendeteksi infeasibility
        assert ok is False

    def test_ac3_returns_true_when_feasible(self, simple_csp):
        """AC-3 harus True untuk masalah yang feasible."""
        ok = simple_csp.arc_consistency_ac3()
        assert ok is True

    def test_ac3_does_not_expand_domain(self, simple_csp):
        """AC-3 tidak boleh menambah nilai ke domain (hanya memangkas)."""
        original_sizes = {v: len(d) for v, d in simple_csp.domains.items()}
        simple_csp.arc_consistency_ac3()
        for var in simple_csp.variables:
            assert len(simple_csp.domains[var]) <= original_sizes[var]

    def test_ac3_night_morning_rest_prune(self):
        """
        AC-3 harus memangkas staf yang sama dari arc (Night-hari-0, Morning-hari-1)
        jika satu-satunya nilai yang tersedia adalah staf yang sama.
        """
        # 2 staf, 2 hari, hanya Night (hari 0) dan Morning (hari 1)
        csp = build_shift_scheduling_csp(
            staff=["A","B"],
            n_days=2,
            shift_types=[ShiftType.NIGHT, ShiftType.MORNING],
            slots_per_shift=1,
            max_hours_per_week=40,
        )
        # Paksa domain Night-hari-0 hanya berisi "A"
        night_d0 = next(v for v in csp.variables if v.day == 0 and v.shift == ShiftType.NIGHT)
        morning_d1 = next(v for v in csp.variables if v.day == 1 and v.shift == ShiftType.MORNING)
        csp.domains[night_d0] = {"A"}
        # Setelah AC-3: Morning-hari-1 tidak boleh berisi "A"
        csp.arc_consistency_ac3()
        assert "A" not in csp.domains[morning_d1], \
            "AC-3 harus membuang 'A' dari Morning-hari-1 karena Night-hari-0 sudah 'A'"


# ===========================================================================
# 3. Uji Backtracking & Solusi
# ===========================================================================

class TestBacktracking:

    def test_simple_case_finds_solution(self, simple_csp):
        """Kasus 1 hari, 5 staf, 3 shift: harus menemukan solusi."""
        sol, _ = simple_csp.solve()
        assert sol is not None

    def test_solution_covers_all_variables(self, simple_csp):
        """Solusi harus meng-assign semua variabel."""
        sol, _ = simple_csp.solve()
        assert sol is not None
        assert set(sol.keys()) == set(simple_csp.variables)

    def test_solution_uses_valid_staff(self, simple_csp, five_staff):
        """Setiap nilai dalam solusi harus merupakan nama staf yang valid."""
        sol, _ = simple_csp.solve()
        assert sol is not None
        for staf in sol.values():
            assert staf in five_staff

    def test_week_schedule_finds_solution(self, week_csp):
        """Kasus 5 staf, 5 hari, 3 shift/hari: harus menemukan solusi."""
        sol, _ = week_csp.solve()
        assert sol is not None

    def test_stats_populated_after_solve(self, simple_csp):
        """Stats harus terisi setelah solve() dipanggil."""
        _, stats = simple_csp.solve()
        assert "nodes_explored" in stats
        assert "elapsed_s" in stats
        assert stats["elapsed_s"] >= 0


# ===========================================================================
# 4. Uji Validitas Batasan (Correctness)
# ===========================================================================

class TestConstraintCorrectness:

    def test_c1_no_same_staff_same_day(self, week_csp):
        """C1: Tidak ada staf yang bekerja lebih dari satu shift pada hari yang sama."""
        sol, _ = week_csp.solve()
        assert sol is not None
        per_day: dict = {}
        for slot, staf in sol.items():
            per_day.setdefault(slot.day, []).append(staf)
        for day, assigned in per_day.items():
            assert len(assigned) == len(set(assigned)), \
                f"Hari {day}: staf duplikat ditemukan: {assigned}"

    def test_c2_no_night_then_morning(self, week_csp):
        """C2: Tidak ada staf yang bekerja NIGHT lalu MORNING hari berikutnya."""
        sol, _ = week_csp.solve()
        assert sol is not None
        night_slots = {v: s for v, s in sol.items() if v.shift == ShiftType.NIGHT}
        morning_slots = {v: s for v, s in sol.items() if v.shift == ShiftType.MORNING}
        for nv, ns in night_slots.items():
            for mv, ms in morning_slots.items():
                if mv.day == nv.day + 1:
                    assert ns != ms, \
                        f"C2 DILANGGAR: {ns} bekerja NIGHT {nv} lalu MORNING {mv}"

    def test_c4_max_hours_respected(self, week_csp):
        """C4: Tidak ada staf yang melebihi batas jam kerja per minggu."""
        sol, _ = week_csp.solve()
        assert sol is not None
        hours: dict = {}
        for var, staf in sol.items():
            hours[staf] = hours.get(staf, 0) + SHIFT_HOURS[var.shift]
        for staf, h in hours.items():
            assert h <= week_csp.max_hours_per_week, \
                f"{staf} bekerja {h} jam, melebihi batas {week_csp.max_hours_per_week} jam"

    def test_verify_solution_passes_for_valid(self, week_csp):
        """verify_solution() harus mengembalikan dict kosong untuk solusi yang valid."""
        sol, _ = week_csp.solve()
        assert sol is not None
        violations = week_csp.verify_solution(sol)
        assert violations == {}, f"Pelanggaran ditemukan: {violations}"


# ===========================================================================
# 5. Edge Cases — Kasus Ekstrem
# ===========================================================================

class TestEdgeCases:

    # ------------------------------------------------------------------
    # EC-1: Masalah trivial — 1 staf, 1 hari, 1 shift
    # ------------------------------------------------------------------
    def test_ec1_trivial_single_staff_single_shift(self):
        """EDGE CASE: 1 staf, 1 shift per hari, 1 hari — solusi trivial."""
        csp = build_shift_scheduling_csp(
            staff=["Solo"],
            n_days=1,
            shift_types=[ShiftType.MORNING],
            slots_per_shift=1,
            max_hours_per_week=40,
        )
        sol, stats = csp.solve()
        assert sol is not None
        assert list(sol.values()) == ["Solo"]

    # ------------------------------------------------------------------
    # EC-2: Overconstrained — tidak cukup staf untuk mengisi slot
    # ------------------------------------------------------------------
    def test_ec2_too_few_staff_returns_none(self):
        """
        EDGE CASE: 1 staf, 1 hari, 3 shift.
        C1 melarang staf yang sama di hari yang sama → tidak ada solusi.
        """
        csp = build_shift_scheduling_csp(
            staff=["LoneWorker"],
            n_days=1,
            shift_types=[ShiftType.MORNING, ShiftType.AFTERNOON, ShiftType.NIGHT],
            slots_per_shift=1,
        )
        sol, stats = csp.solve()
        assert sol is None, "Seharusnya tidak ada solusi (1 staf, 3 shift pada hari yang sama)"

    # ------------------------------------------------------------------
    # EC-3: Staf tidak tersedia pada semua hari → domain kosong
    # ------------------------------------------------------------------
    def test_ec3_all_staff_unavailable_one_day(self):
        """
        EDGE CASE: Semua staf tidak tersedia pada hari tertentu →
        domain kosong → AC-3 mengembalikan False.
        """
        csp = build_shift_scheduling_csp(
            staff=["A","B","C"],
            n_days=2,
            unavailable={"A": {1}, "B": {1}, "C": {1}},  # Semua libur hari ke-1
            max_hours_per_week=40,
        )
        sol, stats = csp.solve()
        assert sol is None
        assert stats["feasible_after_ac3"] is False

    # ------------------------------------------------------------------
    # EC-4: Batas jam kerja sangat rendah → tidak bisa mengisi semua shift
    # ------------------------------------------------------------------
    def test_ec4_max_hours_too_low_returns_none(self):
        """
        EDGE CASE: max_hours_per_week lebih rendah dari satu shift (< 8 jam)
        → tidak ada staf yang bisa di-assign ke slot mana pun.
        """
        csp = build_shift_scheduling_csp(
            staff=["A","B","C"],
            n_days=1,
            shift_types=[ShiftType.MORNING],
            slots_per_shift=1,
            max_hours_per_week=4,  # lebih rendah dari satu shift (8 jam)
        )
        sol, _ = csp.solve()
        assert sol is None, "max_hours < 8 jam seharusnya menghalangi semua assignment"

    # ------------------------------------------------------------------
    # EC-5: Exactly-enough — staf = jumlah shift pada 1 hari
    # ------------------------------------------------------------------
    def test_ec5_exact_staff_count_one_day(self):
        """
        EDGE CASE: 3 staf, 1 hari, 3 shift, 1 slot/shift.
        Hanya ada satu kemungkinan distribusi → harus ditemukan.
        """
        csp = build_shift_scheduling_csp(
            staff=["X","Y","Z"],
            n_days=1,
            slots_per_shift=1,
            max_hours_per_week=40,
        )
        sol, _ = csp.solve()
        assert sol is not None
        assert len(sol) == 3
        # Setiap staf tepat satu kali
        assert sorted(sol.values()) == ["X","Y","Z"]

    # ------------------------------------------------------------------
    # EC-6: Ketidaktersediaan sebagian staf membatasi domain secara signifikan
    # ------------------------------------------------------------------
    def test_ec6_heavy_unavailability_still_solvable(self):
        """
        EDGE CASE: 4 dari 5 staf libur di hari pertama, hanya 1 staf tersedia.
        Dengan hanya 1 shift di hari itu, seharusnya masih bisa diselesaikan.
        """
        csp = build_shift_scheduling_csp(
            staff=["A","B","C","D","E"],
            n_days=2,
            shift_types=[ShiftType.MORNING],  # hanya 1 shift/hari
            slots_per_shift=1,
            unavailable={
                "A": {0}, "B": {0}, "C": {0}, "D": {0},  # hanya E yang bisa hari 0
            },
            max_hours_per_week=40,
        )
        sol, _ = csp.solve()
        assert sol is not None
        # Verifikasi E mengisi hari 0
        day0_slot = next(v for v in csp.variables if v.day == 0)
        assert sol[day0_slot] == "E"

    # ------------------------------------------------------------------
    # EC-7: Night-Morning constraint secara eksplisit
    # ------------------------------------------------------------------
    def test_ec7_night_morning_rest_constraint_enforced(self):
        """
        EDGE CASE: 2 staf, 2 hari, Night+Morning saja.
        Staf yang bekerja Night-hari-0 tidak boleh di-assign Morning-hari-1.
        """
        csp = build_shift_scheduling_csp(
            staff=["Alpha","Beta"],
            n_days=2,
            shift_types=[ShiftType.NIGHT, ShiftType.MORNING],
            slots_per_shift=1,
            max_hours_per_week=40,
        )
        sol, _ = csp.solve()
        assert sol is not None
        night_d0 = next(v for v in csp.variables if v.day == 0 and v.shift == ShiftType.NIGHT)
        morning_d1 = next(v for v in csp.variables if v.day == 1 and v.shift == ShiftType.MORNING)
        # C2 harus terpenuhi
        assert sol[night_d0] != sol[morning_d1], \
            "C2 DILANGGAR: staf yang sama pada Night-hari-0 dan Morning-hari-1"

    # ------------------------------------------------------------------
    # EC-8: Masalah besar — banyak staf & hari (uji performa dasar)
    # ------------------------------------------------------------------
    def test_ec8_large_problem_finds_solution(self):
        """
        EDGE CASE: 10 staf, 7 hari, 2 slot/shift → 42 variabel.
        Solver harus menemukan solusi dalam waktu wajar (< 10 detik).
        """
        import time
        csp = build_shift_scheduling_csp(
            staff=[f"S{i}" for i in range(1,11)],
            n_days=7,
            slots_per_shift=2,
            max_hours_per_week=48,
        )
        t0 = time.perf_counter()
        sol, stats = csp.solve()
        elapsed = time.perf_counter() - t0
        assert sol is not None, "Masalah besar seharusnya masih bisa diselesaikan"
        assert elapsed < 10.0, f"Solver terlalu lambat: {elapsed:.2f} detik"

    # ------------------------------------------------------------------
    # EC-9: Semua staf unavailable (tidak ada siapa pun) pada semua hari
    # ------------------------------------------------------------------
    def test_ec9_completely_unavailable_staff(self):
        """
        EDGE CASE: Staf tunggal yang tidak tersedia pada semua hari →
        semua domain kosong sejak awal.
        """
        csp = build_shift_scheduling_csp(
            staff=["Ghost"],
            n_days=3,
            unavailable={"Ghost": {0, 1, 2}},  # tidak tersedia semua hari
            max_hours_per_week=40,
        )
        sol, stats = csp.solve()
        assert sol is None
        assert stats["feasible_after_ac3"] is False

    # ------------------------------------------------------------------
    # EC-10: Slot staf majemuk (multi-slot) dengan batasan yang ketat
    # ------------------------------------------------------------------
    def test_ec10_multi_slot_no_duplicate_in_same_shift(self):
        """
        EDGE CASE: 2 slot per shift, 4 staf, 1 hari.
        Dalam satu shift, 2 slot berbeda tidak boleh berisi staf yang sama.
        """
        csp = build_shift_scheduling_csp(
            staff=["P","Q","R","S"],
            n_days=1,
            shift_types=[ShiftType.MORNING],
            slots_per_shift=2,
            max_hours_per_week=40,
        )
        sol, _ = csp.solve()
        assert sol is not None
        # Dua slot pada shift yang sama harus diisi staf berbeda
        values = list(sol.values())
        assert len(values) == len(set(values)), \
            f"Duplikasi staf dalam satu shift terdeteksi: {values}"

    # ------------------------------------------------------------------
    # EC-11: Hanya satu shift type tersedia
    # ------------------------------------------------------------------
    def test_ec11_single_shift_type_all_days(self):
        """
        EDGE CASE: Hanya shift AFTERNOON selama 5 hari.
        Setiap staf boleh bekerja maksimal sekali per hari.
        """
        csp = build_shift_scheduling_csp(
            staff=["A","B","C","D","E"],
            n_days=5,
            shift_types=[ShiftType.AFTERNOON],
            slots_per_shift=1,
            max_hours_per_week=40,
        )
        sol, _ = csp.solve()
        assert sol is not None
        assert len(sol) == 5  # 5 variabel (1 per hari)

    # ------------------------------------------------------------------
    # EC-12: verify_solution mendeteksi pelanggaran C1 secara eksplisit
    # ------------------------------------------------------------------
    def test_ec12_verify_detects_c1_violation(self):
        """verify_solution() harus mendeteksi jika solusi melanggar C1."""
        csp = build_shift_scheduling_csp(
            staff=["A","B","C"],
            n_days=1,
            slots_per_shift=1,
        )
        csp.solve()  # pastikan domains masih ada
        # Buat assignment palsu dengan staf yang sama pada dua slot berbeda di hari yang sama
        fake_vars = csp.variables[:2]
        if len(fake_vars) >= 2:
            bad_assignment = {fake_vars[0]: "A", fake_vars[1]: "A"}
            violations = csp.verify_solution(bad_assignment)
            assert "C1_same_day" in violations, \
                "verify_solution() harus mendeteksi pelanggaran C1"

    # ------------------------------------------------------------------
    # EC-13: Masalah dengan staf berlebih (lebih banyak staf dari slot)
    # ------------------------------------------------------------------
    def test_ec13_many_staff_few_slots(self):
        """
        EDGE CASE: 10 staf, hanya 3 slot (1 hari, 3 shift, 1 slot/shift).
        Solver harus tetap menemukan solusi valid.
        """
        csp = build_shift_scheduling_csp(
            staff=[f"W{i}" for i in range(10)],
            n_days=1,
            slots_per_shift=1,
            max_hours_per_week=40,
        )
        sol, _ = csp.solve()
        assert sol is not None
        assert len(sol) == 3  # tepat 3 slot yang diisi


# ===========================================================================
# 6. Uji Analisis Sensitivitas
# ===========================================================================

class TestSensitivityAnalysis:

    def test_sensitivity_returns_all_configs(self):
        """sensitivity_analysis() harus mengembalikan satu hasil per konfigurasi."""
        configs = [
            {"n_staff": 3, "n_days": 1, "slots_per_shift": 1, "max_hours_per_week": 24},
            {"n_staff": 5, "n_days": 3, "slots_per_shift": 1, "max_hours_per_week": 40},
        ]
        results = sensitivity_analysis(configs)
        assert len(results) == len(configs)

    def test_sensitivity_result_has_required_keys(self):
        """Setiap baris hasil sensitivitas harus memiliki kunci yang diperlukan."""
        results = sensitivity_analysis([
            {"n_staff": 4, "n_days": 2, "slots_per_shift": 1, "max_hours_per_week": 40}
        ])
        required_keys = {
            "n_staff", "n_days", "n_variables",
            "nodes_explored", "elapsed_ms", "solution_found",
        }
        assert required_keys.issubset(results[0].keys())

    def test_sensitivity_runtime_nonnegative(self):
        """Waktu eksekusi tidak boleh negatif."""
        results = sensitivity_analysis([
            {"n_staff": 3, "n_days": 1, "slots_per_shift": 1, "max_hours_per_week": 24},
        ])
        assert results[0]["elapsed_ms"] >= 0

    def test_sensitivity_nodes_nonnegative(self):
        """Jumlah node yang dijelajahi tidak boleh negatif."""
        results = sensitivity_analysis([
            {"n_staff": 5, "n_days": 3, "slots_per_shift": 1, "max_hours_per_week": 40},
        ])
        assert results[0]["nodes_explored"] >= 0

    def test_sensitivity_default_configs_run(self):
        """sensitivity_analysis() dengan konfigurasi default tidak boleh error."""
        results = sensitivity_analysis()
        assert len(results) > 0
        for r in results:
            assert r["elapsed_ms"] >= 0


# ===========================================================================
# 7. Uji Integritas Modul (Smoke Tests)
# ===========================================================================

class TestSmoke:

    def test_shift_hours_defined_for_all_types(self):
        """SHIFT_HOURS harus mendefinisikan jam untuk semua ShiftType."""
        for st in ShiftType:
            assert st in SHIFT_HOURS
            assert SHIFT_HOURS[st] > 0

    def test_shiftslot_hashable(self):
        """ShiftSlot harus hashable agar bisa dipakai sebagai kunci dict / elemen set."""
        slot = ShiftSlot(day=0, shift=ShiftType.MORNING, slot=0)
        d = {slot: "OK"}
        assert d[slot] == "OK"

    def test_shiftslot_frozen(self):
        """ShiftSlot tidak boleh bisa dimodifikasi (frozen=True)."""
        slot = ShiftSlot(day=0, shift=ShiftType.MORNING, slot=0)
        with pytest.raises((AttributeError, TypeError)):
            slot.day = 1  # type: ignore[misc]

    def test_solver_returns_tuple(self, simple_csp):
        """solve() harus mengembalikan tuple (assignment, stats)."""
        result = simple_csp.solve()
        assert isinstance(result, tuple)
        assert len(result) == 2
