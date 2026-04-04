"""L0 unit tests for KnowledgeGraph."""

from __future__ import annotations

import pytest

from vector_graph._types import (
    GraphNode,
    Edge,
    NodeLabel,
    EdgeType,
    NodeProperties,
)
from vector_graph.graph.knowledge_graph import KnowledgeGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_node(node_id: str, file_path: str = "/src/a.py", label: NodeLabel = NodeLabel.FUNCTION) -> GraphNode:
    props = NodeProperties(name=node_id, file_path=file_path)
    return GraphNode(id=node_id, label=label, properties=props)


def make_edge(edge_id: str, source: str, target: str, edge_type: EdgeType = EdgeType.CALLS) -> Edge:
    return Edge(id=edge_id, source_id=source, target_id=target, edge_type=edge_type)


# ---------------------------------------------------------------------------
# add_node / get_node / node_count
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_add_and_get_node() -> None:
    kg = KnowledgeGraph()
    node = make_node("n1")
    kg.add_node(node)
    assert kg.get_node("n1") is node


@pytest.mark.level0
def test_node_count_empty() -> None:
    kg = KnowledgeGraph()
    assert kg.node_count == 0


@pytest.mark.level0
def test_node_count_after_adds() -> None:
    kg = KnowledgeGraph()
    kg.add_node(make_node("n1"))
    kg.add_node(make_node("n2"))
    assert kg.node_count == 2


@pytest.mark.level0
def test_get_node_missing_returns_none() -> None:
    kg = KnowledgeGraph()
    assert kg.get_node("nope") is None


@pytest.mark.level0
def test_duplicate_node_id_overwrites() -> None:
    kg = KnowledgeGraph()
    n1 = make_node("n1", file_path="/src/a.py")
    n2 = make_node("n1", file_path="/src/b.py")
    kg.add_node(n1)
    kg.add_node(n2)
    assert kg.node_count == 1
    assert kg.get_node("n1") is n2


# ---------------------------------------------------------------------------
# add_edge / get_edge / edge_count
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_add_and_get_edge() -> None:
    kg = KnowledgeGraph()
    kg.add_node(make_node("n1"))
    kg.add_node(make_node("n2"))
    edge = make_edge("e1", "n1", "n2")
    kg.add_edge(edge)
    assert kg.get_edge("e1") is edge


@pytest.mark.level0
def test_edge_count_empty() -> None:
    kg = KnowledgeGraph()
    assert kg.edge_count == 0


@pytest.mark.level0
def test_edge_count_after_adds() -> None:
    kg = KnowledgeGraph()
    kg.add_node(make_node("n1"))
    kg.add_node(make_node("n2"))
    kg.add_node(make_node("n3"))
    kg.add_edge(make_edge("e1", "n1", "n2"))
    kg.add_edge(make_edge("e2", "n2", "n3"))
    assert kg.edge_count == 2


@pytest.mark.level0
def test_get_edge_missing_returns_none() -> None:
    kg = KnowledgeGraph()
    assert kg.get_edge("nope") is None


# ---------------------------------------------------------------------------
# remove_node — cascades edge removal
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_remove_node_removes_node() -> None:
    kg = KnowledgeGraph()
    kg.add_node(make_node("n1"))
    kg.remove_node("n1")
    assert kg.get_node("n1") is None
    assert kg.node_count == 0


@pytest.mark.level0
def test_remove_node_cascades_outgoing_edges() -> None:
    kg = KnowledgeGraph()
    kg.add_node(make_node("n1"))
    kg.add_node(make_node("n2"))
    kg.add_edge(make_edge("e1", "n1", "n2"))
    kg.remove_node("n1")
    assert kg.get_edge("e1") is None
    assert kg.edge_count == 0


@pytest.mark.level0
def test_remove_node_cascades_incoming_edges() -> None:
    kg = KnowledgeGraph()
    kg.add_node(make_node("n1"))
    kg.add_node(make_node("n2"))
    kg.add_edge(make_edge("e1", "n1", "n2"))
    kg.remove_node("n2")
    assert kg.get_edge("e1") is None
    assert kg.edge_count == 0


@pytest.mark.level0
def test_remove_node_missing_is_noop() -> None:
    kg = KnowledgeGraph()
    kg.remove_node("nope")  # should not raise


# ---------------------------------------------------------------------------
# remove_nodes_by_file
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_remove_nodes_by_file() -> None:
    kg = KnowledgeGraph()
    kg.add_node(make_node("n1", file_path="/src/a.py"))
    kg.add_node(make_node("n2", file_path="/src/a.py"))
    kg.add_node(make_node("n3", file_path="/src/b.py"))
    kg.remove_nodes_by_file("/src/a.py")
    assert kg.node_count == 1
    assert kg.get_node("n1") is None
    assert kg.get_node("n2") is None
    assert kg.get_node("n3") is not None


@pytest.mark.level0
def test_remove_nodes_by_file_cascades_edges() -> None:
    kg = KnowledgeGraph()
    kg.add_node(make_node("n1", file_path="/src/a.py"))
    kg.add_node(make_node("n2", file_path="/src/b.py"))
    kg.add_edge(make_edge("e1", "n1", "n2"))
    kg.remove_nodes_by_file("/src/a.py")
    assert kg.get_edge("e1") is None
    assert kg.edge_count == 0


# ---------------------------------------------------------------------------
# iter_nodes / iter_edges
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_iter_nodes() -> None:
    kg = KnowledgeGraph()
    n1 = make_node("n1")
    n2 = make_node("n2")
    kg.add_node(n1)
    kg.add_node(n2)
    nodes = list(kg.iter_nodes())
    assert len(nodes) == 2
    assert n1 in nodes
    assert n2 in nodes


@pytest.mark.level0
def test_iter_edges() -> None:
    kg = KnowledgeGraph()
    kg.add_node(make_node("n1"))
    kg.add_node(make_node("n2"))
    e1 = make_edge("e1", "n1", "n2")
    kg.add_edge(e1)
    edges = list(kg.iter_edges())
    assert edges == [e1]


# ---------------------------------------------------------------------------
# get_edges_from / get_edges_to
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_get_edges_from() -> None:
    kg = KnowledgeGraph()
    kg.add_node(make_node("n1"))
    kg.add_node(make_node("n2"))
    kg.add_node(make_node("n3"))
    e1 = make_edge("e1", "n1", "n2")
    e2 = make_edge("e2", "n1", "n3")
    e3 = make_edge("e3", "n2", "n3")
    kg.add_edge(e1)
    kg.add_edge(e2)
    kg.add_edge(e3)
    from_n1 = list(kg.get_edges_from("n1"))
    assert len(from_n1) == 2
    assert e1 in from_n1
    assert e2 in from_n1


@pytest.mark.level0
def test_get_edges_to() -> None:
    kg = KnowledgeGraph()
    kg.add_node(make_node("n1"))
    kg.add_node(make_node("n2"))
    kg.add_node(make_node("n3"))
    e1 = make_edge("e1", "n1", "n3")
    e2 = make_edge("e2", "n2", "n3")
    kg.add_edge(e1)
    kg.add_edge(e2)
    to_n3 = list(kg.get_edges_to("n3"))
    assert len(to_n3) == 2
    assert e1 in to_n3
    assert e2 in to_n3


@pytest.mark.level0
def test_get_edges_from_empty_node() -> None:
    kg = KnowledgeGraph()
    kg.add_node(make_node("n1"))
    assert list(kg.get_edges_from("n1")) == []


@pytest.mark.level0
def test_get_edges_to_missing_node() -> None:
    kg = KnowledgeGraph()
    assert list(kg.get_edges_to("ghost")) == []


# ---------------------------------------------------------------------------
# get_nodes_by_label
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_get_nodes_by_label() -> None:
    kg = KnowledgeGraph()
    kg.add_node(make_node("n1", label=NodeLabel.FUNCTION))
    kg.add_node(make_node("n2", label=NodeLabel.CLASS))
    kg.add_node(make_node("n3", label=NodeLabel.FUNCTION))
    funcs = list(kg.get_nodes_by_label(NodeLabel.FUNCTION))
    assert len(funcs) == 2
    classes = list(kg.get_nodes_by_label(NodeLabel.CLASS))
    assert len(classes) == 1


# ---------------------------------------------------------------------------
# get_nodes_by_file
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_get_nodes_by_file() -> None:
    kg = KnowledgeGraph()
    kg.add_node(make_node("n1", file_path="/src/a.py"))
    kg.add_node(make_node("n2", file_path="/src/a.py"))
    kg.add_node(make_node("n3", file_path="/src/b.py"))
    from_a = list(kg.get_nodes_by_file("/src/a.py"))
    assert len(from_a) == 2
    from_b = list(kg.get_nodes_by_file("/src/b.py"))
    assert len(from_b) == 1
    from_c = list(kg.get_nodes_by_file("/src/c.py"))
    assert from_c == []
