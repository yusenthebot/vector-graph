"""Detect dependency cycles in the knowledge graph.

Uses an iterative (non-recursive) Tarjan's SCC algorithm to avoid Python's
default recursion limit on large codebases.

Only CALLS, IMPORTS, and EXTENDS edges are considered dependency edges.
Structural edges (CONTAINS, HAS_METHOD, DEFINES, etc.) are ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from vector_graph._types import EdgeType, GraphNode
from vector_graph.graph.protocols import GraphProtocol

# ---------------------------------------------------------------------------
# Edge types that count as dependency edges for cycle detection
# ---------------------------------------------------------------------------

_CYCLE_EDGE_TYPES: frozenset[EdgeType] = frozenset({
    EdgeType.CALLS,
    EdgeType.IMPORTS,
    EdgeType.EXTENDS,
})


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CycleInfo:
    """A dependency cycle in the knowledge graph.

    Attributes
    ----------
    node_ids:
        Tuple of node IDs that form the cycle.
    node_names:
        Corresponding node display names.
    edge_types:
        Distinct edge types found within the SCC.
    length:
        Number of nodes in the cycle.
    """

    node_ids: tuple[str, ...]
    node_names: tuple[str, ...]
    edge_types: tuple[str, ...]
    length: int


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_cycles(graph: GraphProtocol) -> list[CycleInfo]:
    """Find dependency cycles using iterative Tarjan's SCC algorithm.

    Returns a list of CycleInfo objects — one per SCC with more than one node,
    or exactly one node with a self-loop.

    Parameters
    ----------
    graph:
        Any object satisfying GraphProtocol (e.g. KnowledgeGraph).
    """
    # Build adjacency list restricted to cycle-relevant edge types
    # node_id -> list[target_id]
    adj: dict[str, list[str]] = {}
    for node in graph.iter_nodes():
        adj[node.id] = []

    for edge in graph.iter_edges():
        if edge.edge_type in _CYCLE_EDGE_TYPES:
            if edge.source_id in adj:
                adj[edge.source_id].append(edge.target_id)
            # handle nodes that only appear as edge endpoints
            elif edge.source_id not in adj:
                adj[edge.source_id] = [edge.target_id]

    # Tarjan's SCC (iterative)
    sccs = _tarjan_sccs_iterative(adj)

    # Build a quick lookup: node_id -> node
    node_lookup: dict[str, GraphNode] = {n.id: n for n in graph.iter_nodes()}

    # Pre-compute edge type map for quick SCC edge-type lookup
    # (src_id, tgt_id) -> edge_type.value
    edge_type_map: dict[tuple[str, str], str] = {}
    for edge in graph.iter_edges():
        if edge.edge_type in _CYCLE_EDGE_TYPES:
            edge_type_map[(edge.source_id, edge.target_id)] = edge.edge_type.value

    cycles: list[CycleInfo] = []
    for scc in sccs:
        scc_set = set(scc)

        # Single-node SCC: only counts as a cycle if it has a self-loop
        if len(scc) == 1:
            node_id = scc[0]
            if node_id not in adj or node_id not in [t for t in adj.get(node_id, [])]:
                continue  # no self-loop — not a cycle

        # Collect edge types within the SCC
        edge_types_in_scc: set[str] = set()
        for src_id in scc:
            for tgt_id in adj.get(src_id, []):
                if tgt_id in scc_set:
                    key = (src_id, tgt_id)
                    if key in edge_type_map:
                        edge_types_in_scc.add(edge_type_map[key])

        node_ids = tuple(scc)
        node_names = tuple(
            node_lookup[nid].properties.name if nid in node_lookup else nid
            for nid in scc
        )

        cycles.append(CycleInfo(
            node_ids=node_ids,
            node_names=node_names,
            edge_types=tuple(sorted(edge_types_in_scc)),
            length=len(scc),
        ))

    return cycles


# ---------------------------------------------------------------------------
# Iterative Tarjan's SCC
# ---------------------------------------------------------------------------


def _tarjan_sccs_iterative(adj: dict[str, list[str]]) -> list[list[str]]:
    """Iterative Tarjan's SCC algorithm.

    Returns a list of SCCs. Each SCC is a list of node IDs.
    Only SCCs with >= 1 node are returned (all of them).
    The caller is responsible for filtering trivial single-node SCCs
    that have no self-loop.

    Parameters
    ----------
    adj:
        Adjacency dict: node_id -> list of target node IDs.
        All reachable nodes must be present as keys.
    """
    index_counter: list[int] = [0]
    stack: list[str] = []
    lowlink: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    sccs: list[list[str]] = []

    # Iterative DFS state: (node_id, iterator_over_neighbours, stored_index)
    # We simulate the recursive call stack explicitly.

    def _strongconnect(start: str) -> None:
        # Use an explicit work stack to avoid Python recursion limits
        # Each frame: (node_id, neighbour_iterator)
        work_stack: list[tuple[str, Iterator[str]]] = []

        def _visit(v: str) -> None:
            idx = index_counter[0]
            index[v] = idx
            lowlink[v] = idx
            index_counter[0] += 1
            stack.append(v)
            on_stack[v] = True
            work_stack.append((v, iter(adj.get(v, []))))

        _visit(start)

        while work_stack:
            v, neighbours = work_stack[-1]

            try:
                w = next(neighbours)
            except StopIteration:
                # All neighbours of v processed — pop and propagate lowlink
                work_stack.pop()
                if work_stack:
                    parent, _ = work_stack[-1]
                    lowlink[parent] = min(lowlink[parent], lowlink[v])

                # Check if v is an SCC root
                if lowlink[v] == index[v]:
                    scc: list[str] = []
                    while True:
                        w2 = stack.pop()
                        on_stack[w2] = False
                        scc.append(w2)
                        if w2 == v:
                            break
                    sccs.append(scc)
                continue

            if w not in index:
                _visit(w)
            elif on_stack.get(w, False):
                lowlink[v] = min(lowlink[v], index[w])

    for node_id in list(adj.keys()):
        if node_id not in index:
            _strongconnect(node_id)

    return sccs
