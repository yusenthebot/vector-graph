"""Tests for GraphProtocol structural compliance and new _types additions."""

from __future__ import annotations

import pytest

from vector_graph._types import (
    Edge,
    EdgeType,
    GraphNode,
    NodeLabel,
    NodeProperties,
    QueryResult,
    TypeBinding,
)
from vector_graph.graph.knowledge_graph import KnowledgeGraph
from vector_graph.graph.protocols import GraphProtocol


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node(node_id: str, name: str = "foo", file_path: str = "/f.py") -> GraphNode:
    props = NodeProperties(name=name, file_path=file_path)
    return GraphNode(id=node_id, label=NodeLabel.FUNCTION, properties=props)


def _make_edge(edge_id: str, src: str, tgt: str) -> Edge:
    return Edge(
        id=edge_id,
        source_id=src,
        target_id=tgt,
        edge_type=EdgeType.CALLS,
    )


# ---------------------------------------------------------------------------
# GraphProtocol structural compliance
# ---------------------------------------------------------------------------

class TestGraphProtocolCompliance:
    def test_knowledge_graph_satisfies_protocol(self) -> None:
        """KnowledgeGraph must satisfy GraphProtocol via isinstance check."""
        kg = KnowledgeGraph()
        assert isinstance(kg, GraphProtocol)

    def test_protocol_methods_present_on_knowledge_graph(self) -> None:
        """All Protocol methods are accessible on a KnowledgeGraph instance."""
        kg = KnowledgeGraph()
        assert callable(kg.get_node)
        assert callable(kg.get_edges_from)
        assert callable(kg.get_edges_to)
        assert callable(kg.iter_nodes)
        assert callable(kg.iter_edges)
        assert callable(kg.get_nodes_by_label)
        assert callable(kg.get_nodes_by_file)
        assert hasattr(kg, "node_count")
        assert hasattr(kg, "edge_count")


# ---------------------------------------------------------------------------
# TypeBinding
# ---------------------------------------------------------------------------

class TestTypeBinding:
    def test_type_binding_frozen(self) -> None:
        """TypeBinding is frozen — mutation raises FrozenInstanceError."""
        tb = TypeBinding(
            variable_name="x",
            inferred_type="int",
            source_file="/a.py",
            scope="my_func",
            line=10,
        )
        with pytest.raises(Exception):
            tb.variable_name = "y"  # type: ignore[misc]

    def test_type_binding_fields_accessible(self) -> None:
        """All required fields are accessible after construction."""
        tb = TypeBinding(
            variable_name="result",
            inferred_type="str",
            source_file="/b.py",
            scope="process",
            line=42,
        )
        assert tb.variable_name == "result"
        assert tb.inferred_type == "str"
        assert tb.source_file == "/b.py"
        assert tb.scope == "process"
        assert tb.line == 42

    def test_type_binding_defaults(self) -> None:
        """confidence defaults to 0.9."""
        tb = TypeBinding(
            variable_name="v",
            inferred_type="bool",
            source_file="/c.py",
            scope="fn",
            line=1,
        )
        assert tb.confidence == 0.9

    def test_type_binding_custom_confidence(self) -> None:
        """confidence can be overridden."""
        tb = TypeBinding(
            variable_name="v",
            inferred_type="float",
            source_file="/c.py",
            scope="fn",
            line=1,
            confidence=0.5,
        )
        assert tb.confidence == 0.5


# ---------------------------------------------------------------------------
# QueryResult
# ---------------------------------------------------------------------------

class TestQueryResult:
    def test_query_result_frozen(self) -> None:
        """QueryResult is frozen — mutation raises FrozenInstanceError."""
        qr = QueryResult(query_type="find_nodes", params={"label": "Function"})
        with pytest.raises(Exception):
            qr.query_type = "other"  # type: ignore[misc]

    def test_query_result_count_property(self) -> None:
        """count returns number of nodes."""
        node = _make_node("n1")
        qr = QueryResult(
            query_type="find_nodes",
            params={"label": "Function"},
            nodes=(node,),
        )
        assert qr.count == 1

    def test_query_result_empty(self) -> None:
        """Empty QueryResult has count 0 and empty collections."""
        qr = QueryResult(query_type="find_nodes", params={})
        assert qr.count == 0
        assert qr.nodes == ()
        assert qr.edges == ()

    def test_query_result_with_edges(self) -> None:
        """edges tuple is accessible."""
        edge = _make_edge("e1", "n1", "n2")
        qr = QueryResult(
            query_type="find_edges",
            params={"type": "CALLS"},
            edges=(edge,),
        )
        assert len(qr.edges) == 1
        assert qr.edges[0].id == "e1"

    def test_query_result_params_accessible(self) -> None:
        """params dict is accessible."""
        params = {"label": "Function", "file": "/x.py"}
        qr = QueryResult(query_type="find_nodes", params=params)
        assert qr.params["label"] == "Function"
        assert qr.params["file"] == "/x.py"
