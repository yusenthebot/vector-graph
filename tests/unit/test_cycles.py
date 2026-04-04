"""Unit tests for dependency cycle detection (Tarjan's SCC)."""

from __future__ import annotations

import pytest

from vector_graph._types import (
    Edge,
    EdgeType,
    GraphNode,
    NodeLabel,
    NodeProperties,
)


# ---------------------------------------------------------------------------
# Minimal duck-typed graph for testing
# ---------------------------------------------------------------------------


class SimpleGraph:
    """Minimal duck-typed graph satisfying GraphProtocol for testing."""

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, Edge] = {}

    def add_node(self, node: GraphNode) -> None:
        self._nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        self._edges[edge.id] = edge

    def get_node(self, node_id: str) -> GraphNode | None:
        return self._nodes.get(node_id)

    def iter_nodes(self):
        return iter(self._nodes.values())

    def iter_edges(self):
        return iter(self._edges.values())

    def get_edges_from(self, source_id: str) -> list[Edge]:
        return [e for e in self._edges.values() if e.source_id == source_id]

    def get_edges_to(self, target_id: str) -> list[Edge]:
        return [e for e in self._edges.values() if e.target_id == target_id]

    def get_nodes_by_label(self, label: NodeLabel) -> list[GraphNode]:
        return [n for n in self._nodes.values() if n.label == label]

    def get_nodes_by_file(self, file_path: str) -> list[GraphNode]:
        return [n for n in self._nodes.values() if n.properties.file_path == file_path]

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)


# ---------------------------------------------------------------------------
# Helpers to build test nodes/edges
# ---------------------------------------------------------------------------


def _make_fn(node_id: str, name: str, file_path: str = "a.py") -> GraphNode:
    """Create a FUNCTION node."""
    return GraphNode(
        id=node_id,
        label=NodeLabel.FUNCTION,
        properties=NodeProperties(name=name, file_path=file_path),
    )


def _make_edge(
    edge_id: str,
    src: str,
    tgt: str,
    edge_type: EdgeType = EdgeType.CALLS,
) -> Edge:
    return Edge(id=edge_id, source_id=src, target_id=tgt, edge_type=edge_type)


# ---------------------------------------------------------------------------
# Tests: CycleInfo dataclass
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_cycle_info_frozen() -> None:
    """CycleInfo is a frozen dataclass — mutation raises FrozenInstanceError."""
    from vector_graph.analysis.cycles import CycleInfo

    cycle = CycleInfo(
        node_ids=("a", "b"),
        node_names=("alpha", "beta"),
        edge_types=("CALLS",),
        length=2,
    )
    with pytest.raises((AttributeError, TypeError)):
        cycle.length = 99  # type: ignore[misc]


@pytest.mark.level2
def test_cycle_info_stores_fields() -> None:
    """CycleInfo stores all fields correctly."""
    from vector_graph.analysis.cycles import CycleInfo

    cycle = CycleInfo(
        node_ids=("x", "y", "z"),
        node_names=("X", "Y", "Z"),
        edge_types=("CALLS", "IMPORTS"),
        length=3,
    )
    assert cycle.node_ids == ("x", "y", "z")
    assert cycle.node_names == ("X", "Y", "Z")
    assert cycle.edge_types == ("CALLS", "IMPORTS")
    assert cycle.length == 3


# ---------------------------------------------------------------------------
# Tests: acyclic graph
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_detect_cycles_no_cycles() -> None:
    """Acyclic graph returns an empty list."""
    from vector_graph.analysis.cycles import detect_cycles

    g = SimpleGraph()
    a = _make_fn("a", "alpha")
    b = _make_fn("b", "beta")
    c = _make_fn("c", "gamma")
    g.add_node(a)
    g.add_node(b)
    g.add_node(c)
    # A -> B -> C (no back edge)
    g.add_edge(_make_edge("e1", "a", "b"))
    g.add_edge(_make_edge("e2", "b", "c"))

    cycles = detect_cycles(g)
    assert cycles == []


# ---------------------------------------------------------------------------
# Tests: simple 2-node cycle
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_detect_cycles_simple() -> None:
    """A->B->A returns one cycle of length 2 containing both nodes."""
    from vector_graph.analysis.cycles import detect_cycles

    g = SimpleGraph()
    a = _make_fn("a", "alpha")
    b = _make_fn("b", "beta")
    g.add_node(a)
    g.add_node(b)
    g.add_edge(_make_edge("e1", "a", "b"))
    g.add_edge(_make_edge("e2", "b", "a"))

    cycles = detect_cycles(g)
    assert len(cycles) == 1
    cycle = cycles[0]
    assert cycle.length == 2
    node_id_set = set(cycle.node_ids)
    assert "a" in node_id_set
    assert "b" in node_id_set


# ---------------------------------------------------------------------------
# Tests: triangle cycle
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_detect_cycles_triangle() -> None:
    """A->B->C->A returns one cycle of length 3 containing all three nodes."""
    from vector_graph.analysis.cycles import detect_cycles

    g = SimpleGraph()
    a = _make_fn("a", "alpha")
    b = _make_fn("b", "beta")
    c = _make_fn("c", "gamma")
    g.add_node(a)
    g.add_node(b)
    g.add_node(c)
    g.add_edge(_make_edge("e1", "a", "b"))
    g.add_edge(_make_edge("e2", "b", "c"))
    g.add_edge(_make_edge("e3", "c", "a"))

    cycles = detect_cycles(g)
    assert len(cycles) == 1
    cycle = cycles[0]
    assert cycle.length == 3
    node_id_set = set(cycle.node_ids)
    assert "a" in node_id_set
    assert "b" in node_id_set
    assert "c" in node_id_set


# ---------------------------------------------------------------------------
# Tests: multiple independent cycles
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_detect_cycles_multiple() -> None:
    """Two independent cycles are detected separately."""
    from vector_graph.analysis.cycles import detect_cycles

    g = SimpleGraph()
    # Cycle 1: A <-> B
    a = _make_fn("a", "alpha")
    b = _make_fn("b", "beta")
    # Cycle 2: C <-> D <-> E
    c = _make_fn("c", "gamma", "b.py")
    d = _make_fn("d", "delta", "b.py")
    e = _make_fn("e", "epsilon", "b.py")

    for node in (a, b, c, d, e):
        g.add_node(node)

    g.add_edge(_make_edge("e1", "a", "b"))
    g.add_edge(_make_edge("e2", "b", "a"))
    g.add_edge(_make_edge("e3", "c", "d"))
    g.add_edge(_make_edge("e4", "d", "e"))
    g.add_edge(_make_edge("e5", "e", "c"))

    cycles = detect_cycles(g)
    assert len(cycles) == 2

    # Verify both cycles are present by checking node sets
    cycle_node_sets = [frozenset(cycle.node_ids) for cycle in cycles]
    assert frozenset({"a", "b"}) in cycle_node_sets
    assert frozenset({"c", "d", "e"}) in cycle_node_sets


# ---------------------------------------------------------------------------
# Tests: structural edges don't create cycles
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_detect_cycles_ignores_structural_edges() -> None:
    """CONTAINS and HAS_METHOD edges are not cycle edges."""
    from vector_graph.analysis.cycles import detect_cycles

    g = SimpleGraph()
    a = _make_fn("a", "alpha")
    b = _make_fn("b", "beta")
    g.add_node(a)
    g.add_node(b)
    # Only structural edges — not cycle-forming
    g.add_edge(_make_edge("e1", "a", "b", EdgeType.CONTAINS))
    g.add_edge(_make_edge("e2", "b", "a", EdgeType.HAS_METHOD))

    cycles = detect_cycles(g)
    assert cycles == []


@pytest.mark.level2
def test_detect_cycles_ignores_defines_edge() -> None:
    """DEFINES edges are not cycle edges."""
    from vector_graph.analysis.cycles import detect_cycles

    g = SimpleGraph()
    a = _make_fn("a", "alpha")
    b = _make_fn("b", "beta")
    g.add_node(a)
    g.add_node(b)
    g.add_edge(_make_edge("e1", "a", "b", EdgeType.DEFINES))
    g.add_edge(_make_edge("e2", "b", "a", EdgeType.DEFINES))

    cycles = detect_cycles(g)
    assert cycles == []


# ---------------------------------------------------------------------------
# Tests: self-loop
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_detect_cycles_self_loop() -> None:
    """A->A is a cycle of length 1 (self-referencing function)."""
    from vector_graph.analysis.cycles import detect_cycles

    g = SimpleGraph()
    a = _make_fn("a", "recursive_fn")
    g.add_node(a)
    g.add_edge(_make_edge("e1", "a", "a"))

    cycles = detect_cycles(g)
    assert len(cycles) == 1
    cycle = cycles[0]
    assert cycle.length == 1
    assert "a" in cycle.node_ids


# ---------------------------------------------------------------------------
# Tests: IMPORTS cycle
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_detect_cycles_imports_edge() -> None:
    """IMPORTS edges are counted as cycle edges."""
    from vector_graph.analysis.cycles import detect_cycles

    g = SimpleGraph()
    a = GraphNode(
        id="a", label=NodeLabel.MODULE,
        properties=NodeProperties(name="module_a", file_path="a.py"),
    )
    b = GraphNode(
        id="b", label=NodeLabel.MODULE,
        properties=NodeProperties(name="module_b", file_path="b.py"),
    )
    g.add_node(a)
    g.add_node(b)
    # Circular import: A imports B, B imports A
    g.add_edge(_make_edge("e1", "a", "b", EdgeType.IMPORTS))
    g.add_edge(_make_edge("e2", "b", "a", EdgeType.IMPORTS))

    cycles = detect_cycles(g)
    assert len(cycles) == 1


# ---------------------------------------------------------------------------
# Tests: EXTENDS cycle
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_detect_cycles_extends_edge() -> None:
    """EXTENDS edges are counted as cycle edges."""
    from vector_graph.analysis.cycles import detect_cycles

    g = SimpleGraph()
    a = GraphNode(
        id="a", label=NodeLabel.CLASS,
        properties=NodeProperties(name="ClassA", file_path="a.py"),
    )
    b = GraphNode(
        id="b", label=NodeLabel.CLASS,
        properties=NodeProperties(name="ClassB", file_path="a.py"),
    )
    g.add_node(a)
    g.add_node(b)
    g.add_edge(_make_edge("e1", "a", "b", EdgeType.EXTENDS))
    g.add_edge(_make_edge("e2", "b", "a", EdgeType.EXTENDS))

    cycles = detect_cycles(g)
    assert len(cycles) == 1


# ---------------------------------------------------------------------------
# Tests: empty graph
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_detect_cycles_empty_graph() -> None:
    """Empty graph returns empty list."""
    from vector_graph.analysis.cycles import detect_cycles

    g = SimpleGraph()
    cycles = detect_cycles(g)
    assert cycles == []


# ---------------------------------------------------------------------------
# Tests: no edges
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_detect_cycles_nodes_no_edges() -> None:
    """Graph with nodes but no edges has no cycles."""
    from vector_graph.analysis.cycles import detect_cycles

    g = SimpleGraph()
    g.add_node(_make_fn("a", "alpha"))
    g.add_node(_make_fn("b", "beta"))
    g.add_node(_make_fn("c", "gamma"))

    cycles = detect_cycles(g)
    assert cycles == []


# ---------------------------------------------------------------------------
# Tests: mixed structural and cycle edges
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_detect_cycles_mixed_edges_only_calls_form_cycle() -> None:
    """Only CALLS edges (not CONTAINS) form the cycle."""
    from vector_graph.analysis.cycles import detect_cycles

    g = SimpleGraph()
    a = _make_fn("a", "alpha")
    b = _make_fn("b", "beta")
    c = _make_fn("c", "gamma")
    g.add_node(a)
    g.add_node(b)
    g.add_node(c)
    # Real cycle via CALLS: A -> B -> A
    g.add_edge(_make_edge("e1", "a", "b", EdgeType.CALLS))
    g.add_edge(_make_edge("e2", "b", "a", EdgeType.CALLS))
    # Structural edge: C -> A (CONTAINS, not a cycle edge)
    g.add_edge(_make_edge("e3", "c", "a", EdgeType.CONTAINS))

    cycles = detect_cycles(g)
    assert len(cycles) == 1
    node_id_set = set(cycles[0].node_ids)
    assert "a" in node_id_set
    assert "b" in node_id_set
    assert "c" not in node_id_set
