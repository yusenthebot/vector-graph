"""Tests for vector_graph.analysis.query — 8 query types via execute_query().

Graph under test:
  file_a.py:
    class Base: ...
    class Foo(Base):
      @decorator_fn
      def bar(self): ...    # calls baz()
      def baz(self): ...
    def helper(): ...       # calls Foo.bar()
  file_b.py:
    class Child(Foo):
      def bar(self): ...    # overrides Foo.bar (same name, different file)
"""

from __future__ import annotations

import pytest

from vector_graph._types import Edge, EdgeType, GraphNode, NodeLabel, NodeProperties
from vector_graph.graph.knowledge_graph import KnowledgeGraph


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_node(
    node_id: str,
    name: str,
    file_path: str,
    label: NodeLabel,
    decorators: tuple[str, ...] = (),
    bases: tuple[str, ...] = (),
) -> GraphNode:
    props = NodeProperties(
        name=name,
        file_path=file_path,
        decorators=decorators,
        bases=bases,
    )
    return GraphNode(id=node_id, label=label, properties=props)


def _make_edge(
    edge_id: str,
    source_id: str,
    target_id: str,
    edge_type: EdgeType,
) -> Edge:
    return Edge(id=edge_id, source_id=source_id, target_id=target_id, edge_type=edge_type)


@pytest.fixture
def sample_graph() -> KnowledgeGraph:
    """Build a small graph for query testing.

    file_a.py:
      Base (Class)
      Foo(Base) (Class)
        @decorator_fn bar() (Method)  -- CALLS baz
        baz() (Method)
      helper() (Function)             -- CALLS Foo.bar

    file_b.py:
      Child(Foo) (Class)
        bar() (Method)                -- overrides Foo.bar (same name)
    """
    g = KnowledgeGraph()

    # --- Nodes ---
    g.add_node(_make_node("base_id", "Base", "file_a.py", NodeLabel.CLASS))
    g.add_node(_make_node("foo_id", "Foo", "file_a.py", NodeLabel.CLASS, bases=("Base",)))
    g.add_node(
        _make_node(
            "foo_bar_id", "bar", "file_a.py", NodeLabel.METHOD, decorators=("decorator_fn",)
        )
    )
    g.add_node(_make_node("foo_baz_id", "baz", "file_a.py", NodeLabel.METHOD))
    g.add_node(_make_node("helper_id", "helper", "file_a.py", NodeLabel.FUNCTION))

    g.add_node(_make_node("child_id", "Child", "file_b.py", NodeLabel.CLASS, bases=("Foo",)))
    g.add_node(_make_node("child_bar_id", "bar", "file_b.py", NodeLabel.METHOD))

    # --- Edges ---
    # Class hierarchy: Foo EXTENDS Base, Child EXTENDS Foo
    g.add_edge(_make_edge("e_foo_extends", "foo_id", "base_id", EdgeType.EXTENDS))
    g.add_edge(_make_edge("e_child_extends", "child_id", "foo_id", EdgeType.EXTENDS))

    # HAS_METHOD: Foo -> bar, Foo -> baz
    g.add_edge(_make_edge("e_foo_has_bar", "foo_id", "foo_bar_id", EdgeType.HAS_METHOD))
    g.add_edge(_make_edge("e_foo_has_baz", "foo_id", "foo_baz_id", EdgeType.HAS_METHOD))

    # HAS_METHOD: Child -> bar
    g.add_edge(_make_edge("e_child_has_bar", "child_id", "child_bar_id", EdgeType.HAS_METHOD))

    # CONTAINS: file-level (use CONTAINS edges from class -> methods)
    g.add_edge(_make_edge("e_dec_bar", "foo_bar_id", "foo_baz_id", EdgeType.CALLS))
    # helper CALLS Foo.bar
    g.add_edge(_make_edge("e_helper_calls_bar", "helper_id", "foo_bar_id", EdgeType.CALLS))

    # DECORATES: decorator_fn -> Foo.bar
    g.add_edge(_make_edge("e_dec", "foo_bar_id", "foo_bar_id", EdgeType.DECORATES))

    return g


# ---------------------------------------------------------------------------
# callers_of
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_query_callers_of(sample_graph: KnowledgeGraph) -> None:
    """callers_of 'baz' returns the node(s) that CALL baz — i.e. Foo.bar."""
    from vector_graph.analysis.query import execute_query

    result = execute_query(sample_graph, "callers_of", name="baz")
    assert result.query_type == "callers_of"
    names = {n.properties.name for n in result.nodes}
    assert "bar" in names
    assert result.count == len(result.nodes)


@pytest.mark.level2
def test_query_callers_of_no_callers(sample_graph: KnowledgeGraph) -> None:
    """callers_of a node with no incoming CALLS edges returns empty nodes."""
    from vector_graph.analysis.query import execute_query

    result = execute_query(sample_graph, "callers_of", name="helper")
    assert result.count == 0
    assert result.nodes == ()


# ---------------------------------------------------------------------------
# callees_of
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_query_callees_of(sample_graph: KnowledgeGraph) -> None:
    """callees_of 'bar' returns nodes that Foo.bar calls — i.e. baz."""
    from vector_graph.analysis.query import execute_query

    result = execute_query(sample_graph, "callees_of", name="bar")
    assert result.query_type == "callees_of"
    names = {n.properties.name for n in result.nodes}
    assert "baz" in names


@pytest.mark.level2
def test_query_callees_of_no_callees(sample_graph: KnowledgeGraph) -> None:
    """callees_of a node that calls nothing returns empty nodes."""
    from vector_graph.analysis.query import execute_query

    # baz calls nothing
    result = execute_query(sample_graph, "callees_of", name="baz")
    assert result.count == 0


# ---------------------------------------------------------------------------
# subclasses_of
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_query_subclasses_of(sample_graph: KnowledgeGraph) -> None:
    """subclasses_of 'Foo' returns Child (which EXTENDS Foo)."""
    from vector_graph.analysis.query import execute_query

    result = execute_query(sample_graph, "subclasses_of", name="Foo")
    assert result.query_type == "subclasses_of"
    names = {n.properties.name for n in result.nodes}
    assert "Child" in names
    assert "Base" not in names


@pytest.mark.level2
def test_query_subclasses_of_base(sample_graph: KnowledgeGraph) -> None:
    """subclasses_of 'Base' returns Foo (which EXTENDS Base)."""
    from vector_graph.analysis.query import execute_query

    result = execute_query(sample_graph, "subclasses_of", name="Base")
    names = {n.properties.name for n in result.nodes}
    assert "Foo" in names
    assert "Child" not in names


# ---------------------------------------------------------------------------
# implementations_of
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_query_implementations_of(sample_graph: KnowledgeGraph) -> None:
    """implementations_of 'bar' returns both Foo.bar and Child.bar (same name, Method label)."""
    from vector_graph.analysis.query import execute_query

    result = execute_query(sample_graph, "implementations_of", name="bar")
    assert result.query_type == "implementations_of"
    # Both method nodes named "bar" should appear
    assert result.count == 2
    node_ids = {n.id for n in result.nodes}
    assert "foo_bar_id" in node_ids
    assert "child_bar_id" in node_ids


# ---------------------------------------------------------------------------
# path_between
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_query_path_between(sample_graph: KnowledgeGraph) -> None:
    """path from 'helper' to 'baz' goes through 'bar' (helper->bar->baz)."""
    from vector_graph.analysis.query import execute_query

    result = execute_query(sample_graph, "path_between", source="helper", target="baz")
    assert result.query_type == "path_between"
    # Path should include at least helper, bar, baz
    assert result.count >= 2
    node_names = [n.properties.name for n in result.nodes]
    assert "helper" in node_names
    assert "baz" in node_names


@pytest.mark.level2
def test_query_path_between_no_path(sample_graph: KnowledgeGraph) -> None:
    """No path between disconnected nodes returns empty result (no edges to Base from helper)."""
    from vector_graph.analysis.query import execute_query

    # Base has no edges connecting it to helper in either direction
    result = execute_query(sample_graph, "path_between", source="Base", target="baz")
    # Base is only reachable via EXTENDS from Foo, and baz is reachable via CALLS from bar
    # BFS from Base going outward: Base has no edges_from and edges_to only from Foo
    # Going undirected: Base <- Foo <- Child, and Foo -> bar -> baz
    # So Base IS reachable to baz via undirected BFS through Foo -> bar -> baz
    # Let's instead test truly disconnected: a fresh graph node
    from vector_graph._types import GraphNode, NodeProperties, NodeLabel

    isolated_props = NodeProperties(name="IsolatedFn", file_path="isolated.py")
    isolated_node = GraphNode(
        id="isolated_id", label=NodeLabel.FUNCTION, properties=isolated_props
    )
    sample_graph.add_node(isolated_node)

    result2 = execute_query(sample_graph, "path_between", source="IsolatedFn", target="baz")
    assert result2.count == 0
    assert result2.nodes == ()


# ---------------------------------------------------------------------------
# by_file
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_query_by_file(sample_graph: KnowledgeGraph) -> None:
    """by_file returns all nodes in file_a.py."""
    from vector_graph.analysis.query import execute_query

    result = execute_query(sample_graph, "by_file", file_path="file_a.py")
    assert result.query_type == "by_file"
    names = {n.properties.name for n in result.nodes}
    assert "Base" in names
    assert "Foo" in names
    assert "bar" in names
    assert "baz" in names
    assert "helper" in names
    # Child is in file_b.py, not file_a.py
    assert "Child" not in names


# ---------------------------------------------------------------------------
# by_pattern
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_query_by_pattern(sample_graph: KnowledgeGraph) -> None:
    """by_pattern 'b*' matches bar and baz (and Base) — glob-style."""
    from vector_graph.analysis.query import execute_query

    result = execute_query(sample_graph, "by_pattern", pattern="b*")
    assert result.query_type == "by_pattern"
    names = {n.properties.name for n in result.nodes}
    assert "bar" in names
    assert "baz" in names
    # "Base" starts with "B" (capital) — fnmatch is case-sensitive by default
    assert "helper" not in names
    assert "Foo" not in names


# ---------------------------------------------------------------------------
# by_decorator
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_query_by_decorator(sample_graph: KnowledgeGraph) -> None:
    """by_decorator 'decorator_fn' finds Foo.bar (the only decorated method)."""
    from vector_graph.analysis.query import execute_query

    result = execute_query(sample_graph, "by_decorator", decorator="decorator_fn")
    assert result.query_type == "by_decorator"
    assert result.count == 1
    assert result.nodes[0].id == "foo_bar_id"


@pytest.mark.level2
def test_query_by_decorator_no_match(sample_graph: KnowledgeGraph) -> None:
    """by_decorator for a non-existent decorator returns empty."""
    from vector_graph.analysis.query import execute_query

    result = execute_query(sample_graph, "by_decorator", decorator="nonexistent_deco")
    assert result.count == 0
    assert result.nodes == ()


# ---------------------------------------------------------------------------
# unknown query type
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_query_unknown_type(sample_graph: KnowledgeGraph) -> None:
    """Unknown query type returns empty QueryResult (no nodes, no edges)."""
    from vector_graph.analysis.query import execute_query

    result = execute_query(sample_graph, "totally_unknown", name="foo")
    assert result.query_type == "totally_unknown"
    assert result.count == 0
    assert result.nodes == ()
    assert result.edges == ()


# ---------------------------------------------------------------------------
# count property
# ---------------------------------------------------------------------------


@pytest.mark.level2
def test_query_result_count(sample_graph: KnowledgeGraph) -> None:
    """count property always equals len(nodes) for any query."""
    from vector_graph.analysis.query import execute_query

    for qt, kwargs in [
        ("by_file", {"file_path": "file_a.py"}),
        ("by_pattern", {"pattern": "*"}),
        ("callers_of", {"name": "baz"}),
        ("callees_of", {"name": "bar"}),
        ("subclasses_of", {"name": "Foo"}),
    ]:
        result = execute_query(sample_graph, qt, **kwargs)
        assert result.count == len(result.nodes), (
            f"count mismatch for {qt}: count={result.count}, len(nodes)={len(result.nodes)}"
        )
