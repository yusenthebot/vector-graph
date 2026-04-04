"""Tests for vector_graph.analysis.export."""

from __future__ import annotations

import json

import pytest

from vector_graph._types import Edge, EdgeType, GraphNode, NodeLabel, NodeProperties
from vector_graph.graph.knowledge_graph import KnowledgeGraph


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_graph() -> KnowledgeGraph:
    """Small graph for export testing."""
    g = KnowledgeGraph()
    props_a = NodeProperties(name="foo", file_path="/src/a.py", start_line=1, end_line=10)
    props_b = NodeProperties(name="bar", file_path="/src/a.py", start_line=12, end_line=20)
    props_c = NodeProperties(name="MyClass", file_path="/src/b.py", start_line=1, end_line=50)

    g.add_node(GraphNode(id="n1", label=NodeLabel.FUNCTION, properties=props_a))
    g.add_node(GraphNode(id="n2", label=NodeLabel.FUNCTION, properties=props_b))
    g.add_node(GraphNode(id="n3", label=NodeLabel.CLASS, properties=props_c))

    g.add_edge(Edge(id="e1", source_id="n1", target_id="n2", edge_type=EdgeType.CALLS, confidence=0.9))
    g.add_edge(Edge(id="e2", source_id="n3", target_id="n1", edge_type=EdgeType.CONTAINS, confidence=1.0))

    return g


@pytest.fixture
def empty_graph() -> KnowledgeGraph:
    return KnowledgeGraph()


# ---------------------------------------------------------------------------
# JSON export tests
# ---------------------------------------------------------------------------


def test_export_json_valid(sample_graph: KnowledgeGraph) -> None:
    """export_json produces syntactically valid JSON."""
    from vector_graph.analysis.export import export_json

    output = export_json(sample_graph)
    # Should not raise
    parsed = json.loads(output)
    assert parsed is not None


def test_export_json_structure(sample_graph: KnowledgeGraph) -> None:
    """JSON has 'nodes' and 'edges' as top-level keys."""
    from vector_graph.analysis.export import export_json

    parsed = json.loads(export_json(sample_graph))
    assert "nodes" in parsed
    assert "edges" in parsed
    assert isinstance(parsed["nodes"], list)
    assert isinstance(parsed["edges"], list)


def test_export_json_node_count(sample_graph: KnowledgeGraph) -> None:
    """nodes array length matches graph.node_count."""
    from vector_graph.analysis.export import export_json

    parsed = json.loads(export_json(sample_graph))
    assert len(parsed["nodes"]) == sample_graph.node_count


def test_export_json_edge_count(sample_graph: KnowledgeGraph) -> None:
    """edges array length matches graph.edge_count."""
    from vector_graph.analysis.export import export_json

    parsed = json.loads(export_json(sample_graph))
    assert len(parsed["edges"]) == sample_graph.edge_count


def test_export_json_roundtrip(sample_graph: KnowledgeGraph) -> None:
    """Load JSON, verify node ids and edge ids match original."""
    from vector_graph.analysis.export import export_json

    parsed = json.loads(export_json(sample_graph))

    node_ids = {n["id"] for n in parsed["nodes"]}
    edge_ids = {e["id"] for e in parsed["edges"]}

    assert node_ids == {"n1", "n2", "n3"}
    assert edge_ids == {"e1", "e2"}


def test_export_json_node_fields(sample_graph: KnowledgeGraph) -> None:
    """Each node has id, label, properties.name, properties.file_path."""
    from vector_graph.analysis.export import export_json

    parsed = json.loads(export_json(sample_graph))
    for node in parsed["nodes"]:
        assert "id" in node
        assert "label" in node
        assert "properties" in node
        assert "name" in node["properties"]
        assert "file_path" in node["properties"]


def test_export_json_edge_fields(sample_graph: KnowledgeGraph) -> None:
    """Each edge has id, source_id, target_id, edge_type, confidence."""
    from vector_graph.analysis.export import export_json

    parsed = json.loads(export_json(sample_graph))
    for edge in parsed["edges"]:
        assert "id" in edge
        assert "source_id" in edge
        assert "target_id" in edge
        assert "edge_type" in edge
        assert "confidence" in edge


def test_export_json_empty_graph(empty_graph: KnowledgeGraph) -> None:
    """Empty graph produces {'nodes': [], 'edges': []}."""
    from vector_graph.analysis.export import export_json

    parsed = json.loads(export_json(empty_graph))
    assert parsed == {"nodes": [], "edges": []}


# ---------------------------------------------------------------------------
# DOT export tests
# ---------------------------------------------------------------------------


def test_export_dot_valid(sample_graph: KnowledgeGraph) -> None:
    """export_dot produces a string starting with 'digraph'."""
    from vector_graph.analysis.export import export_dot

    output = export_dot(sample_graph)
    assert isinstance(output, str)
    assert output.strip().startswith("digraph")


def test_export_dot_contains_nodes(sample_graph: KnowledgeGraph) -> None:
    """DOT output contains node IDs with labels."""
    from vector_graph.analysis.export import export_dot

    output = export_dot(sample_graph)
    assert '"n1"' in output
    assert '"n2"' in output
    assert '"n3"' in output
    # Labels should appear too
    assert "foo" in output
    assert "bar" in output
    assert "MyClass" in output


def test_export_dot_contains_edges(sample_graph: KnowledgeGraph) -> None:
    """DOT output contains arrow notation for edges."""
    from vector_graph.analysis.export import export_dot

    output = export_dot(sample_graph)
    # n1 -> n2 (CALLS) and n3 -> n1 (CONTAINS)
    assert '"n1" -> "n2"' in output
    assert '"n3" -> "n1"' in output


def test_export_dot_empty_graph(empty_graph: KnowledgeGraph) -> None:
    """Empty graph produces valid minimal DOT (digraph G { })."""
    from vector_graph.analysis.export import export_dot

    output = export_dot(empty_graph)
    assert output.strip().startswith("digraph")
    assert "}" in output
    # No node or edge lines between braces
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    inner_lines = lines[1:-1]  # strip "digraph G {" and "}"
    assert inner_lines == []
