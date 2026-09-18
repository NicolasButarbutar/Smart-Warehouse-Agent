"""
warehouse_search.py
--------------------
Baseline search module for the Smart Warehouse Management Agent
(Smart Warehouse Management Agent untuk Optimasi Penyimpanan Barang).

Implements:
  - Uniform Cost Search (UCS)
  - A* Search (with an admissible Manhattan-distance heuristic)

The warehouse is modeled as a weighted graph. Nodes represent points on the
warehouse map (receiving dock, aisle intersections, rack/storage slots).
Edge weights represent real travel cost (distance/time) between adjacent
nodes, consistent with the formal state-space definition (X, A, T, G, C)
described in the Milestone 1 report.

Run directly to see UCS and A* compared on an example warehouse graph:
    python src/warehouse_search.py
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Graph representation
# ---------------------------------------------------------------------------

Graph = Dict[str, List[Tuple[str, float]]]
Coordinates = Dict[str, Tuple[float, float]]


@dataclass
class SearchResult:
    """Holds the outcome of a search run."""
    path: Optional[List[str]]
    cost: float
    nodes_expanded: int
    frontier_max_size: int = field(default=0)

    def __str__(self) -> str:  # pragma: no cover - convenience only
        if self.path is None:
            return "Tidak ditemukan jalur (goal tidak tercapai)."
        return (
            f"Path: {' -> '.join(self.path)}\n"
            f"Total cost: {self.cost:.2f}\n"
            f"Nodes expanded: {self.nodes_expanded}\n"
            f"Max frontier size: {self.frontier_max_size}"
        )


def reconstruct_path(came_from: Dict[str, str], start: str, goal: str) -> List[str]:
    path = [goal]
    while path[-1] != start:
        path.append(came_from[path[-1]])
    path.reverse()
    return path


# ---------------------------------------------------------------------------
# Uniform Cost Search (UCS)
# ---------------------------------------------------------------------------

def uniform_cost_search(graph: Graph, start: str, goal: str) -> SearchResult:
    """
    Explores nodes in order of lowest cumulative path cost g(n).
    Guarantees an optimal path for graphs with non-negative edge weights.
    """
    frontier: List[Tuple[float, int, str]] = []
    counter = 0  # tie-breaker so the heap never compares strings directly
    heapq.heappush(frontier, (0.0, counter, start))

    came_from: Dict[str, str] = {}
    cost_so_far: Dict[str, float] = {start: 0.0}
    visited = set()
    nodes_expanded = 0
    max_frontier = 1

    while frontier:
        max_frontier = max(max_frontier, len(frontier))
        current_cost, _, current = heapq.heappop(frontier)

        if current in visited:
            continue
        visited.add(current)
        nodes_expanded += 1

        if current == goal:
            return SearchResult(
                path=reconstruct_path(came_from, start, goal),
                cost=current_cost,
                nodes_expanded=nodes_expanded,
                frontier_max_size=max_frontier,
            )

        for neighbor, weight in graph.get(current, []):
            new_cost = current_cost + weight
            if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                cost_so_far[neighbor] = new_cost
                came_from[neighbor] = current
                counter += 1
                heapq.heappush(frontier, (new_cost, counter, neighbor))

    return SearchResult(path=None, cost=float("inf"), nodes_expanded=nodes_expanded,
                         frontier_max_size=max_frontier)


# ---------------------------------------------------------------------------
# A* Search
# ---------------------------------------------------------------------------

def manhattan_heuristic(node: str, goal: str, coordinates: Coordinates) -> float:
    """
    Admissible heuristic for a grid-shaped warehouse layout: the Manhattan
    distance between the node and the goal never overestimates the real
    travel cost, since actual paths through aisles are >= straight-line
    grid distance.
    """
    (x1, y1) = coordinates[node]
    (x2, y2) = coordinates[goal]
    return abs(x1 - x2) + abs(y1 - y2)


def a_star_search(graph: Graph, start: str, goal: str, coordinates: Coordinates) -> SearchResult:
    """
    Explores nodes in order of f(n) = g(n) + h(n), where g(n) is the
    cumulative real cost and h(n) is the Manhattan-distance heuristic.
    """
    frontier: List[Tuple[float, int, str]] = []
    counter = 0
    heapq.heappush(frontier, (manhattan_heuristic(start, goal, coordinates), counter, start))

    came_from: Dict[str, str] = {}
    cost_so_far: Dict[str, float] = {start: 0.0}
    visited = set()
    nodes_expanded = 0
    max_frontier = 1

    while frontier:
        max_frontier = max(max_frontier, len(frontier))
        _, _, current = heapq.heappop(frontier)

        if current in visited:
            continue
        visited.add(current)
        nodes_expanded += 1

        if current == goal:
            return SearchResult(
                path=reconstruct_path(came_from, start, goal),
                cost=cost_so_far[current],
                nodes_expanded=nodes_expanded,
                frontier_max_size=max_frontier,
            )

        for neighbor, weight in graph.get(current, []):
            new_cost = cost_so_far[current] + weight
            if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                cost_so_far[neighbor] = new_cost
                priority = new_cost + manhattan_heuristic(neighbor, goal, coordinates)
                came_from[neighbor] = current
                counter += 1
                heapq.heappush(frontier, (priority, counter, neighbor))

    return SearchResult(path=None, cost=float("inf"), nodes_expanded=nodes_expanded,
                         frontier_max_size=max_frontier)


# ---------------------------------------------------------------------------
# Example warehouse graph
# ---------------------------------------------------------------------------
# Nodes:
#   DOCK   - receiving dock (entry point for incoming goods)
#   J1..J4 - aisle junctions (intersections between rack rows)
#   R1..R5 - storage rack slots (putaway / retrieval targets)
#
# Edge weights approximate travel distance/time in meters.

def build_example_warehouse() -> Tuple[Graph, Coordinates]:
    graph: Graph = {
        "DOCK": [("J1", 5)],
        "J1": [("DOCK", 5), ("J2", 4), ("R1", 3)],
        "J2": [("J1", 4), ("J3", 4), ("R2", 2)],
        "J3": [("J2", 4), ("J4", 3), ("R3", 2)],
        "J4": [("J3", 3), ("R4", 2), ("R5", 5)],
        "R1": [("J1", 3)],
        "R2": [("J2", 2)],
        "R3": [("J3", 2)],
        "R4": [("J4", 2)],
        "R5": [("J4", 5)],
    }

    # Approximate grid coordinates (x = lorong index, y = jarak dari dock)
    coordinates: Coordinates = {
        "DOCK": (0, 0),
        "J1": (0, 1),
        "J2": (0, 2),
        "J3": (0, 3),
        "J4": (0, 4),
        "R1": (1, 1),
        "R2": (1, 2),
        "R3": (1, 3),
        "R4": (1, 4),
        "R5": (2, 4),
    }
    return graph, coordinates


def main() -> None:
    graph, coordinates = build_example_warehouse()
    start, goal = "DOCK", "R5"

    print(f"=== Uniform Cost Search: {start} -> {goal} ===")
    ucs_result = uniform_cost_search(graph, start, goal)
    print(ucs_result)

    print(f"\n=== A* Search: {start} -> {goal} ===")
    astar_result = a_star_search(graph, start, goal, coordinates)
    print(astar_result)

    print("\n=== Ringkasan Perbandingan ===")
    print(f"UCS  -> cost: {ucs_result.cost:.2f}, nodes expanded: {ucs_result.nodes_expanded}")
    print(f"A*   -> cost: {astar_result.cost:.2f}, nodes expanded: {astar_result.nodes_expanded}")


if __name__ == "__main__":
    main()
