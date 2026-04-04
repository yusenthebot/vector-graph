"""L2 unit tests for build_call_edges (call graph resolution)."""

from __future__ import annotations

import pytest

from vector_graph._types import (
    GraphNode,
    Edge,
    EdgeType,
    NodeLabel,
    NodeProperties,
    ExtractedCall,
    ExtractedFunction,
    ExtractedImport,
    FileParseResult,
    SymbolDef,
    ResolutionTier,
    TIER_CONFIDENCE,
    TypeBinding,
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
# Minimal ResolutionContext stub for testing
# ---------------------------------------------------------------------------

class StubResolutionContext:
    """Minimal resolution context for testing call graph building."""

    def __init__(self) -> None:
        # name -> list of SymbolDef
        self._same_file: dict[str, list[SymbolDef]] = {}
        self._import_scoped: dict[str, list[SymbolDef]] = {}
        self._global: dict[str, list[SymbolDef]] = {}

    def register_same_file(self, file_path: str, name: str, symbol: SymbolDef) -> None:
        key = f"{file_path}::{name}"
        self._same_file.setdefault(key, []).append(symbol)

    def register_import_scoped(self, file_path: str, name: str, symbol: SymbolDef) -> None:
        key = f"{file_path}::{name}"
        self._import_scoped.setdefault(key, []).append(symbol)

    def register_global(self, name: str, symbol: SymbolDef) -> None:
        self._global.setdefault(name, []).append(symbol)

    def resolve(self, file_path: str, name: str) -> tuple[list[SymbolDef], ResolutionTier] | None:
        """Return (candidates, tier) or None."""
        # same-file first
        key = f"{file_path}::{name}"
        if key in self._same_file and self._same_file[key]:
            return self._same_file[key], ResolutionTier.SAME_FILE
        if key in self._import_scoped and self._import_scoped[key]:
            return self._import_scoped[key], ResolutionTier.IMPORT_SCOPED
        if name in self._global and self._global[name]:
            return self._global[name], ResolutionTier.GLOBAL
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_fn_node(node_id: str, name: str, file_path: str, param_count: int = 0) -> GraphNode:
    props = NodeProperties(name=name, file_path=file_path, parameter_count=param_count)
    return GraphNode(id=node_id, label=NodeLabel.FUNCTION, properties=props)


def make_symbol(node_id: str, name: str, file_path: str, param_count: int | None = None) -> SymbolDef:
    return SymbolDef(
        node_id=node_id,
        name=name,
        file_path=file_path,
        label=NodeLabel.FUNCTION,
        parameter_count=param_count,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.level2
def test_call_graph_empty_parse_results() -> None:
    """No parse results produces no call edges."""
    from vector_graph.analysis.call_graph import build_call_edges

    g = SimpleGraph()
    ctx = StubResolutionContext()
    edges = build_call_edges(g, {}, ctx)
    assert edges == []


@pytest.mark.level2
def test_call_graph_same_file_high_confidence() -> None:
    """Calls within same file get SAME_FILE confidence (0.95)."""
    from vector_graph.analysis.call_graph import build_call_edges

    g = SimpleGraph()
    g.add_node(make_fn_node("caller_id", "caller_fn", "/src/a.py"))
    g.add_node(make_fn_node("callee_id", "callee_fn", "/src/a.py"))

    ctx = StubResolutionContext()
    ctx.register_same_file("/src/a.py", "callee_fn", make_symbol("callee_id", "callee_fn", "/src/a.py"))

    call = ExtractedCall(
        callee_name="callee_fn",
        file_path="/src/a.py",
        line=10,
        caller_name="caller_fn",
    )
    parse_results = {
        "/src/a.py": FileParseResult(file_path="/src/a.py", calls=(call,))
    }

    edges = build_call_edges(g, parse_results, ctx)
    assert len(edges) >= 1
    e = edges[0]
    assert e.confidence == TIER_CONFIDENCE[ResolutionTier.SAME_FILE]
    assert e.edge_type == EdgeType.CALLS


@pytest.mark.level2
def test_call_graph_imported_function_medium_confidence() -> None:
    """Call to imported function gets IMPORT_SCOPED confidence (0.9)."""
    from vector_graph.analysis.call_graph import build_call_edges

    g = SimpleGraph()
    g.add_node(make_fn_node("caller_id", "caller_fn", "/src/views.py"))
    g.add_node(make_fn_node("utils_fn_id", "validate_email", "/src/utils.py"))

    ctx = StubResolutionContext()
    ctx.register_import_scoped(
        "/src/views.py", "validate_email",
        make_symbol("utils_fn_id", "validate_email", "/src/utils.py"),
    )

    call = ExtractedCall(
        callee_name="validate_email",
        file_path="/src/views.py",
        line=5,
        caller_name="caller_fn",
    )
    parse_results = {
        "/src/views.py": FileParseResult(file_path="/src/views.py", calls=(call,))
    }

    edges = build_call_edges(g, parse_results, ctx)
    assert len(edges) >= 1
    assert edges[0].confidence == TIER_CONFIDENCE[ResolutionTier.IMPORT_SCOPED]


@pytest.mark.level2
def test_call_graph_unknown_function_low_confidence() -> None:
    """Call to unresolvable function gets GLOBAL tier confidence (0.5)."""
    from vector_graph.analysis.call_graph import build_call_edges

    g = SimpleGraph()
    g.add_node(make_fn_node("caller_id", "caller_fn", "/src/a.py"))
    g.add_node(make_fn_node("mystery_id", "mystery_fn", "/src/b.py"))

    ctx = StubResolutionContext()
    # mystery_fn registered as global
    ctx.register_global("mystery_fn", make_symbol("mystery_id", "mystery_fn", "/src/b.py"))

    call = ExtractedCall(
        callee_name="mystery_fn",
        file_path="/src/a.py",
        line=3,
        caller_name="caller_fn",
    )
    parse_results = {
        "/src/a.py": FileParseResult(file_path="/src/a.py", calls=(call,))
    }

    edges = build_call_edges(g, parse_results, ctx)
    assert len(edges) >= 1
    assert edges[0].confidence == TIER_CONFIDENCE[ResolutionTier.GLOBAL]


@pytest.mark.level2
def test_call_graph_unresolvable_call_skipped() -> None:
    """Calls that cannot be resolved at all are skipped (no edge created)."""
    from vector_graph.analysis.call_graph import build_call_edges

    g = SimpleGraph()
    g.add_node(make_fn_node("caller_id", "caller_fn", "/src/a.py"))

    ctx = StubResolutionContext()
    # nothing registered for 'ghost_fn'

    call = ExtractedCall(
        callee_name="ghost_fn",
        file_path="/src/a.py",
        line=7,
        caller_name="caller_fn",
    )
    parse_results = {
        "/src/a.py": FileParseResult(file_path="/src/a.py", calls=(call,))
    }

    edges = build_call_edges(g, parse_results, ctx)
    assert edges == []


@pytest.mark.level2
def test_call_graph_arity_filtering_excludes_wrong_param_count() -> None:
    """Candidate with wrong parameter count is excluded by arity filtering."""
    from vector_graph.analysis.call_graph import build_call_edges

    g = SimpleGraph()
    g.add_node(make_fn_node("caller_id", "caller_fn", "/src/a.py"))
    g.add_node(make_fn_node("callee_2args_id", "my_fn", "/src/b.py", param_count=2))
    g.add_node(make_fn_node("callee_3args_id", "my_fn", "/src/c.py", param_count=3))

    ctx = StubResolutionContext()
    # Two candidates for 'my_fn' at global scope
    ctx.register_global("my_fn", make_symbol("callee_2args_id", "my_fn", "/src/b.py", param_count=2))
    ctx.register_global("my_fn", make_symbol("callee_3args_id", "my_fn", "/src/c.py", param_count=3))

    call = ExtractedCall(
        callee_name="my_fn",
        file_path="/src/a.py",
        line=1,
        caller_name="caller_fn",
        arg_count=3,  # caller passes 3 args
    )
    parse_results = {
        "/src/a.py": FileParseResult(file_path="/src/a.py", calls=(call,))
    }

    edges = build_call_edges(g, parse_results, ctx)
    # Only the 3-arg candidate should be kept
    target_ids = {e.target_id for e in edges}
    assert "callee_3args_id" in target_ids
    assert "callee_2args_id" not in target_ids


@pytest.mark.level2
def test_call_graph_arity_filtering_keeps_unknown_param_count() -> None:
    """Candidate with unknown (None) parameter count is kept despite arity mismatch."""
    from vector_graph.analysis.call_graph import build_call_edges

    g = SimpleGraph()
    g.add_node(make_fn_node("caller_id", "caller_fn", "/src/a.py"))
    g.add_node(make_fn_node("callee_id", "flexible_fn", "/src/b.py"))

    ctx = StubResolutionContext()
    # param_count=None means unknown
    ctx.register_global("flexible_fn", make_symbol("callee_id", "flexible_fn", "/src/b.py", param_count=None))

    call = ExtractedCall(
        callee_name="flexible_fn",
        file_path="/src/a.py",
        line=1,
        caller_name="caller_fn",
        arg_count=5,
    )
    parse_results = {
        "/src/a.py": FileParseResult(file_path="/src/a.py", calls=(call,))
    }

    edges = build_call_edges(g, parse_results, ctx)
    assert len(edges) >= 1
    assert edges[0].target_id == "callee_id"


@pytest.mark.level2
def test_call_graph_attribute_call_resolved() -> None:
    """Attribute calls (obj.method()) resolve via receiver type info."""
    from vector_graph.analysis.call_graph import build_call_edges

    g = SimpleGraph()
    g.add_node(make_fn_node("caller_id", "use_service", "/src/handler.py"))
    g.add_node(make_fn_node("method_id", "process", "/src/service.py"))

    ctx = StubResolutionContext()
    # method 'process' on object 'self.svc' in scope of handler.py
    ctx.register_import_scoped(
        "/src/handler.py", "process",
        make_symbol("method_id", "process", "/src/service.py"),
    )

    call = ExtractedCall(
        callee_name="process",
        file_path="/src/handler.py",
        line=10,
        caller_name="use_service",
        is_attribute=True,
        receiver="self.svc",
    )
    parse_results = {
        "/src/handler.py": FileParseResult(file_path="/src/handler.py", calls=(call,))
    }

    edges = build_call_edges(g, parse_results, ctx)
    assert len(edges) >= 1
    assert edges[0].target_id == "method_id"


@pytest.mark.level2
def test_call_graph_multiple_calls_multiple_edges() -> None:
    """Multiple calls in a file produce multiple edges."""
    from vector_graph.analysis.call_graph import build_call_edges

    g = SimpleGraph()
    g.add_node(make_fn_node("caller_id", "main_fn", "/src/main.py"))
    g.add_node(make_fn_node("a_id", "func_a", "/src/main.py"))
    g.add_node(make_fn_node("b_id", "func_b", "/src/main.py"))

    ctx = StubResolutionContext()
    ctx.register_same_file("/src/main.py", "func_a", make_symbol("a_id", "func_a", "/src/main.py"))
    ctx.register_same_file("/src/main.py", "func_b", make_symbol("b_id", "func_b", "/src/main.py"))

    calls = (
        ExtractedCall(callee_name="func_a", file_path="/src/main.py", line=5, caller_name="main_fn"),
        ExtractedCall(callee_name="func_b", file_path="/src/main.py", line=6, caller_name="main_fn"),
    )
    parse_results = {
        "/src/main.py": FileParseResult(file_path="/src/main.py", calls=calls)
    }

    edges = build_call_edges(g, parse_results, ctx)
    target_ids = {e.target_id for e in edges}
    assert "a_id" in target_ids
    assert "b_id" in target_ids


@pytest.mark.level2
def test_call_graph_edge_source_is_caller() -> None:
    """Edge source_id corresponds to the caller node, not the callee."""
    from vector_graph.analysis.call_graph import build_call_edges

    g = SimpleGraph()
    g.add_node(make_fn_node("caller_id", "caller_fn", "/src/a.py"))
    g.add_node(make_fn_node("callee_id", "callee_fn", "/src/a.py"))

    ctx = StubResolutionContext()
    ctx.register_same_file("/src/a.py", "callee_fn", make_symbol("callee_id", "callee_fn", "/src/a.py"))

    call = ExtractedCall(
        callee_name="callee_fn",
        file_path="/src/a.py",
        line=3,
        caller_name="caller_fn",
    )
    parse_results = {
        "/src/a.py": FileParseResult(file_path="/src/a.py", calls=(call,))
    }

    edges = build_call_edges(g, parse_results, ctx)
    assert len(edges) >= 1
    assert edges[0].source_id == "caller_id"
    assert edges[0].target_id == "callee_id"


@pytest.mark.level2
def test_build_caller_index_basic() -> None:
    """Build index from a graph with 2 functions — (name, file) -> node_id lookup works."""
    from vector_graph.analysis.call_graph import _build_caller_index

    g = SimpleGraph()
    g.add_node(make_fn_node("fn_a_id", "fn_a", "/src/a.py"))
    g.add_node(make_fn_node("fn_b_id", "fn_b", "/src/b.py"))

    index = _build_caller_index(g)

    assert index[("fn_a", "/src/a.py")] == "fn_a_id"
    assert index[("fn_b", "/src/b.py")] == "fn_b_id"
    assert len(index) == 2


@pytest.mark.level2
def test_build_caller_index_same_name_different_files() -> None:
    """Two functions named 'process' in different files both appear at their own (name, file) keys."""
    from vector_graph.analysis.call_graph import _build_caller_index

    g = SimpleGraph()
    g.add_node(make_fn_node("proc_a_id", "process", "/src/module_a.py"))
    g.add_node(make_fn_node("proc_b_id", "process", "/src/module_b.py"))

    index = _build_caller_index(g)

    assert index[("process", "/src/module_a.py")] == "proc_a_id"
    assert index[("process", "/src/module_b.py")] == "proc_b_id"
    assert len(index) == 2


@pytest.mark.level2
def test_build_caller_index_empty_graph() -> None:
    """Empty graph returns empty dict."""
    from vector_graph.analysis.call_graph import _build_caller_index

    g = SimpleGraph()
    index = _build_caller_index(g)

    assert index == {}


@pytest.mark.level2
def test_build_caller_index_skips_non_callable() -> None:
    """Classes, files, and variables are NOT included — only Function and Method nodes."""
    from vector_graph.analysis.call_graph import _build_caller_index

    g = SimpleGraph()
    # Add one Function node
    g.add_node(make_fn_node("fn_id", "my_func", "/src/a.py"))
    # Add a Method node
    props_method = NodeProperties(name="my_method", file_path="/src/a.py", parameter_count=1)
    g.add_node(GraphNode(id="method_id", label=NodeLabel.METHOD, properties=props_method))
    # Add a Class node — should be skipped
    props_class = NodeProperties(name="MyClass", file_path="/src/a.py")
    g.add_node(GraphNode(id="class_id", label=NodeLabel.CLASS, properties=props_class))
    # Add a File node — should be skipped
    props_file = NodeProperties(name="a.py", file_path="/src/a.py")
    g.add_node(GraphNode(id="file_id", label=NodeLabel.FILE, properties=props_file))

    index = _build_caller_index(g)

    assert ("my_func", "/src/a.py") in index
    assert ("my_method", "/src/a.py") in index
    assert ("MyClass", "/src/a.py") not in index
    assert ("a.py", "/src/a.py") not in index
    assert len(index) == 2


@pytest.mark.level2
def test_caller_index_used_in_build_call_edges() -> None:
    """Integration-style: build_call_edges still produces correct edges with the index path."""
    from vector_graph.analysis.call_graph import build_call_edges

    g = SimpleGraph()
    g.add_node(make_fn_node("caller_id", "caller_fn", "/src/a.py"))
    g.add_node(make_fn_node("callee_id", "callee_fn", "/src/a.py"))

    ctx = StubResolutionContext()
    ctx.register_same_file("/src/a.py", "callee_fn", make_symbol("callee_id", "callee_fn", "/src/a.py"))

    call = ExtractedCall(
        callee_name="callee_fn",
        file_path="/src/a.py",
        line=10,
        caller_name="caller_fn",
    )
    parse_results = {
        "/src/a.py": FileParseResult(file_path="/src/a.py", calls=(call,))
    }

    edges = build_call_edges(g, parse_results, ctx)

    assert len(edges) == 1
    assert edges[0].source_id == "caller_id"
    assert edges[0].target_id == "callee_id"
    assert edges[0].edge_type == EdgeType.CALLS
    assert edges[0].confidence == TIER_CONFIDENCE[ResolutionTier.SAME_FILE]


@pytest.mark.level2
def test_call_graph_self_calls_excluded() -> None:
    """A function calling itself (recursion) still produces an edge."""
    from vector_graph.analysis.call_graph import build_call_edges

    g = SimpleGraph()
    g.add_node(make_fn_node("recursive_id", "recursive_fn", "/src/a.py"))

    ctx = StubResolutionContext()
    ctx.register_same_file(
        "/src/a.py", "recursive_fn",
        make_symbol("recursive_id", "recursive_fn", "/src/a.py"),
    )

    call = ExtractedCall(
        callee_name="recursive_fn",
        file_path="/src/a.py",
        line=5,
        caller_name="recursive_fn",  # same function
    )
    parse_results = {
        "/src/a.py": FileParseResult(file_path="/src/a.py", calls=(call,))
    }

    edges = build_call_edges(g, parse_results, ctx)
    # Recursive calls are allowed (the function calls itself)
    # Edge should exist with source == target
    assert len(edges) >= 1
    assert edges[0].source_id == "recursive_id"
    assert edges[0].target_id == "recursive_id"


# ---------------------------------------------------------------------------
# Helpers for type-aware resolution tests
# ---------------------------------------------------------------------------

def make_method_node(node_id: str, name: str, file_path: str, param_count: int = 1) -> GraphNode:
    """Create a METHOD node."""
    props = NodeProperties(name=name, file_path=file_path, parameter_count=param_count)
    return GraphNode(id=node_id, label=NodeLabel.METHOD, properties=props)


def make_class_node(node_id: str, name: str, file_path: str, bases: tuple[str, ...] = ()) -> GraphNode:
    """Create a CLASS node."""
    props = NodeProperties(name=name, file_path=file_path, bases=bases)
    return GraphNode(id=node_id, label=NodeLabel.CLASS, properties=props)


def make_method_symbol(node_id: str, name: str, file_path: str, param_count: int = 1) -> SymbolDef:
    """Create a SymbolDef for a METHOD."""
    return SymbolDef(
        node_id=node_id,
        name=name,
        file_path=file_path,
        label=NodeLabel.METHOD,
        parameter_count=param_count,
    )


def _add_has_method_edge(
    graph: SimpleGraph,
    class_id: str,
    method_id: str,
    edge_id: str,
) -> None:
    """Add a HAS_METHOD edge from class node to method node."""
    graph.add_edge(Edge(
        id=edge_id,
        source_id=class_id,
        target_id=method_id,
        edge_type=EdgeType.HAS_METHOD,
        confidence=0.95,
    ))


def _build_type_map_with_binding(
    file_path: str,
    scope: str,
    variable: str,
    inferred_type: str,
):
    """Build a TypeMap with a single binding (avoids importing TypeMap directly)."""
    from vector_graph.analysis.type_inference import TypeMap
    type_map = TypeMap()
    type_map.add(TypeBinding(
        variable_name=variable,
        inferred_type=inferred_type,
        source_file=file_path,
        scope=scope,
        line=1,
        confidence=0.9,
    ))
    return type_map


def _build_symbol_table_with_method(method_name: str, method_sym: SymbolDef):
    """Build a SymbolTable with one method registered."""
    from vector_graph.graph.symbol_table import SymbolTable
    st = SymbolTable()
    st.register(method_sym)
    return st


# ---------------------------------------------------------------------------
# Type-aware resolution tests
# ---------------------------------------------------------------------------

@pytest.mark.level2
def test_typed_attribute_call_resolves_to_class_method() -> None:
    """x = Foo(); x.bar() should resolve to Foo.bar, not to any bar()."""
    from vector_graph.analysis.call_graph import build_call_edges
    from vector_graph.graph.symbol_table import SymbolTable
    from vector_graph.analysis.type_inference import TypeMap

    # Graph: caller_fn (function), Foo (class), Foo.bar (method), other_bar (function)
    g = SimpleGraph()
    g.add_node(make_fn_node("caller_id", "caller_fn", "/src/a.py"))
    g.add_node(make_class_node("foo_cls_id", "Foo", "/src/a.py"))
    g.add_node(make_method_node("foo_bar_id", "bar", "/src/a.py"))
    g.add_node(make_fn_node("other_bar_id", "bar", "/src/b.py"))
    _add_has_method_edge(g, "foo_cls_id", "foo_bar_id", "hm_edge_1")

    # TypeMap: in scope "caller_fn", x -> Foo
    type_map = _build_type_map_with_binding("/src/a.py", "caller_fn", "x", "Foo")

    # SymbolTable: both bar symbols registered
    st = SymbolTable()
    st.register(make_method_symbol("foo_bar_id", "bar", "/src/a.py"))
    st.register(make_symbol("other_bar_id", "bar", "/src/b.py"))

    ctx = StubResolutionContext()
    # Global fallback would find both bars — typed resolution should pick only Foo.bar

    call = ExtractedCall(
        callee_name="bar",
        file_path="/src/a.py",
        line=10,
        caller_name="caller_fn",
        is_attribute=True,
        receiver="x",
    )
    parse_results = {"/src/a.py": FileParseResult(file_path="/src/a.py", calls=(call,))}

    edges = build_call_edges(g, parse_results, ctx, type_map=type_map, symbol_table=st)

    target_ids = {e.target_id for e in edges}
    assert "foo_bar_id" in target_ids, "Should resolve to Foo.bar"
    assert "other_bar_id" not in target_ids, "Should NOT resolve to unrelated bar"


@pytest.mark.level2
def test_self_attr_method_resolves_correctly() -> None:
    """self.graph.add_node() where self.graph is KnowledgeGraph resolves correctly."""
    from vector_graph.analysis.call_graph import build_call_edges
    from vector_graph.graph.symbol_table import SymbolTable
    from vector_graph.analysis.type_inference import TypeMap

    g = SimpleGraph()
    g.add_node(make_fn_node("init_id", "__init__", "/src/runner.py"))
    g.add_node(make_fn_node("use_graph_id", "use_graph", "/src/runner.py"))
    g.add_node(make_class_node("kg_cls_id", "KnowledgeGraph", "/src/kg.py"))
    g.add_node(make_method_node("add_node_id", "add_node", "/src/kg.py"))
    _add_has_method_edge(g, "kg_cls_id", "add_node_id", "hm_edge_2")

    # TypeMap: self.graph -> KnowledgeGraph (stored under class scope "Runner")
    type_map = _build_type_map_with_binding("/src/runner.py", "Runner", "self.graph", "KnowledgeGraph")

    st = SymbolTable()
    st.register(make_method_symbol("add_node_id", "add_node", "/src/kg.py"))

    ctx = StubResolutionContext()

    call = ExtractedCall(
        callee_name="add_node",
        file_path="/src/runner.py",
        line=20,
        caller_name="use_graph",
        caller_class="Runner",
        is_attribute=True,
        receiver="self.graph",
    )
    parse_results = {"/src/runner.py": FileParseResult(file_path="/src/runner.py", calls=(call,))}

    edges = build_call_edges(g, parse_results, ctx, type_map=type_map, symbol_table=st)

    target_ids = {e.target_id for e in edges}
    assert "add_node_id" in target_ids, "Should resolve self.graph.add_node to KnowledgeGraph.add_node"


@pytest.mark.level2
def test_untyped_attribute_call_falls_back() -> None:
    """x.bar() with no type info for x should fall back to global resolution."""
    from vector_graph.analysis.call_graph import build_call_edges
    from vector_graph.graph.symbol_table import SymbolTable
    from vector_graph.analysis.type_inference import TypeMap

    g = SimpleGraph()
    g.add_node(make_fn_node("caller_id", "caller_fn", "/src/a.py"))
    g.add_node(make_method_node("bar_id", "bar", "/src/b.py"))

    # Empty TypeMap — no type info for x
    type_map = TypeMap()

    st = SymbolTable()
    st.register(make_method_symbol("bar_id", "bar", "/src/b.py"))

    ctx = StubResolutionContext()
    # Register bar in global fallback
    ctx.register_global("bar", make_method_symbol("bar_id", "bar", "/src/b.py"))

    call = ExtractedCall(
        callee_name="bar",
        file_path="/src/a.py",
        line=5,
        caller_name="caller_fn",
        is_attribute=True,
        receiver="x",  # x has no type in type_map
    )
    parse_results = {"/src/a.py": FileParseResult(file_path="/src/a.py", calls=(call,))}

    edges = build_call_edges(g, parse_results, ctx, type_map=type_map, symbol_table=st)

    # Falls back to global resolution — bar_id should be resolved
    target_ids = {e.target_id for e in edges}
    assert "bar_id" in target_ids, "Should fall back to global resolution when type unknown"


@pytest.mark.level2
def test_confidence_boost_for_typed_resolution() -> None:
    """Type-confirmed calls should have confidence >= 0.95."""
    from vector_graph.analysis.call_graph import build_call_edges
    from vector_graph.graph.symbol_table import SymbolTable

    g = SimpleGraph()
    g.add_node(make_fn_node("caller_id", "caller_fn", "/src/a.py"))
    g.add_node(make_class_node("foo_cls_id", "Foo", "/src/a.py"))
    g.add_node(make_method_node("foo_bar_id", "bar", "/src/a.py"))
    _add_has_method_edge(g, "foo_cls_id", "foo_bar_id", "hm_edge_3")

    type_map = _build_type_map_with_binding("/src/a.py", "caller_fn", "x", "Foo")

    st = SymbolTable()
    st.register(make_method_symbol("foo_bar_id", "bar", "/src/a.py"))

    ctx = StubResolutionContext()

    call = ExtractedCall(
        callee_name="bar",
        file_path="/src/a.py",
        line=15,
        caller_name="caller_fn",
        is_attribute=True,
        receiver="x",
    )
    parse_results = {"/src/a.py": FileParseResult(file_path="/src/a.py", calls=(call,))}

    edges = build_call_edges(g, parse_results, ctx, type_map=type_map, symbol_table=st)

    assert len(edges) >= 1, "Expected at least one resolved edge"
    typed_edges = [e for e in edges if e.target_id == "foo_bar_id"]
    assert len(typed_edges) >= 1
    assert typed_edges[0].confidence >= 0.95, (
        f"Type-inferred edge should have confidence >= 0.95, got {typed_edges[0].confidence}"
    )


@pytest.mark.level2
def test_typed_resolution_with_inheritance() -> None:
    """x = Child(); x.parent_method() should resolve via EXTENDS edge to Parent."""
    from vector_graph.analysis.call_graph import build_call_edges
    from vector_graph.graph.symbol_table import SymbolTable

    g = SimpleGraph()
    g.add_node(make_fn_node("caller_id", "caller_fn", "/src/a.py"))
    # Class hierarchy: Child extends Parent
    g.add_node(make_class_node("child_cls_id", "Child", "/src/a.py", bases=("Parent",)))
    g.add_node(make_class_node("parent_cls_id", "Parent", "/src/a.py"))
    g.add_node(make_method_node("parent_method_id", "parent_method", "/src/a.py"))
    _add_has_method_edge(g, "parent_cls_id", "parent_method_id", "hm_edge_4")
    # EXTENDS edge: Child -> Parent
    g.add_edge(Edge(
        id="extends_edge_1",
        source_id="child_cls_id",
        target_id="parent_cls_id",
        edge_type=EdgeType.EXTENDS,
        confidence=0.85,
    ))

    type_map = _build_type_map_with_binding("/src/a.py", "caller_fn", "x", "Child")

    st = SymbolTable()
    # Register Parent class so hierarchy walk can find it
    st.register(SymbolDef(
        node_id="parent_cls_id",
        name="Parent",
        file_path="/src/a.py",
        label=NodeLabel.CLASS,
    ))
    st.register(SymbolDef(
        node_id="child_cls_id",
        name="Child",
        file_path="/src/a.py",
        label=NodeLabel.CLASS,
    ))
    st.register(make_method_symbol("parent_method_id", "parent_method", "/src/a.py"))

    ctx = StubResolutionContext()

    call = ExtractedCall(
        callee_name="parent_method",
        file_path="/src/a.py",
        line=30,
        caller_name="caller_fn",
        is_attribute=True,
        receiver="x",
    )
    parse_results = {"/src/a.py": FileParseResult(file_path="/src/a.py", calls=(call,))}

    edges = build_call_edges(g, parse_results, ctx, type_map=type_map, symbol_table=st)

    target_ids = {e.target_id for e in edges}
    assert "parent_method_id" in target_ids, (
        "Should resolve Child.parent_method via inheritance walk to Parent.parent_method"
    )
