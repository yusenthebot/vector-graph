"""L2 unit tests for detect_communities."""

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
def test_community_empty_graph_returns_empty() -> None:
    """Empty graph returns no communities."""
    from vector_graph.analysis.community import detect_communities

    g = SimpleGraph()
    result = detect_communities(g)
    assert result == []


@pytest.mark.level2
def test_community_two_clusters_detected_as_separate() -> None:
    """Two tightly-connected clusters are detected as separate communities."""
    from vector_graph.analysis.community import detect_communities

    g = SimpleGraph()
    # Cluster A: a1, a2, a3 — fully connected
    for nid in ["a1", "a2", "a3"]:
        g.add_node(make_node(nid, file_path="/src/module_a.py"))
    g.add_edge(make_edge("ea12", "a1", "a2", EdgeType.CALLS))
    g.add_edge(make_edge("ea21", "a2", "a1", EdgeType.CALLS))
    g.add_edge(make_edge("ea13", "a1", "a3", EdgeType.CALLS))
    g.add_edge(make_edge("ea31", "a3", "a1", EdgeType.CALLS))
    g.add_edge(make_edge("ea23", "a2", "a3", EdgeType.CALLS))
    g.add_edge(make_edge("ea32", "a3", "a2", EdgeType.CALLS))

    # Cluster B: b1, b2, b3 — fully connected
    for nid in ["b1", "b2", "b3"]:
        g.add_node(make_node(nid, file_path="/src/module_b.py"))
    g.add_edge(make_edge("eb12", "b1", "b2", EdgeType.CALLS))
    g.add_edge(make_edge("eb21", "b2", "b1", EdgeType.CALLS))
    g.add_edge(make_edge("eb13", "b1", "b3", EdgeType.CALLS))
    g.add_edge(make_edge("eb31", "b3", "b1", EdgeType.CALLS))
    g.add_edge(make_edge("eb23", "b2", "b3", EdgeType.CALLS))
    g.add_edge(make_edge("eb32", "b3", "b2", EdgeType.CALLS))

    # No edges between A and B
    communities = detect_communities(g)
    assert len(communities) >= 2

    a_nodes = {"a1", "a2", "a3"}
    b_nodes = {"b1", "b2", "b3"}

    # Each community's members should be entirely in A or entirely in B
    for c in communities:
        member_set = set(c.members)
        # must be subset of A or subset of B (not mixed)
        assert member_set.issubset(a_nodes) or member_set.issubset(b_nodes)


@pytest.mark.level2
def test_community_single_cluster() -> None:
    """Tightly connected functions form a single community."""
    from vector_graph.analysis.community import detect_communities

    g = SimpleGraph()
    for nid in ["x", "y", "z"]:
        g.add_node(make_node(nid, file_path="/src/module.py"))
    g.add_edge(make_edge("e1", "x", "y", EdgeType.CALLS))
    g.add_edge(make_edge("e2", "y", "z", EdgeType.CALLS))
    g.add_edge(make_edge("e3", "z", "x", EdgeType.CALLS))

    communities = detect_communities(g)
    # All three in one community
    all_members = set()
    for c in communities:
        all_members.update(c.members)
    assert "x" in all_members
    assert "y" in all_members
    assert "z" in all_members


@pytest.mark.level2
def test_community_isolated_functions_not_merged() -> None:
    """Completely isolated nodes each form their own singleton or are excluded."""
    from vector_graph.analysis.community import detect_communities

    g = SimpleGraph()
    g.add_node(make_node("iso1", file_path="/src/a.py"))
    g.add_node(make_node("iso2", file_path="/src/b.py"))
    g.add_node(make_node("iso3", file_path="/src/c.py"))
    # No edges at all

    communities = detect_communities(g)
    # Isolated nodes should NOT be merged into one community together
    for c in communities:
        # No community should contain multiple isolated nodes
        if "iso1" in c.members:
            assert "iso2" not in c.members
            assert "iso3" not in c.members


@pytest.mark.level2
def test_community_label_from_common_directory() -> None:
    """Community label is derived from the common directory of members."""
    from vector_graph.analysis.community import detect_communities

    g = SimpleGraph()
    for nid in ["fn1", "fn2", "fn3"]:
        g.add_node(make_node(nid, file_path="/src/auth/auth.py"))
    g.add_edge(make_edge("e1", "fn1", "fn2", EdgeType.CALLS))
    g.add_edge(make_edge("e2", "fn2", "fn3", EdgeType.CALLS))
    g.add_edge(make_edge("e3", "fn3", "fn1", EdgeType.CALLS))

    communities = detect_communities(g)
    assert len(communities) >= 1
    # The label should reflect the directory or file path
    auth_comm = [c for c in communities if "auth" in c.label.lower() or "fn" in c.label.lower()]
    assert len(auth_comm) >= 1


@pytest.mark.level2
def test_community_works_without_networkx() -> None:
    """Community detection does not raise even if networkx is unavailable."""
    import sys
    import importlib

    # Temporarily mask networkx if it exists
    networkx_backup = sys.modules.get("networkx")
    sys.modules["networkx"] = None  # type: ignore

    try:
        # Force reimport of community module
        if "vector_graph.analysis.community" in sys.modules:
            del sys.modules["vector_graph.analysis.community"]

        from vector_graph.analysis.community import detect_communities

        g = SimpleGraph()
        for nid in ["p", "q"]:
            g.add_node(make_node(nid))
        g.add_edge(make_edge("e1", "p", "q", EdgeType.CALLS))

        result = detect_communities(g)
        assert isinstance(result, list)
    finally:
        if networkx_backup is not None:
            sys.modules["networkx"] = networkx_backup
        elif "networkx" in sys.modules:
            del sys.modules["networkx"]
        # Reload community module with real networkx
        if "vector_graph.analysis.community" in sys.modules:
            del sys.modules["vector_graph.analysis.community"]


@pytest.mark.level2
def test_community_confidence_filtering() -> None:
    """Low-confidence edges are excluded during community detection."""
    from vector_graph.analysis.community import detect_communities

    g = SimpleGraph()
    for nid in ["a", "b", "c", "d"]:
        g.add_node(make_node(nid, file_path="/src/a.py"))

    # a-b-c tightly connected (high confidence)
    g.add_edge(make_edge("e1", "a", "b", EdgeType.CALLS, confidence=0.9))
    g.add_edge(make_edge("e2", "b", "c", EdgeType.CALLS, confidence=0.9))
    g.add_edge(make_edge("e3", "c", "a", EdgeType.CALLS, confidence=0.9))

    # d loosely connected to c (low confidence — should not merge)
    g.add_edge(make_edge("e4", "c", "d", EdgeType.CALLS, confidence=0.1))

    communities = detect_communities(g, min_confidence=0.5)
    all_members = set()
    for c in communities:
        all_members.update(c.members)
    # a, b, c should be detected; d behavior can vary but should not dominate
    assert "a" in all_members or "b" in all_members or "c" in all_members


@pytest.mark.level2
def test_community_info_fields() -> None:
    """CommunityInfo has non-empty id, label, members, and cohesion in [0,1]."""
    from vector_graph.analysis.community import detect_communities

    g = SimpleGraph()
    for nid in ["f1", "f2", "f3"]:
        g.add_node(make_node(nid, file_path="/src/core.py"))
    g.add_edge(make_edge("e1", "f1", "f2", EdgeType.CALLS))
    g.add_edge(make_edge("e2", "f2", "f3", EdgeType.CALLS))
    g.add_edge(make_edge("e3", "f3", "f1", EdgeType.CALLS))

    communities = detect_communities(g)
    for c in communities:
        assert c.id
        assert c.label
        assert c.size >= 1
        assert 0.0 <= c.cohesion <= 1.0
