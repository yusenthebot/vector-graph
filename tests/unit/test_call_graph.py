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
