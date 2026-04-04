"""L2 unit tests for analyze_impact (blast radius analysis)."""

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
# Minimal duck-typed graph for testing (no dependency on Alpha's KnowledgeGraph)
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
    file_path: str = "/src/a.py",
    label: NodeLabel = NodeLabel.FUNCTION,
    name: str | None = None,
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
def test_impact_empty_graph() -> None:
    """Empty graph returns empty result with no entries."""
    from vector_graph.analysis.impact import analyze_impact

    g = SimpleGraph()
    result = analyze_impact(g, "nonexistent")
    assert result.impacted_count == 0
    assert result.entries == ()


@pytest.mark.level2
def test_impact_isolated_node_no_edges() -> None:
    """A node with no edges returns empty impact."""
    from vector_graph.analysis.impact import analyze_impact

    g = SimpleGraph()
    g.add_node(make_node("fn_a", name="fn_a"))
    result = analyze_impact(g, "fn_a")
    assert result.impacted_count == 0


@pytest.mark.level2
def test_impact_upstream_direct_caller() -> None:
    """Upstream finds direct callers of the target."""
    from vector_graph.analysis.impact import analyze_impact

    g = SimpleGraph()
    g.add_node(make_node("caller", name="caller"))
    g.add_node(make_node("target", name="target"))
    g.add_edge(make_edge("e1", "caller", "target", EdgeType.CALLS))

    result = analyze_impact(g, "target", direction="upstream")
    ids = {e.node_id for e in result.entries}
    assert "caller" in ids
    assert result.direction == "upstream"


@pytest.mark.level2
def test_impact_downstream_direct_callee() -> None:
    """Downstream finds functions called by the target."""
    from vector_graph.analysis.impact import analyze_impact

    g = SimpleGraph()
    g.add_node(make_node("target", name="target"))
    g.add_node(make_node("callee", name="callee"))
    g.add_edge(make_edge("e1", "target", "callee", EdgeType.CALLS))

    result = analyze_impact(g, "target", direction="downstream")
    ids = {e.node_id for e in result.entries}
    assert "callee" in ids


@pytest.mark.level2
def test_impact_upstream_bfs_multi_hop() -> None:
    """BFS finds indirect callers across multiple hops."""
    from vector_graph.analysis.impact import analyze_impact

    g = SimpleGraph()
    for nid in ["a", "b", "c", "target"]:
        g.add_node(make_node(nid, name=nid))
    g.add_edge(make_edge("e1", "a", "b", EdgeType.CALLS))
    g.add_edge(make_edge("e2", "b", "c", EdgeType.CALLS))
    g.add_edge(make_edge("e3", "c", "target", EdgeType.CALLS))

    result = analyze_impact(g, "target", direction="upstream", max_depth=5)
    ids = {e.node_id for e in result.entries}
    assert "c" in ids  # depth 1
    assert "b" in ids  # depth 2
    assert "a" in ids  # depth 3


@pytest.mark.level2
def test_impact_depth_limiting_max1() -> None:
    """max_depth=1 returns only direct neighbors."""
    from vector_graph.analysis.impact import analyze_impact

    g = SimpleGraph()
    for nid in ["a", "b", "target"]:
        g.add_node(make_node(nid, name=nid))
    g.add_edge(make_edge("e1", "b", "target", EdgeType.CALLS))
    g.add_edge(make_edge("e2", "a", "b", EdgeType.CALLS))

    result = analyze_impact(g, "target", direction="upstream", max_depth=1)
    ids = {e.node_id for e in result.entries}
    assert "b" in ids
    assert "a" not in ids  # too deep


@pytest.mark.level2
def test_impact_depth_limiting_max3_vs_full() -> None:
    """max_depth=3 vs unlimited returns different results on deep chain."""
    from vector_graph.analysis.impact import analyze_impact

    g = SimpleGraph()
    # Chain: a->b->c->d->e->target (5 hops upstream)
    nodes = ["a", "b", "c", "d", "e", "target"]
    for nid in nodes:
        g.add_node(make_node(nid, name=nid))
    for i in range(len(nodes) - 1):
        g.add_edge(make_edge(f"e{i}", nodes[i], nodes[i + 1], EdgeType.CALLS))

    shallow = analyze_impact(g, "target", direction="upstream", max_depth=2)
    deep = analyze_impact(g, "target", direction="upstream", max_depth=10)

    shallow_ids = {e.node_id for e in shallow.entries}
    deep_ids = {e.node_id for e in deep.entries}

    # Chain: a->b->c->d->e->target
    # upstream from target: e=depth1, d=depth2, c=depth3, b=depth4, a=depth5
    assert "e" in shallow_ids  # depth 1 (direct caller)
    assert "d" in shallow_ids  # depth 2 (last allowed with max_depth=2)
    assert "c" not in shallow_ids  # depth 3 — beyond max_depth=2
    assert "a" not in shallow_ids
    assert "a" in deep_ids


@pytest.mark.level2
def test_impact_confidence_filtering() -> None:
    """min_confidence filters out low-confidence edges."""
    from vector_graph.analysis.impact import analyze_impact

    g = SimpleGraph()
    g.add_node(make_node("target", name="target"))
    g.add_node(make_node("high_conf", name="high_conf"))
    g.add_node(make_node("low_conf", name="low_conf"))
    g.add_edge(make_edge("e1", "high_conf", "target", EdgeType.CALLS, confidence=0.9))
    g.add_edge(make_edge("e2", "low_conf", "target", EdgeType.CALLS, confidence=0.3))

    result = analyze_impact(g, "target", direction="upstream", min_confidence=0.8)
    ids = {e.node_id for e in result.entries}
    assert "high_conf" in ids
    assert "low_conf" not in ids


@pytest.mark.level2
def test_impact_risk_scoring_high_when_direct_callers() -> None:
    """Many direct (depth=1) callers yields HIGH or CRITICAL risk."""
    from vector_graph.analysis.impact import analyze_impact

    g = SimpleGraph()
    g.add_node(make_node("target", name="target"))
    for i in range(6):
        nid = f"caller_{i}"
        g.add_node(make_node(nid, name=nid))
        g.add_edge(make_edge(f"e{i}", nid, "target", EdgeType.CALLS))

    result = analyze_impact(g, "target", direction="upstream")
    assert result.risk in ("HIGH", "CRITICAL")


@pytest.mark.level2
def test_impact_risk_scoring_low_when_few_entries() -> None:
    """Zero or one impacted node yields LOW risk."""
    from vector_graph.analysis.impact import analyze_impact

    g = SimpleGraph()
    g.add_node(make_node("target", name="target"))
    result = analyze_impact(g, "target", direction="upstream")
    assert result.risk == "LOW"


@pytest.mark.level2
def test_impact_circular_chain_no_infinite_loop() -> None:
    """Circular call chain terminates without infinite loop."""
    from vector_graph.analysis.impact import analyze_impact

    g = SimpleGraph()
    for nid in ["a", "b", "c"]:
        g.add_node(make_node(nid, name=nid))
    g.add_edge(make_edge("e1", "a", "b", EdgeType.CALLS))
    g.add_edge(make_edge("e2", "b", "c", EdgeType.CALLS))
    g.add_edge(make_edge("e3", "c", "a", EdgeType.CALLS))  # cycle back

    # Should not hang; result is finite
    result = analyze_impact(g, "a", direction="upstream", max_depth=10)
    assert result.impacted_count < 100  # sanity bound


@pytest.mark.level2
def test_impact_target_node_not_in_entries() -> None:
    """The target node itself is not included in the result entries."""
    from vector_graph.analysis.impact import analyze_impact

    g = SimpleGraph()
    g.add_node(make_node("target", name="target"))
    g.add_node(make_node("caller", name="caller"))
    g.add_edge(make_edge("e1", "caller", "target", EdgeType.CALLS))

    result = analyze_impact(g, "target", direction="upstream")
    ids = {e.node_id for e in result.entries}
    assert "target" not in ids


@pytest.mark.level2
def test_impact_result_has_correct_metadata() -> None:
    """ImpactResult carries correct target_name and target_file."""
    from vector_graph.analysis.impact import analyze_impact

    g = SimpleGraph()
    g.add_node(make_node("my_fn", file_path="/src/myfile.py", name="my_fn"))
    result = analyze_impact(g, "my_fn", direction="downstream")
    assert result.target_name == "my_fn"
    assert result.target_file == "/src/myfile.py"


@pytest.mark.level2
def test_impact_relation_types_filter() -> None:
    """relation_types restricts which edge types are traversed."""
    from vector_graph.analysis.impact import analyze_impact

    g = SimpleGraph()
    g.add_node(make_node("target", name="target"))
    g.add_node(make_node("caller", name="caller"))
    g.add_node(make_node("importer", name="importer"))
    g.add_edge(make_edge("e1", "caller", "target", EdgeType.CALLS))
    g.add_edge(make_edge("e2", "importer", "target", EdgeType.IMPORTS))

    result = analyze_impact(
        g, "target", direction="upstream",
        relation_types={EdgeType.CALLS},
    )
    ids = {e.node_id for e in result.entries}
    assert "caller" in ids
    assert "importer" not in ids


@pytest.mark.level2
def test_impact_entry_fields_populated() -> None:
    """Each ImpactEntry has depth, edge_type, confidence populated."""
    from vector_graph.analysis.impact import analyze_impact

    g = SimpleGraph()
    g.add_node(make_node("target", name="target"))
    g.add_node(make_node("caller", name="caller"))
    g.add_edge(make_edge("e1", "caller", "target", EdgeType.CALLS, confidence=0.95))

    result = analyze_impact(g, "target", direction="upstream")
    assert len(result.entries) == 1
    entry = result.entries[0]
    assert entry.depth == 1
    assert entry.edge_type == EdgeType.CALLS.value
    assert entry.confidence == 0.95


@pytest.mark.level2
def test_impact_downstream_multi_hop() -> None:
    """Downstream BFS follows outgoing edges through multiple hops."""
    from vector_graph.analysis.impact import analyze_impact

    g = SimpleGraph()
    for nid in ["entry", "middle", "leaf"]:
        g.add_node(make_node(nid, name=nid))
    g.add_edge(make_edge("e1", "entry", "middle", EdgeType.CALLS))
    g.add_edge(make_edge("e2", "middle", "leaf", EdgeType.CALLS))

    result = analyze_impact(g, "entry", direction="downstream", max_depth=5)
    ids = {e.node_id for e in result.entries}
    assert "middle" in ids
    assert "leaf" in ids
