"""L0 unit tests for vector_graph/_types.py — all frozen dataclasses."""

from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError

from vector_graph._types import (
    NodeLabel,
    EdgeType,
    ResolutionTier,
    TIER_CONFIDENCE,
    NodeProperties,
    GraphNode,
    Edge,
    SymbolDef,
    TieredCandidates,
)


# ---------------------------------------------------------------------------
# NodeLabel enum
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_node_label_values() -> None:
    assert NodeLabel.FILE == "File"
    assert NodeLabel.FUNCTION == "Function"
    assert NodeLabel.CLASS == "Class"
    assert NodeLabel.METHOD == "Method"
    assert NodeLabel.ROS2_NODE == "ROS2Node"
    assert NodeLabel.TOPIC == "Topic"


@pytest.mark.level0
def test_node_label_is_str_enum() -> None:
    assert isinstance(NodeLabel.FILE, str)
    assert NodeLabel.FILE.value == "File"


# ---------------------------------------------------------------------------
# EdgeType enum
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_edge_type_values() -> None:
    assert EdgeType.CALLS == "CALLS"
    assert EdgeType.IMPORTS == "IMPORTS"
    assert EdgeType.CONTAINS == "CONTAINS"
    assert EdgeType.PUBLISHES_TO == "PUBLISHES_TO"
    assert EdgeType.SUBSCRIBES_TO == "SUBSCRIBES_TO"


@pytest.mark.level0
def test_edge_type_is_str_enum() -> None:
    assert isinstance(EdgeType.CALLS, str)


# ---------------------------------------------------------------------------
# ResolutionTier + TIER_CONFIDENCE
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_resolution_tier_values() -> None:
    assert ResolutionTier.SAME_FILE == "same-file"
    assert ResolutionTier.IMPORT_SCOPED == "import-scoped"
    assert ResolutionTier.GLOBAL == "global"


@pytest.mark.level0
def test_tier_confidence_values() -> None:
    assert TIER_CONFIDENCE[ResolutionTier.SAME_FILE] == 0.95
    assert TIER_CONFIDENCE[ResolutionTier.IMPORT_SCOPED] == 0.9
    assert TIER_CONFIDENCE[ResolutionTier.GLOBAL] == 0.5


# ---------------------------------------------------------------------------
# NodeProperties
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_node_properties_creation() -> None:
    props = NodeProperties(name="foo", file_path="/src/foo.py")
    assert props.name == "foo"
    assert props.file_path == "/src/foo.py"
    assert props.start_line is None
    assert props.is_exported is False
    assert props.parameters == ()


@pytest.mark.level0
def test_node_properties_frozen() -> None:
    props = NodeProperties(name="foo", file_path="/src/foo.py")
    with pytest.raises(FrozenInstanceError):
        props.name = "bar"  # type: ignore[misc]


@pytest.mark.level0
def test_node_properties_to_dict_filters_none_and_empty() -> None:
    props = NodeProperties(
        name="foo",
        file_path="/src/foo.py",
        start_line=None,
        end_line=None,
        return_type=None,
        parameters=(),
        decorators=(),
    )
    d = props.to_dict()
    assert "name" in d
    assert "file_path" in d
    # None fields excluded
    assert "start_line" not in d
    assert "return_type" not in d
    # empty tuples excluded
    assert "parameters" not in d
    assert "decorators" not in d


@pytest.mark.level0
def test_node_properties_to_dict_includes_non_empty_tuples() -> None:
    props = NodeProperties(
        name="bar",
        file_path="/src/bar.py",
        parameters=("x", "y"),
        start_line=10,
    )
    d = props.to_dict()
    assert d["parameters"] == ("x", "y")
    assert d["start_line"] == 10


# ---------------------------------------------------------------------------
# GraphNode
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_graph_node_creation() -> None:
    props = NodeProperties(name="my_func", file_path="/src/a.py", start_line=5)
    node = GraphNode(id="node-1", label=NodeLabel.FUNCTION, properties=props)
    assert node.id == "node-1"
    assert node.label == NodeLabel.FUNCTION
    assert node.properties is props


@pytest.mark.level0
def test_graph_node_frozen() -> None:
    props = NodeProperties(name="fn", file_path="/src/a.py")
    node = GraphNode(id="n1", label=NodeLabel.FUNCTION, properties=props)
    with pytest.raises(FrozenInstanceError):
        node.id = "n2"  # type: ignore[misc]


@pytest.mark.level0
def test_graph_node_to_dict() -> None:
    props = NodeProperties(name="my_func", file_path="/src/a.py", start_line=1)
    node = GraphNode(id="node-1", label=NodeLabel.FUNCTION, properties=props)
    d = node.to_dict()
    assert d["id"] == "node-1"
    assert d["label"] == "Function"
    assert isinstance(d["properties"], dict)
    assert d["properties"]["name"] == "my_func"


# ---------------------------------------------------------------------------
# Edge
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_edge_creation() -> None:
    edge = Edge(
        id="e1",
        source_id="n1",
        target_id="n2",
        edge_type=EdgeType.CALLS,
    )
    assert edge.id == "e1"
    assert edge.source_id == "n1"
    assert edge.target_id == "n2"
    assert edge.edge_type == EdgeType.CALLS
    assert edge.confidence == 0.9
    assert edge.reason == ""


@pytest.mark.level0
def test_edge_frozen() -> None:
    edge = Edge(id="e1", source_id="n1", target_id="n2", edge_type=EdgeType.CALLS)
    with pytest.raises(FrozenInstanceError):
        edge.id = "e2"  # type: ignore[misc]


@pytest.mark.level0
def test_edge_to_dict_no_reason() -> None:
    edge = Edge(id="e1", source_id="n1", target_id="n2", edge_type=EdgeType.IMPORTS)
    d = edge.to_dict()
    assert d["id"] == "e1"
    assert d["source_id"] == "n1"
    assert d["target_id"] == "n2"
    assert d["edge_type"] == "IMPORTS"
    assert d["confidence"] == 0.9
    assert "reason" not in d


@pytest.mark.level0
def test_edge_to_dict_with_reason() -> None:
    edge = Edge(
        id="e2",
        source_id="n1",
        target_id="n2",
        edge_type=EdgeType.CALLS,
        confidence=0.8,
        reason="direct call at line 10",
    )
    d = edge.to_dict()
    assert d["reason"] == "direct call at line 10"
    assert d["confidence"] == 0.8


# ---------------------------------------------------------------------------
# SymbolDef
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_symbol_def_creation() -> None:
    sym = SymbolDef(
        node_id="n1",
        name="my_func",
        file_path="/src/a.py",
        label=NodeLabel.FUNCTION,
    )
    assert sym.node_id == "n1"
    assert sym.name == "my_func"
    assert sym.file_path == "/src/a.py"
    assert sym.label == NodeLabel.FUNCTION
    assert sym.parameter_count is None
    assert sym.owner_id is None


@pytest.mark.level0
def test_symbol_def_frozen() -> None:
    sym = SymbolDef(node_id="n1", name="f", file_path="/a.py", label=NodeLabel.FUNCTION)
    with pytest.raises(FrozenInstanceError):
        sym.name = "g"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TieredCandidates
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_tiered_candidates_confidence() -> None:
    sym = SymbolDef(node_id="n1", name="f", file_path="/a.py", label=NodeLabel.FUNCTION)
    tc = TieredCandidates(candidates=(sym,), tier=ResolutionTier.SAME_FILE)
    assert tc.confidence == 0.95


@pytest.mark.level0
def test_tiered_candidates_is_empty_false() -> None:
    sym = SymbolDef(node_id="n1", name="f", file_path="/a.py", label=NodeLabel.FUNCTION)
    tc = TieredCandidates(candidates=(sym,), tier=ResolutionTier.GLOBAL)
    assert tc.is_empty is False


@pytest.mark.level0
def test_tiered_candidates_is_empty_true() -> None:
    tc = TieredCandidates(candidates=(), tier=ResolutionTier.GLOBAL)
    assert tc.is_empty is True


@pytest.mark.level0
def test_tiered_candidates_frozen() -> None:
    tc = TieredCandidates(candidates=(), tier=ResolutionTier.GLOBAL)
    with pytest.raises(FrozenInstanceError):
        tc.tier = ResolutionTier.SAME_FILE  # type: ignore[misc]


@pytest.mark.level0
def test_tiered_candidates_import_scoped_confidence() -> None:
    tc = TieredCandidates(candidates=(), tier=ResolutionTier.IMPORT_SCOPED)
    assert tc.confidence == 0.9
