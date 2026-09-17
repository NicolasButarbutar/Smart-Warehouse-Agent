"""
Unit tests untuk src/warehouse_search.py (baseline UCS & A*).

Jalankan dengan:
    uv run pytest
atau:
    pytest
"""

import sys
from pathlib import Path

# Agar 'src' bisa di-import tanpa perlu package installer tambahan.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from warehouse_search import (  # noqa: E402
    build_example_warehouse,
    uniform_cost_search,
    a_star_search,
)


def test_ucs_finds_a_path():
    graph, _ = build_example_warehouse()
    result = uniform_cost_search(graph, "DOCK", "R5")
    assert result.path is not None
    assert result.path[0] == "DOCK"
    assert result.path[-1] == "R5"
    assert result.cost > 0


def test_astar_finds_a_path():
    graph, coordinates = build_example_warehouse()
    result = a_star_search(graph, "DOCK", "R5", coordinates)
    assert result.path is not None
    assert result.path[0] == "DOCK"
    assert result.path[-1] == "R5"
    assert result.cost > 0


def test_ucs_and_astar_agree_on_optimal_cost():
    """
    UCS dan A* dengan heuristik admissible harus menghasilkan biaya lintasan
    optimal yang sama, meskipun jumlah node yang dieksplorasi bisa berbeda.
    """
    graph, coordinates = build_example_warehouse()
    ucs_result = uniform_cost_search(graph, "DOCK", "R5")
    astar_result = a_star_search(graph, "DOCK", "R5", coordinates)

    assert ucs_result.cost == astar_result.cost


def test_unreachable_goal_returns_no_path():
    graph = {
        "A": [("B", 1)],
        "B": [("A", 1)],
        "C": [],  # terisolasi, tidak terhubung ke A/B
    }
    result = uniform_cost_search(graph, "A", "C")
    assert result.path is None
    assert result.cost == float("inf")
