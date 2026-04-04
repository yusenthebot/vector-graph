"""Tests for vector_graph.analysis.type_inference."""

from __future__ import annotations

import textwrap

import pytest

from vector_graph._types import (
    ExtractedAssignment,
    ExtractedFunction,
    FileParseResult,
    NodeLabel,
    SymbolDef,
)
from vector_graph.analysis.type_inference import TypeBinding, TypeMap, build_type_map
from vector_graph.graph.symbol_table import SymbolTable
from vector_graph.parse.python_parser import parse_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_symbol_table(*class_names: str, file_path: str = "test.py") -> SymbolTable:
    """Return a SymbolTable with the given class names registered."""
    st = SymbolTable()
    for name in class_names:
        st.register(
            SymbolDef(
                node_id=f"cls:{name}",
                name=name,
                file_path=file_path,
                label=NodeLabel.CLASS,
            )
        )
    return st


def _parse(source: str, file_path: str = "test.py") -> FileParseResult:
    return parse_file(file_path, source=textwrap.dedent(source))


# ---------------------------------------------------------------------------
# TypeBinding — unit tests
# ---------------------------------------------------------------------------

def test_type_binding_from_constructor() -> None:
    """x = Foo() where Foo is a known class => TypeBinding(inferred_type='Foo', confidence=0.9)."""
    source = """\
        class Foo:
            pass

        x = Foo()
    """
    result = _parse(source)
    st = _make_symbol_table("Foo")
    type_map = build_type_map({"test.py": result}, st)

    binding = type_map.lookup("test.py", "<module>", "x")
    assert binding is not None
    assert binding.variable_name == "x"
    assert binding.inferred_type == "Foo"
    assert binding.confidence == pytest.approx(0.9)


def test_type_binding_from_annotation() -> None:
    """x: Foo = bar() => TypeBinding(inferred_type='Foo', confidence=0.95)."""
    source = """\
        class Foo:
            pass

        x: Foo = bar()
    """
    result = _parse(source)
    st = _make_symbol_table("Foo")
    type_map = build_type_map({"test.py": result}, st)

    binding = type_map.lookup("test.py", "<module>", "x")
    assert binding is not None
    assert binding.inferred_type == "Foo"
    assert binding.confidence == pytest.approx(0.95)


def test_type_binding_from_module_constructor() -> None:
    """x = mod.Foo() => inferred_type='Foo' (strip module prefix)."""
    source = """\
        x = mod.Foo()
    """
    result = _parse(source)
    # Register Foo as a known class
    st = _make_symbol_table("Foo")
    type_map = build_type_map({"test.py": result}, st)

    binding = type_map.lookup("test.py", "<module>", "x")
    assert binding is not None
    assert binding.inferred_type == "Foo"
    assert binding.confidence == pytest.approx(0.9)


def test_type_binding_self_attr() -> None:
    """In __init__, self.graph = KnowledgeGraph() => binds self.graph -> 'KnowledgeGraph'."""
    source = """\
        class MyNode:
            def __init__(self):
                self.graph = KnowledgeGraph()
    """
    result = _parse(source)
    st = _make_symbol_table("KnowledgeGraph")
    type_map = build_type_map({"test.py": result}, st)

    # self.graph should be bound under class scope "MyNode"
    binding = type_map.lookup("test.py", "MyNode", "self.graph")
    assert binding is not None
    assert binding.inferred_type == "KnowledgeGraph"
    assert binding.variable_name == "self.graph"


def test_type_binding_parameter_annotation() -> None:
    """def f(x: Foo) => within scope 'f', x is Foo with confidence 0.95."""
    source = """\
        class Foo:
            pass

        def f(x: Foo) -> None:
            pass
    """
    result = _parse(source)
    st = _make_symbol_table("Foo")
    type_map = build_type_map({"test.py": result}, st)

    binding = type_map.lookup("test.py", "f", "x")
    assert binding is not None
    assert binding.inferred_type == "Foo"
    assert binding.scope == "f"
    assert binding.confidence == pytest.approx(0.95)


def test_type_binding_ignores_unknown_constructors() -> None:
    """x = unknown_func() where unknown_func is not a class => no binding."""
    source = """\
        x = unknown_func()
    """
    result = _parse(source)
    # Empty symbol table — no known classes
    st = SymbolTable()
    type_map = build_type_map({"test.py": result}, st)

    binding = type_map.lookup("test.py", "<module>", "x")
    assert binding is None


def test_type_binding_multi_assignment() -> None:
    """x = Foo(); x = Bar() => last assignment wins (x is Bar)."""
    source = """\
        x = Foo()
        x = Bar()
    """
    result = _parse(source)
    st = _make_symbol_table("Foo", "Bar")
    type_map = build_type_map({"test.py": result}, st)

    binding = type_map.lookup("test.py", "<module>", "x")
    assert binding is not None
    assert binding.inferred_type == "Bar"


# ---------------------------------------------------------------------------
# TypeMap — lookup tests
# ---------------------------------------------------------------------------

def test_type_map_lookup_scoped() -> None:
    """Function-local binding shadows module-level binding of same name."""
    source = """\
        class Foo:
            pass

        class Bar:
            pass

        x = Foo()

        def my_func(x: Bar) -> None:
            pass
    """
    result = _parse(source)
    st = _make_symbol_table("Foo", "Bar")
    type_map = build_type_map({"test.py": result}, st)

    # Inside my_func, x is Bar (parameter annotation)
    binding = type_map.lookup("test.py", "my_func", "x")
    assert binding is not None
    assert binding.inferred_type == "Bar"
    assert binding.scope == "my_func"

    # Module-level x is Foo
    module_binding = type_map.lookup("test.py", "<module>", "x")
    assert module_binding is not None
    assert module_binding.inferred_type == "Foo"


def test_type_map_lookup_module_scope() -> None:
    """Module-level assignment is accessible with scope '<module>'."""
    source = """\
        class Config:
            pass

        cfg = Config()
    """
    result = _parse(source)
    st = _make_symbol_table("Config")
    type_map = build_type_map({"test.py": result}, st)

    binding = type_map.lookup("test.py", "<module>", "cfg")
    assert binding is not None
    assert binding.inferred_type == "Config"
    assert binding.scope == "<module>"


def test_type_map_lookup_attribute() -> None:
    """'self.graph' lookup with class context returns correct type."""
    source = """\
        class Runner:
            def __init__(self):
                self.graph = KnowledgeGraph()
    """
    result = _parse(source)
    st = _make_symbol_table("KnowledgeGraph")
    type_map = build_type_map({"test.py": result}, st)

    # lookup_attribute should resolve self.graph -> KnowledgeGraph
    inferred = type_map.lookup_attribute("test.py", "Runner", "self.graph")
    assert inferred == "KnowledgeGraph"


def test_type_map_lookup_missing() -> None:
    """Lookup for non-existent variable returns None."""
    type_map = TypeMap()
    result = type_map.lookup("nonexistent.py", "<module>", "xyz")
    assert result is None


# ---------------------------------------------------------------------------
# build_type_map — integration-style tests
# ---------------------------------------------------------------------------

def test_build_type_map_empty() -> None:
    """Empty parse_results => empty TypeMap (all lookups return None)."""
    st = SymbolTable()
    type_map = build_type_map({}, st)

    assert type_map.lookup("any.py", "<module>", "x") is None


def test_build_type_map_real_file() -> None:
    """Parse a multi-class file and verify key bindings are present."""
    source = """\
        class Engine:
            pass

        class Car:
            def __init__(self):
                self.engine = Engine()

        def drive(car: Car) -> None:
            pass

        my_car = Car()
    """
    result = _parse(source)
    st = _make_symbol_table("Engine", "Car")
    type_map = build_type_map({"test.py": result}, st)

    # Module-level my_car -> Car
    car_binding = type_map.lookup("test.py", "<module>", "my_car")
    assert car_binding is not None
    assert car_binding.inferred_type == "Car"

    # Parameter annotation in 'drive': car -> Car
    param_binding = type_map.lookup("test.py", "drive", "car")
    assert param_binding is not None
    assert param_binding.inferred_type == "Car"

    # self.engine in Car.__init__ -> Engine
    attr_type = type_map.lookup_attribute("test.py", "Car", "self.engine")
    assert attr_type == "Engine"
