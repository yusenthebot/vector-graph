"""L2 unit tests for find_orphans."""

from __future__ import annotations

import pytest

from vector_graph._types import (
    GraphNode,
    Edge,
    NodeLabel,
    EdgeType,
    NodeProperties,
)


# ---------------------------------------------------------------------------
# Minimal duck-typed graph for testing
# ---------------------------------------------------------------------------

class SimpleGraph:
    """Minimal graph for testing analysis algorithms."""

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

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_node(
    node_id: str,
    name: str | None = None,
    file_path: str = "/src/a.py",
    label: NodeLabel = NodeLabel.FUNCTION,
) -> GraphNode:
    props = NodeProperties(name=name or node_id, file_path=file_path)
    return GraphNode(id=node_id, label=label, properties=props)


def make_edge(
    edge_id: str,
    source: str,
    target: str,
    edge_type: EdgeType = EdgeType.CALLS,
    confidence: float = 0.9,
) -> Edge:
    return Edge(
        id=edge_id,
        source_id=source,
        target_id=target,
        edge_type=edge_type,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.level2
def test_orphan_empty_graph_returns_empty() -> None:
    """Empty graph has no orphans."""
    from vector_graph.analysis.orphan import find_orphans

    g = SimpleGraph()
    result = find_orphans(g)
    assert result == []


@pytest.mark.level2
def test_orphan_function_with_no_callers() -> None:
    """Function with no incoming CALLS edges and no entry-point name is an orphan."""
    from vector_graph.analysis.orphan import find_orphans

    g = SimpleGraph()
    g.add_node(make_node("unused_fn", name="unused_fn"))

    orphans = find_orphans(g)
    ids = {n.id for n in orphans}
    assert "unused_fn" in ids


@pytest.mark.level2
def test_orphan_function_with_caller_not_orphan() -> None:
    """Function that IS called by something else is not an orphan."""
    from vector_graph.analysis.orphan import find_orphans

    g = SimpleGraph()
    g.add_node(make_node("caller_fn", name="caller_fn"))
    g.add_node(make_node("called_fn", name="called_fn"))
    g.add_edge(make_edge("e1", "caller_fn", "called_fn", EdgeType.CALLS))

    orphans = find_orphans(g)
    ids = {n.id for n in orphans}
    assert "called_fn" not in ids


@pytest.mark.level2
def test_orphan_class_with_no_references() -> None:
    """Class with no incoming edges (no CALLS, IMPORTS, EXTENDS, etc.) is orphan."""
    from vector_graph.analysis.orphan import find_orphans

    g = SimpleGraph()
    g.add_node(make_node("UnusedClass", name="UnusedClass", label=NodeLabel.CLASS))

    orphans = find_orphans(g)
    ids = {n.id for n in orphans}
    assert "UnusedClass" in ids


@pytest.mark.level2
def test_orphan_main_function_not_orphan() -> None:
    """Function named 'main' is treated as entry point, not orphan."""
    from vector_graph.analysis.orphan import find_orphans

    g = SimpleGraph()
    g.add_node(make_node("main", name="main"))

    orphans = find_orphans(g)
    ids = {n.id for n in orphans}
    assert "main" not in ids


@pytest.mark.level2
def test_orphan_dunder_init_not_orphan() -> None:
    """__init__ methods are entry points by convention, not orphans."""
    from vector_graph.analysis.orphan import find_orphans

    g = SimpleGraph()
    g.add_node(make_node("MyClass.__init__", name="__init__", label=NodeLabel.METHOD))

    orphans = find_orphans(g)
    ids = {n.id for n in orphans}
    assert "MyClass.__init__" not in ids


@pytest.mark.level2
def test_orphan_test_files_excluded() -> None:
    """Nodes in test files (test_*.py / *_test.py) are excluded from orphan detection."""
    from vector_graph.analysis.orphan import find_orphans

    g = SimpleGraph()
    g.add_node(make_node("test_helper", name="test_helper", file_path="/tests/test_utils.py"))
    g.add_node(make_node("prod_fn", name="prod_fn", file_path="/src/utils.py"))

    orphans = find_orphans(g)
    ids = {n.id for n in orphans}
    assert "test_helper" not in ids
    assert "prod_fn" in ids


@pytest.mark.level2
def test_orphan_imported_function_not_orphan() -> None:
    """Function that is imported (has incoming IMPORTS edge) is not an orphan."""
    from vector_graph.analysis.orphan import find_orphans

    g = SimpleGraph()
    g.add_node(make_node("importer_module", name="importer_module", label=NodeLabel.FILE))
    g.add_node(make_node("exported_fn", name="exported_fn"))
    g.add_edge(make_edge("e1", "importer_module", "exported_fn", EdgeType.IMPORTS))

    orphans = find_orphans(g)
    ids = {n.id for n in orphans}
    assert "exported_fn" not in ids
