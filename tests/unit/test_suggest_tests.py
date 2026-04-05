"""Unit tests for vector_graph.analysis.suggest_tests."""

from __future__ import annotations

import pytest

from vector_graph._types import Edge, EdgeType, GraphNode, NodeLabel, NodeProperties
from vector_graph.analysis.suggest_tests import suggest_tests
from vector_graph.graph.knowledge_graph import KnowledgeGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fn(name: str, file_path: str) -> GraphNode:
    return GraphNode(
        id=name,
        label=NodeLabel.FUNCTION,
        properties=NodeProperties(name=name, file_path=file_path),
    )


def _edge(src: str, tgt: str) -> Edge:
    return Edge(
        id=f"{src}->{tgt}",
        source_id=src,
        target_id=tgt,
        edge_type=EdgeType.CALLS,
        confidence=0.9,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.level5
def test_suggest_tests_finds_test_callers() -> None:
    """A function called by a test function returns that test file."""
    graph = KnowledgeGraph()
    graph.add_node(_fn("target_fn", "src/mymod.py"))
    graph.add_node(_fn("test_target_fn", "tests/unit/test_mymod.py"))
    graph.add_edge(_edge("test_target_fn", "target_fn"))

    results = suggest_tests(graph, "target_fn")

    assert len(results) == 1
    assert results[0].test_file == "tests/unit/test_mymod.py"
    assert results[0].test_name == "test_target_fn"
    assert results[0].depth == 1


@pytest.mark.level5
def test_suggest_tests_no_tests() -> None:
    """An orphan function with no callers returns empty list."""
    graph = KnowledgeGraph()
    graph.add_node(_fn("orphan_fn", "src/orphan.py"))

    results = suggest_tests(graph, "orphan_fn")

    assert results == []


@pytest.mark.level5
def test_suggest_tests_transitive() -> None:
    """A function called by a helper called by a test is found transitively."""
    graph = KnowledgeGraph()
    graph.add_node(_fn("base_fn", "src/base.py"))
    graph.add_node(_fn("helper_fn", "src/helper.py"))
    graph.add_node(_fn("test_helper", "tests/unit/test_helper.py"))

    # test_helper -> helper_fn -> base_fn
    graph.add_edge(_edge("test_helper", "helper_fn"))
    graph.add_edge(_edge("helper_fn", "base_fn"))

    results = suggest_tests(graph, "base_fn")

    assert len(results) == 1
    assert results[0].test_file == "tests/unit/test_helper.py"
    assert results[0].test_name == "test_helper"
    assert results[0].depth == 2


@pytest.mark.level5
def test_suggest_tests_unknown_function() -> None:
    """suggest_tests for a name not in the graph returns empty list."""
    graph = KnowledgeGraph()
    results = suggest_tests(graph, "definitely_not_in_graph_xyz")
    assert results == []


@pytest.mark.level5
def test_suggest_tests_multiple_test_callers() -> None:
    """A function called by multiple test functions returns all of them."""
    graph = KnowledgeGraph()
    graph.add_node(_fn("shared_fn", "src/shared.py"))
    graph.add_node(_fn("test_a", "tests/unit/test_a.py"))
    graph.add_node(_fn("test_b", "tests/unit/test_b.py"))
    graph.add_edge(_edge("test_a", "shared_fn"))
    graph.add_edge(_edge("test_b", "shared_fn"))

    results = suggest_tests(graph, "shared_fn")

    test_names = {r.test_name for r in results}
    assert "test_a" in test_names
    assert "test_b" in test_names
    assert all(r.depth == 1 for r in results)


@pytest.mark.level5
def test_suggest_tests_sorted_by_depth() -> None:
    """Results are sorted by depth ascending."""
    graph = KnowledgeGraph()
    graph.add_node(_fn("deep_fn", "src/deep.py"))
    graph.add_node(_fn("mid_fn", "src/mid.py"))
    graph.add_node(_fn("test_mid", "tests/unit/test_mid.py"))
    graph.add_node(_fn("test_deep", "tests/unit/test_deep.py"))

    # test_mid -> mid_fn -> deep_fn  (transitive, depth 2)
    # test_deep -> deep_fn           (direct, depth 1)
    graph.add_edge(_edge("test_mid", "mid_fn"))
    graph.add_edge(_edge("mid_fn", "deep_fn"))
    graph.add_edge(_edge("test_deep", "deep_fn"))

    results = suggest_tests(graph, "deep_fn")

    assert len(results) == 2
    # Direct caller first
    assert results[0].depth <= results[1].depth
    direct = [r for r in results if r.test_name == "test_deep"]
    assert direct[0].depth == 1


@pytest.mark.level5
def test_suggest_tests_non_call_edges_ignored() -> None:
    """Non-CALLS edges (IMPORTS, etc.) are not followed upstream."""
    from vector_graph._types import EdgeType

    graph = KnowledgeGraph()
    graph.add_node(_fn("fn_a", "src/a.py"))
    graph.add_node(_fn("test_a", "tests/unit/test_a.py"))

    # IMPORTS edge — should not count
    import_edge = Edge(
        id="test_a->fn_a-import",
        source_id="test_a",
        target_id="fn_a",
        edge_type=EdgeType.IMPORTS,
        confidence=0.9,
    )
    graph.add_edge(import_edge)

    results = suggest_tests(graph, "fn_a")

    assert results == []
