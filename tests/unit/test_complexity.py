"""Tests for vector_graph.analysis.complexity — code health metrics.

TDD: these tests are written BEFORE the implementation.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from vector_graph._types import Edge, EdgeType, GraphNode, NodeLabel, NodeProperties
from vector_graph.graph.knowledge_graph import KnowledgeGraph


# ---------------------------------------------------------------------------
# Helpers to build minimal graph nodes
# ---------------------------------------------------------------------------

def _fn_node_id(name: str, file_path: str, start_line: int) -> str:
    raw = f"fn:{file_path}:{name}:{start_line}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _cls_node_id(name: str, file_path: str, start_line: int) -> str:
    raw = f"cls:{file_path}:{name}:{start_line}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _edge_id(src: str, tgt: str, et: EdgeType) -> str:
    return hashlib.md5(f"{src}-{et.value}->{tgt}".encode()).hexdigest()[:16]


def _make_fn_node(
    name: str, file_path: str, start_line: int, end_line: int,
    label: NodeLabel = NodeLabel.FUNCTION,
) -> GraphNode:
    nid = _fn_node_id(name, file_path, start_line)
    props = NodeProperties(
        name=name,
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        parameter_count=0,
    )
    return GraphNode(id=nid, label=label, properties=props)


def _make_cls_node(name: str, file_path: str, start_line: int, end_line: int) -> GraphNode:
    nid = _cls_node_id(name, file_path, start_line)
    props = NodeProperties(name=name, file_path=file_path, start_line=start_line, end_line=end_line)
    return GraphNode(id=nid, label=NodeLabel.CLASS, properties=props)


# ---------------------------------------------------------------------------
# compute_cyclomatic_complexity — unit tests on inline source strings
# ---------------------------------------------------------------------------

from vector_graph.analysis.complexity import compute_cyclomatic_complexity


def test_cyclomatic_simple_function():
    """A function with no branches has complexity 1."""
    src = "def foo():\n    return 42\n"
    assert compute_cyclomatic_complexity(src) == 1


def test_cyclomatic_if_else():
    """if/else adds 1 decision point → complexity 2."""
    src = (
        "def foo(x):\n"
        "    if x > 0:\n"
        "        return 1\n"
        "    else:\n"
        "        return -1\n"
    )
    assert compute_cyclomatic_complexity(src) == 2


def test_cyclomatic_nested_if():
    """Two nested ifs → complexity 3."""
    src = (
        "def foo(x, y):\n"
        "    if x:\n"
        "        if y:\n"
        "            return 1\n"
        "    return 0\n"
    )
    assert compute_cyclomatic_complexity(src) == 3


def test_cyclomatic_for_loop():
    """A for loop adds 1 → complexity 2."""
    src = (
        "def foo(items):\n"
        "    for i in items:\n"
        "        print(i)\n"
    )
    assert compute_cyclomatic_complexity(src) == 2


def test_cyclomatic_while_loop():
    """A while loop adds 1 → complexity 2."""
    src = (
        "def foo(n):\n"
        "    while n > 0:\n"
        "        n -= 1\n"
    )
    assert compute_cyclomatic_complexity(src) == 2


def test_cyclomatic_boolean_and_or():
    """'if a and b or c' — 1 base + 1 (if) + 1 (and: 2 values → 1 extra) + 1 (or: 2 values → 1 extra)."""
    src = (
        "def foo(a, b, c):\n"
        "    if a and b or c:\n"
        "        return 1\n"
        "    return 0\n"
    )
    # 1 base + 1 if + 1 BoolOp(and, 2 vals) + 1 BoolOp(or, 2 vals) = 4
    # Actually: `a and b or c` is parsed as BoolOp(or, [BoolOp(and, [a, b]), c])
    # BoolOp(and, [a, b]) → len(values)-1 = 1
    # BoolOp(or, [BoolOp(and,...), c]) → len(values)-1 = 1
    # + if = 1, base = 1 → total = 4
    result = compute_cyclomatic_complexity(src)
    assert result == 4


def test_cyclomatic_try_except():
    """try with 2 except clauses → 2 ExceptHandler → complexity 3."""
    src = (
        "def foo():\n"
        "    try:\n"
        "        risky()\n"
        "    except ValueError:\n"
        "        pass\n"
        "    except TypeError:\n"
        "        pass\n"
    )
    assert compute_cyclomatic_complexity(src) == 3


def test_cyclomatic_comprehension_if():
    """List comp with one if clause → +1 → complexity 2."""
    src = (
        "def foo(items):\n"
        "    return [x for x in items if x > 0]\n"
    )
    assert compute_cyclomatic_complexity(src) == 2


def test_cyclomatic_assert():
    """assert adds 1 decision point → complexity 2."""
    src = (
        "def foo(x):\n"
        "    assert x > 0\n"
        "    return x\n"
    )
    assert compute_cyclomatic_complexity(src) == 2


def test_cyclomatic_ternary():
    """Ternary expression (IfExp) adds 1 → complexity 2."""
    src = (
        "def foo(x):\n"
        "    return 1 if x else 0\n"
    )
    assert compute_cyclomatic_complexity(src) == 2


def test_cyclomatic_complex_function():
    """Realistic mixed function — verify accumulated count."""
    src = (
        "def process(items, flag):\n"
        "    result = []\n"
        "    for item in items:\n"           # +1
        "        if item and flag:\n"         # +1 (if) +1 (BoolOp and)
        "            try:\n"
        "                result.append(item)\n"
        "            except Exception:\n"     # +1
        "                pass\n"
        "        elif item:\n"               # +1 (elif → another ast.If)
        "            result.append(item)\n"
        "    return result\n"
    )
    cc = compute_cyclomatic_complexity(src)
    assert cc >= 5  # at minimum 5 paths


def test_cyclomatic_syntax_error():
    """Unparseable source returns 1 (base complexity)."""
    assert compute_cyclomatic_complexity("def (broken:") == 1


# ---------------------------------------------------------------------------
# _risk_from_complexity — risk level assignment
# ---------------------------------------------------------------------------

from vector_graph.analysis.complexity import _risk_from_complexity


def test_risk_low():
    assert _risk_from_complexity(2, 20) == "LOW"


def test_risk_medium():
    assert _risk_from_complexity(7, 60) == "MEDIUM"


def test_risk_high():
    assert _risk_from_complexity(12, 80) == "HIGH"


def test_risk_critical():
    assert _risk_from_complexity(25, 250) == "CRITICAL"


def test_risk_high_by_lines_only():
    """Low CC but many lines → HIGH."""
    assert _risk_from_complexity(3, 120) == "HIGH"


def test_risk_critical_by_cc_only():
    """Very high CC, modest lines → CRITICAL."""
    assert _risk_from_complexity(21, 30) == "CRITICAL"


# ---------------------------------------------------------------------------
# analyze_complexity — reads real files via graph nodes
# ---------------------------------------------------------------------------

from vector_graph.analysis.complexity import analyze_complexity, ComplexityScore

PROJECT_ROOT = Path(__file__).parent.parent.parent


def test_analyze_complexity_on_graph(tmp_path: Path):
    """analyze_complexity reads function source from disk and returns scores."""
    # Write a small Python file with a known function
    src_file = tmp_path / "sample.py"
    src_file.write_text(
        "def simple():\n"
        "    return 42\n"
        "\n"
        "def branchy(x):\n"
        "    if x > 0:\n"
        "        return 1\n"
        "    return 0\n",
        encoding="utf-8",
    )

    graph = KnowledgeGraph()
    n1 = _make_fn_node("simple", str(src_file), 1, 2)
    n2 = _make_fn_node("branchy", str(src_file), 4, 7)
    graph.add_node(n1)
    graph.add_node(n2)

    scores = analyze_complexity(graph)
    assert len(scores) == 2

    by_name = {s.name: s for s in scores}
    assert "simple" in by_name
    assert "branchy" in by_name

    assert by_name["simple"].cyclomatic == 1
    assert by_name["branchy"].cyclomatic == 2

    # All scores are ComplexityScore instances with correct fields
    for s in scores:
        assert isinstance(s, ComplexityScore)
        assert s.node_id
        assert s.risk in ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def test_analyze_complexity_skips_non_functions():
    """analyze_complexity only processes FUNCTION and METHOD nodes."""
    graph = KnowledgeGraph()
    # Add a FILE node — should be skipped
    file_node = GraphNode(
        id="file:abc",
        label=NodeLabel.FILE,
        properties=NodeProperties(name="foo.py", file_path="/fake/foo.py"),
    )
    graph.add_node(file_node)
    scores = analyze_complexity(graph)
    assert scores == []


def test_analyze_complexity_handles_missing_file():
    """analyze_complexity skips nodes whose file does not exist."""
    graph = KnowledgeGraph()
    node = _make_fn_node("ghost", "/nonexistent/path.py", 1, 5)
    graph.add_node(node)
    # Should not raise, just skip
    scores = analyze_complexity(graph)
    assert scores == []


def test_analyze_complexity_on_real_project():
    """Self-analysis: complexity scores for vector_graph/pipeline.py functions."""
    from vector_graph.api.python_api import CodeGraph

    cg = CodeGraph(PROJECT_ROOT)
    cg.analyze()
    assert cg._graph is not None

    scores = analyze_complexity(cg._graph)
    assert len(scores) > 0

    # All have required fields
    for s in scores:
        assert isinstance(s.cyclomatic, int)
        assert s.cyclomatic >= 1
        assert s.risk in ("LOW", "MEDIUM", "HIGH", "CRITICAL")


# ---------------------------------------------------------------------------
# analyze_fan — fan-in / fan-out
# ---------------------------------------------------------------------------

from vector_graph.analysis.complexity import analyze_fan


def test_analyze_fan_in_out(tmp_path: Path):
    """Fan-in/out counts are computed from CALLS edges."""
    src = tmp_path / "f.py"
    src.write_text("def a(): pass\ndef b(): pass\ndef c(): pass\n", encoding="utf-8")

    graph = KnowledgeGraph()
    na = _make_fn_node("a", str(src), 1, 1)
    nb = _make_fn_node("b", str(src), 2, 2)
    nc = _make_fn_node("c", str(src), 3, 3)
    graph.add_node(na)
    graph.add_node(nb)
    graph.add_node(nc)

    # a -> b (CALLS), a -> c (CALLS)
    e1 = Edge(
        id=_edge_id(na.id, nb.id, EdgeType.CALLS),
        source_id=na.id, target_id=nb.id, edge_type=EdgeType.CALLS,
    )
    e2 = Edge(
        id=_edge_id(na.id, nc.id, EdgeType.CALLS),
        source_id=na.id, target_id=nc.id, edge_type=EdgeType.CALLS,
    )
    graph.add_edge(e1)
    graph.add_edge(e2)

    fan = analyze_fan(graph)
    assert fan[na.id] == (0, 2)  # a: no callers, calls 2
    assert fan[nb.id] == (1, 0)  # b: called by a, calls nobody
    assert fan[nc.id] == (1, 0)  # c: called by a, calls nobody


def test_analyze_fan_only_counts_calls_edges(tmp_path: Path):
    """IMPORTS edges should NOT be counted as fan-in/out."""
    src = tmp_path / "f.py"
    src.write_text("def a(): pass\ndef b(): pass\n", encoding="utf-8")

    graph = KnowledgeGraph()
    na = _make_fn_node("a", str(src), 1, 1)
    nb = _make_fn_node("b", str(src), 2, 2)
    graph.add_node(na)
    graph.add_node(nb)

    e = Edge(
        id=_edge_id(na.id, nb.id, EdgeType.IMPORTS),
        source_id=na.id, target_id=nb.id, edge_type=EdgeType.IMPORTS,
    )
    graph.add_edge(e)

    fan = analyze_fan(graph)
    # IMPORTS edge should not count
    assert fan[na.id] == (0, 0)
    assert fan[nb.id] == (0, 0)


# ---------------------------------------------------------------------------
# analyze_module_health — module-level metrics
# ---------------------------------------------------------------------------

from vector_graph.analysis.complexity import analyze_module_health, ModuleHealth


def test_module_health_coupling(tmp_path: Path):
    """Cross-group edges increase coupling_ratio."""
    # Two files in different subdirs
    dir_a = tmp_path / "pkg_a"
    dir_b = tmp_path / "pkg_b"
    dir_a.mkdir()
    dir_b.mkdir()

    fa = dir_a / "mod_a.py"
    fb = dir_b / "mod_b.py"
    fa.write_text("def aa(): pass\n", encoding="utf-8")
    fb.write_text("def bb(): pass\n", encoding="utf-8")

    graph = KnowledgeGraph()
    na = _make_fn_node("aa", str(fa), 1, 1)
    nb = _make_fn_node("bb", str(fb), 1, 1)
    graph.add_node(na)
    graph.add_node(nb)

    # aa -> bb: cross-group CALLS edge
    e = Edge(
        id=_edge_id(na.id, nb.id, EdgeType.CALLS),
        source_id=na.id, target_id=nb.id, edge_type=EdgeType.CALLS,
    )
    graph.add_edge(e)

    scores = analyze_complexity(graph)
    modules = analyze_module_health(graph, scores, str(tmp_path))

    # pkg_a group should have coupling_ratio = 1.0 (1 cross of 1 total)
    pkg_a_health = next((m for m in modules if "pkg_a" in m.group), None)
    assert pkg_a_health is not None
    assert pkg_a_health.coupling_ratio == 1.0


def test_module_health_cohesion(tmp_path: Path):
    """Internal calls increase cohesion."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    f = pkg / "mod.py"
    f.write_text("def x(): pass\ndef y(): pass\n", encoding="utf-8")

    graph = KnowledgeGraph()
    nx_ = _make_fn_node("x", str(f), 1, 1)
    ny = _make_fn_node("y", str(f), 2, 2)
    graph.add_node(nx_)
    graph.add_node(ny)

    # x -> y: internal CALLS edge
    e = Edge(
        id=_edge_id(nx_.id, ny.id, EdgeType.CALLS),
        source_id=nx_.id, target_id=ny.id, edge_type=EdgeType.CALLS,
    )
    graph.add_edge(e)

    scores = analyze_complexity(graph)
    modules = analyze_module_health(graph, scores, str(tmp_path))

    pkg_health = next((m for m in modules if "pkg" in m.group), None)
    assert pkg_health is not None
    assert pkg_health.cohesion > 0


def test_god_function_detection(tmp_path: Path):
    """Functions with CC > 10 are counted as god_functions."""
    f = tmp_path / "big.py"
    # Write a function that has many branches
    branches = "\n".join(f"    if x == {i}: return {i}" for i in range(15))
    f.write_text(f"def monster(x):\n{branches}\n    return -1\n", encoding="utf-8")

    graph = KnowledgeGraph()
    n = _make_fn_node("monster", str(f), 1, 20)
    graph.add_node(n)

    scores = analyze_complexity(graph)
    modules = analyze_module_health(graph, scores, str(tmp_path))

    # Should detect monster as a god function
    assert len(scores) == 1
    assert scores[0].cyclomatic > 10
    assert len(modules) >= 1
    root_m = next((m for m in modules), None)
    assert root_m is not None
    assert root_m.god_functions >= 1


def test_god_class_detection(tmp_path: Path):
    """Classes with > 20 methods are detected as god_classes."""
    import hashlib as _hashlib

    f = tmp_path / "god.py"
    methods = "\n".join(f"    def method_{i}(self): pass" for i in range(22))
    f.write_text(f"class GodClass:\n{methods}\n", encoding="utf-8")

    graph = KnowledgeGraph()
    cls_id = _cls_node_id("GodClass", str(f), 1)
    cls_props = NodeProperties(name="GodClass", file_path=str(f), start_line=1, end_line=24)
    cls_node = GraphNode(id=cls_id, label=NodeLabel.CLASS, properties=cls_props)
    graph.add_node(cls_node)

    # Add 22 method nodes with HAS_METHOD edges
    for i in range(22):
        mname = f"method_{i}"
        mid = _fn_node_id(mname, str(f), i + 2)
        mnode = _make_fn_node(mname, str(f), i + 2, i + 2, label=NodeLabel.METHOD)
        graph.add_node(mnode)
        eid = _edge_id(cls_id, mid, EdgeType.HAS_METHOD)
        graph.add_edge(Edge(id=eid, source_id=cls_id, target_id=mid, edge_type=EdgeType.HAS_METHOD))

    scores = analyze_complexity(graph)
    modules = analyze_module_health(graph, scores, str(tmp_path))
    total_god_cls = sum(m.god_classes for m in modules)
    assert total_god_cls >= 1


# ---------------------------------------------------------------------------
# build_health_report — HealthReport structure
# ---------------------------------------------------------------------------

from vector_graph.analysis.complexity import build_health_report, HealthReport


def test_health_report_structure(tmp_path: Path):
    """build_health_report returns a HealthReport with all required fields."""
    f = tmp_path / "sample.py"
    f.write_text(
        "def alpha(): return 1\n"
        "def beta(x):\n"
        "    if x: return x\n"
        "    return 0\n",
        encoding="utf-8",
    )

    graph = KnowledgeGraph()
    graph.add_node(_make_fn_node("alpha", str(f), 1, 1))
    graph.add_node(_make_fn_node("beta", str(f), 2, 4))

    report = build_health_report(graph, root_path=str(tmp_path))
    assert isinstance(report, HealthReport)
    assert report.total_functions == 2
    assert isinstance(report.avg_complexity, float)
    assert report.avg_complexity >= 1.0
    assert isinstance(report.high_risk_count, int)
    assert isinstance(report.critical_risk_count, int)
    assert isinstance(report.functions, tuple)
    assert isinstance(report.modules, tuple)


def test_health_report_sorted(tmp_path: Path):
    """Functions in HealthReport are sorted by cyclomatic complexity descending."""
    f = tmp_path / "s.py"
    # simple: CC=1, complex: CC>1
    f.write_text(
        "def simple(): return 1\n"
        "def complex_fn(x):\n"
        "    if x > 0:\n"
        "        if x > 10:\n"
        "            return 3\n"
        "        return 2\n"
        "    return 1\n",
        encoding="utf-8",
    )
    graph = KnowledgeGraph()
    graph.add_node(_make_fn_node("simple", str(f), 1, 1))
    graph.add_node(_make_fn_node("complex_fn", str(f), 2, 7))

    report = build_health_report(graph, root_path=str(tmp_path))
    assert len(report.functions) == 2
    # First function should have higher or equal complexity
    assert report.functions[0].cyclomatic >= report.functions[1].cyclomatic


def test_health_report_empty_graph():
    """build_health_report on empty graph returns zero counts."""
    graph = KnowledgeGraph()
    report = build_health_report(graph)
    assert report.total_functions == 0
    assert report.avg_complexity == 0.0
    assert report.high_risk_count == 0
    assert report.critical_risk_count == 0


# ---------------------------------------------------------------------------
# Integration: CodeGraph.health()
# ---------------------------------------------------------------------------

def test_self_analysis_health_report():
    """CodeGraph.health() on PROJECT_ROOT returns non-empty report."""
    from vector_graph.api.python_api import CodeGraph

    cg = CodeGraph(PROJECT_ROOT)
    report = cg.health()

    assert isinstance(report, HealthReport)
    assert report.total_functions > 0
    assert report.avg_complexity >= 1.0
    assert len(report.functions) > 0
    assert len(report.modules) > 0

    # All risk levels are valid
    for fn in report.functions:
        assert fn.risk in ("LOW", "MEDIUM", "HIGH", "CRITICAL")

    # Modules have valid fields
    for mod in report.modules:
        assert 0.0 <= mod.coupling_ratio <= 1.0
        assert 0.0 <= mod.cohesion <= 1.0
