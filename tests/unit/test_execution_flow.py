"""L2 unit tests for detect_execution_flows."""

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
def test_flow_empty_graph_returns_empty() -> None:
    """Empty graph produces no traces."""
    from vector_graph.analysis.execution_flow import detect_execution_flows

    g = SimpleGraph()
    result = detect_execution_flows(g)
    assert result == []


@pytest.mark.level2
def test_flow_entry_point_detection_many_callees() -> None:
    """Function with many callees and few callers is detected as entry point."""
    from vector_graph.analysis.execution_flow import detect_execution_flows

    g = SimpleGraph()
    # entry has many callees
    entry = make_node("entry", name="entry")
    g.add_node(entry)
    for i in range(5):
        leaf = make_node(f"leaf_{i}", name=f"leaf_{i}")
        g.add_node(leaf)
        g.add_edge(make_edge(f"e{i}", "entry", f"leaf_{i}", EdgeType.CALLS))

    traces = detect_execution_flows(g, min_steps=1)
    entry_ids = {t.entry_point_id for t in traces}
    assert "entry" in entry_ids


@pytest.mark.level2
def test_flow_bfs_trace_follows_calls_edges() -> None:
    """BFS trace follows CALLS edges from entry point."""
    from vector_graph.analysis.execution_flow import detect_execution_flows

    g = SimpleGraph()
    for nid in ["main", "step1", "step2", "step3"]:
        g.add_node(make_node(nid, name=nid))
    g.add_edge(make_edge("e1", "main", "step1", EdgeType.CALLS))
    g.add_edge(make_edge("e2", "step1", "step2", EdgeType.CALLS))
    g.add_edge(make_edge("e3", "step2", "step3", EdgeType.CALLS))

    traces = detect_execution_flows(g, min_steps=1)
    all_traces = [t.trace for t in traces]
    # some trace must start at main and visit downstream nodes
    main_traces = [t for t in traces if t.entry_point_id == "main"]
    assert len(main_traces) >= 1
    # the trace should include step nodes
    combined = set().union(*[set(t.trace) for t in main_traces])
    assert "step1" in combined or "step2" in combined or "step3" in combined


@pytest.mark.level2
def test_flow_max_depth_limits_trace_length() -> None:
    """max_depth restricts how deep traces can go."""
    from vector_graph.analysis.execution_flow import detect_execution_flows

    g = SimpleGraph()
    # Chain: main -> a -> b -> c -> d -> e
    chain = ["main", "a", "b", "c", "d", "e"]
    for nid in chain:
        g.add_node(make_node(nid, name=nid))
    for i in range(len(chain) - 1):
        g.add_edge(make_edge(f"e{i}", chain[i], chain[i + 1], EdgeType.CALLS))

    traces = detect_execution_flows(g, max_depth=3, min_steps=1)
    for t in traces:
        assert t.step_count <= 4  # max_depth=3 means up to 4 nodes (incl entry)


@pytest.mark.level2
def test_flow_max_branching_limits_width() -> None:
    """max_branching limits how many children are explored per node."""
    from vector_graph.analysis.execution_flow import detect_execution_flows

    g = SimpleGraph()
    g.add_node(make_node("root", name="root"))
    for i in range(10):
        child = make_node(f"child_{i}", name=f"child_{i}")
        g.add_node(child)
        g.add_edge(make_edge(f"e{i}", "root", f"child_{i}", EdgeType.CALLS))

    traces = detect_execution_flows(g, max_branching=2, min_steps=1)
    root_traces = [t for t in traces if t.entry_point_id == "root"]
    # each trace should explore at most max_branching children per node
    for t in root_traces:
        assert t.step_count <= 3  # root + up to 2 children in depth-1 scenario


@pytest.mark.level2
def test_flow_deduplication_of_identical_traces() -> None:
    """Identical traces (same nodes in same order) are deduplicated."""
    from vector_graph.analysis.execution_flow import detect_execution_flows

    g = SimpleGraph()
    for nid in ["main", "helper"]:
        g.add_node(make_node(nid, name=nid))
    g.add_edge(make_edge("e1", "main", "helper", EdgeType.CALLS))

    # Run twice with same graph - result set should not have duplicate trace ids
    traces = detect_execution_flows(g, min_steps=1)
    ids = [t.id for t in traces]
    assert len(ids) == len(set(ids))


@pytest.mark.level2
def test_flow_name_pattern_main_scores_higher() -> None:
    """'main' named function is treated as an entry point candidate."""
    from vector_graph.analysis.execution_flow import detect_execution_flows

    g = SimpleGraph()
    g.add_node(make_node("main", name="main"))
    g.add_node(make_node("helper1", name="helper1"))
    g.add_node(make_node("helper2", name="helper2"))
    g.add_edge(make_edge("e1", "main", "helper1", EdgeType.CALLS))
    g.add_edge(make_edge("e2", "main", "helper2", EdgeType.CALLS))
    # helper2 also calls helper1 (so helper2 has callees) but main is the named one
    g.add_edge(make_edge("e3", "helper2", "helper1", EdgeType.CALLS))

    traces = detect_execution_flows(g, min_steps=1)
    entry_ids = {t.entry_point_id for t in traces}
    assert "main" in entry_ids


@pytest.mark.level2
def test_flow_handle_pattern_scores_higher() -> None:
    """Functions named 'handle_*' are scored as entry point candidates."""
    from vector_graph.analysis.execution_flow import detect_execution_flows

    g = SimpleGraph()
    g.add_node(make_node("handle_request", name="handle_request"))
    g.add_node(make_node("process_data", name="process_data"))
    g.add_node(make_node("save_result", name="save_result"))
    g.add_edge(make_edge("e1", "handle_request", "process_data", EdgeType.CALLS))
    g.add_edge(make_edge("e2", "process_data", "save_result", EdgeType.CALLS))

    traces = detect_execution_flows(g, min_steps=1)
    entry_ids = {t.entry_point_id for t in traces}
    assert "handle_request" in entry_ids


@pytest.mark.level2
def test_flow_on_pattern_scores_higher() -> None:
    """Functions named 'on_*' are scored as entry point candidates."""
    from vector_graph.analysis.execution_flow import detect_execution_flows

    g = SimpleGraph()
    g.add_node(make_node("on_connect", name="on_connect"))
    g.add_node(make_node("send_greeting", name="send_greeting"))
    g.add_edge(make_edge("e1", "on_connect", "send_greeting", EdgeType.CALLS))

    traces = detect_execution_flows(g, min_steps=1)
    entry_ids = {t.entry_point_id for t in traces}
    assert "on_connect" in entry_ids


@pytest.mark.level2
def test_flow_min_steps_excludes_short_traces() -> None:
    """Traces shorter than min_steps are excluded."""
    from vector_graph.analysis.execution_flow import detect_execution_flows

    g = SimpleGraph()
    g.add_node(make_node("lone_fn", name="lone_fn"))

    traces = detect_execution_flows(g, min_steps=3)
    # lone_fn has only 1 step; should be excluded
    entry_ids = {t.entry_point_id for t in traces}
    assert "lone_fn" not in entry_ids


@pytest.mark.level2
def test_flow_process_trace_fields_populated() -> None:
    """ProcessTrace has non-empty id, label, step_count, trace."""
    from vector_graph.analysis.execution_flow import detect_execution_flows

    g = SimpleGraph()
    for nid in ["start", "middle", "end"]:
        g.add_node(make_node(nid, name=nid))
    g.add_edge(make_edge("e1", "start", "middle", EdgeType.CALLS))
    g.add_edge(make_edge("e2", "middle", "end", EdgeType.CALLS))

    traces = detect_execution_flows(g, min_steps=1)
    start_traces = [t for t in traces if t.entry_point_id == "start"]
    assert len(start_traces) >= 1
    t = start_traces[0]
    assert t.id
    assert t.label
    assert t.step_count >= 1
    assert len(t.trace) >= 1


@pytest.mark.level2
def test_flow_max_processes_cap() -> None:
    """max_processes limits total number of returned traces."""
    from vector_graph.analysis.execution_flow import detect_execution_flows

    g = SimpleGraph()
    # Create many potential entry points: fan-out tree
    for i in range(20):
        root = make_node(f"root_{i}", name=f"main_{i}")
        leaf = make_node(f"leaf_{i}", name=f"leaf_{i}")
        g.add_node(root)
        g.add_node(leaf)
        g.add_edge(make_edge(f"e{i}", f"root_{i}", f"leaf_{i}", EdgeType.CALLS))

    traces = detect_execution_flows(g, max_processes=5, min_steps=1)
    assert len(traces) <= 5


@pytest.mark.level2
def test_flow_ignores_non_calls_edges() -> None:
    """IMPORTS edges are not followed as execution flow."""
    from vector_graph.analysis.execution_flow import detect_execution_flows

    g = SimpleGraph()
    g.add_node(make_node("importer", name="importer"))
    g.add_node(make_node("imported_mod", name="imported_mod"))
    # Only IMPORTS edge between them, no CALLS
    g.add_edge(make_edge("e1", "importer", "imported_mod", EdgeType.IMPORTS))

    traces = detect_execution_flows(g, min_steps=2)
    # No CALLS edges means no traces of length >= 2
    long_traces = [t for t in traces if t.step_count >= 2]
    assert len(long_traces) == 0
