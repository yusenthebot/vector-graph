"""L0 unit tests for SymbolTable."""

from __future__ import annotations

import pytest

from vector_graph._types import NodeLabel, SymbolDef
from vector_graph.graph.symbol_table import SymbolTable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_sym(
    name: str,
    file_path: str = "/src/a.py",
    label: NodeLabel = NodeLabel.FUNCTION,
    owner_id: str | None = None,
    node_id: str | None = None,
) -> SymbolDef:
    return SymbolDef(
        node_id=node_id or f"{file_path}::{name}",
        name=name,
        file_path=file_path,
        label=label,
        owner_id=owner_id,
    )


# ---------------------------------------------------------------------------
# register / lookup_exact
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_register_and_lookup_exact() -> None:
    st = SymbolTable()
    sym = make_sym("my_func", "/src/a.py")
    st.register(sym)
    results = st.lookup_exact("/src/a.py", "my_func")
    assert len(results) == 1
    assert results[0] is sym


@pytest.mark.level0
def test_lookup_exact_missing_file_returns_empty() -> None:
    st = SymbolTable()
    assert st.lookup_exact("/no/file.py", "f") == []


@pytest.mark.level0
def test_lookup_exact_missing_name_returns_empty() -> None:
    st = SymbolTable()
    sym = make_sym("my_func", "/src/a.py")
    st.register(sym)
    assert st.lookup_exact("/src/a.py", "other") == []


@pytest.mark.level0
def test_lookup_exact_multiple_same_name() -> None:
    """Two overloads in the same file with the same name."""
    st = SymbolTable()
    s1 = SymbolDef(node_id="n1", name="process", file_path="/src/a.py", label=NodeLabel.FUNCTION)
    s2 = SymbolDef(node_id="n2", name="process", file_path="/src/a.py", label=NodeLabel.FUNCTION)
    st.register(s1)
    st.register(s2)
    results = st.lookup_exact("/src/a.py", "process")
    assert len(results) == 2


# ---------------------------------------------------------------------------
# lookup_global
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_lookup_global_returns_all_files() -> None:
    st = SymbolTable()
    s1 = make_sym("helper", "/src/a.py")
    s2 = make_sym("helper", "/src/b.py")
    st.register(s1)
    st.register(s2)
    results = st.lookup_global("helper")
    assert len(results) == 2
    node_ids = {r.node_id for r in results}
    assert s1.node_id in node_ids
    assert s2.node_id in node_ids


@pytest.mark.level0
def test_lookup_global_missing_returns_empty() -> None:
    st = SymbolTable()
    assert st.lookup_global("nonexistent") == []


# ---------------------------------------------------------------------------
# lookup_fuzzy_callable
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_lookup_fuzzy_callable_only_functions_methods() -> None:
    st = SymbolTable()
    fn = make_sym("process", "/src/a.py", label=NodeLabel.FUNCTION)
    meth = make_sym("run", "/src/a.py", label=NodeLabel.METHOD)
    cls = make_sym("MyClass", "/src/a.py", label=NodeLabel.CLASS)
    var = make_sym("counter", "/src/a.py", label=NodeLabel.VARIABLE)
    st.register(fn)
    st.register(meth)
    st.register(cls)
    st.register(var)
    results = st.lookup_fuzzy_callable("process")
    assert any(r.name == "process" and r.label == NodeLabel.FUNCTION for r in results)


@pytest.mark.level0
def test_lookup_fuzzy_callable_excludes_classes() -> None:
    st = SymbolTable()
    st.register(make_sym("MyClass", "/src/a.py", label=NodeLabel.CLASS))
    results = st.lookup_fuzzy_callable("MyClass")
    assert all(r.label in (NodeLabel.FUNCTION, NodeLabel.METHOD) for r in results)


@pytest.mark.level0
def test_lookup_fuzzy_callable_partial_match() -> None:
    st = SymbolTable()
    st.register(make_sym("process_data", "/src/a.py", label=NodeLabel.FUNCTION))
    st.register(make_sym("process_raw", "/src/b.py", label=NodeLabel.FUNCTION))
    st.register(make_sym("unrelated", "/src/c.py", label=NodeLabel.FUNCTION))
    results = st.lookup_fuzzy_callable("process")
    names = {r.name for r in results}
    assert "process_data" in names
    assert "process_raw" in names
    assert "unrelated" not in names


# ---------------------------------------------------------------------------
# field_by_owner lookup
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_field_by_owner() -> None:
    st = SymbolTable()
    field_sym = SymbolDef(
        node_id="n1",
        name="email",
        file_path="/src/a.py",
        label=NodeLabel.PROPERTY,
        owner_id="class-User",
    )
    st.register(field_sym)
    results = st.lookup_field_by_owner("class-User", "email")
    assert len(results) == 1
    assert results[0] is field_sym


@pytest.mark.level0
def test_field_by_owner_missing_returns_empty() -> None:
    st = SymbolTable()
    assert st.lookup_field_by_owner("no-owner", "no-field") == []


# ---------------------------------------------------------------------------
# remove_file
# ---------------------------------------------------------------------------

@pytest.mark.level0
def test_remove_file_removes_all_symbols() -> None:
    st = SymbolTable()
    st.register(make_sym("f1", "/src/a.py"))
    st.register(make_sym("f2", "/src/a.py"))
    st.register(make_sym("f3", "/src/b.py"))
    st.remove_file("/src/a.py")
    assert st.lookup_exact("/src/a.py", "f1") == []
    assert st.lookup_exact("/src/a.py", "f2") == []
    # global index cleaned up
    assert not any(s.file_path == "/src/a.py" for s in st.lookup_global("f1"))
    # other file unaffected
    assert len(st.lookup_exact("/src/b.py", "f3")) == 1


@pytest.mark.level0
def test_remove_file_missing_is_noop() -> None:
    st = SymbolTable()
    st.remove_file("/no/such/file.py")  # should not raise
