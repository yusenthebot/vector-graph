"""L1 tests for python_types.py — TDD RED phase first."""

from __future__ import annotations

import textwrap

import pytest

from vector_graph._types import (
    ExtractedFunction,
    ExtractedAssignment,
    FileParseResult,
)


def _parse(source: str, path: str = "test.py") -> FileParseResult:
    from vector_graph.parse.python_parser import parse_file
    return parse_file(path, source)


def _env(source: str, path: str = "test.py") -> dict[str, str]:
    from vector_graph.parse.python_types import extract_type_env
    result = _parse(source, path)
    return extract_type_env(result)


# ---------------------------------------------------------------------------
# Parameter type extraction
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_parameter_types_int_str():
    src = "def foo(x: int, y: str): pass"
    result = _parse(src)
    fn = result.functions[0]
    assert fn.parameter_types == ("int", "str")


@pytest.mark.level1
def test_parameter_types_no_annotations():
    src = "def foo(x, y): pass"
    result = _parse(src)
    fn = result.functions[0]
    # Unannotated params get empty string or omitted
    assert len(fn.parameter_types) == 0 or all(t == "" for t in fn.parameter_types)


@pytest.mark.level1
def test_parameter_types_partial_annotations():
    src = "def foo(x: int, y): pass"
    result = _parse(src)
    fn = result.functions[0]
    # "int" for x, "" or missing for y
    assert fn.parameter_types[0] == "int"


# ---------------------------------------------------------------------------
# Return type extraction
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_return_type_bool():
    src = "def foo() -> bool: pass"
    result = _parse(src)
    assert result.functions[0].return_type == "bool"


@pytest.mark.level1
def test_return_type_none_annotation():
    src = "def foo() -> None: pass"
    result = _parse(src)
    assert result.functions[0].return_type == "None"


@pytest.mark.level1
def test_return_type_missing():
    src = "def foo(): pass"
    result = _parse(src)
    assert result.functions[0].return_type is None


# ---------------------------------------------------------------------------
# Complex type annotations
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_complex_type_list_str():
    src = "def foo(items: list[str]) -> None: pass"
    result = _parse(src)
    fn = result.functions[0]
    assert "list[str]" in fn.parameter_types


@pytest.mark.level1
def test_complex_type_dict():
    src = "def foo(d: dict[str, int]) -> None: pass"
    result = _parse(src)
    fn = result.functions[0]
    assert "dict[str, int]" in fn.parameter_types


@pytest.mark.level1
def test_complex_type_tuple():
    src = "def foo(t: tuple[int, ...]) -> None: pass"
    result = _parse(src)
    fn = result.functions[0]
    assert "tuple[int, ...]" in fn.parameter_types


@pytest.mark.level1
def test_complex_type_union_optional():
    src = "def foo(x: str | None) -> None: pass"
    result = _parse(src)
    fn = result.functions[0]
    assert "str | None" in fn.parameter_types


@pytest.mark.level1
def test_return_type_complex_list():
    src = "def foo() -> list[str]: pass"
    result = _parse(src)
    assert result.functions[0].return_type == "list[str]"


# ---------------------------------------------------------------------------
# Class variable types
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_class_variable_type_str():
    src = textwrap.dedent("""\
        class Foo:
            name: str = ""
    """)
    result = _parse(src)
    assigns = [a for a in result.assignments if a.name == "name"]
    assert len(assigns) == 1
    assert assigns[0].declared_type == "str"


@pytest.mark.level1
def test_class_variable_type_int():
    src = textwrap.dedent("""\
        class Foo:
            count: int = 0
    """)
    result = _parse(src)
    assigns = [a for a in result.assignments if a.name == "count"]
    assert assigns[0].declared_type == "int"


# ---------------------------------------------------------------------------
# Assignment type annotation extraction
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_assignment_annotated_int():
    src = "x: int = 5"
    result = _parse(src)
    assigns = [a for a in result.assignments if a.name == "x"]
    assert assigns[0].declared_type == "int"


@pytest.mark.level1
def test_assignment_annotated_str():
    src = 'name: str = "hello"'
    result = _parse(src)
    assigns = [a for a in result.assignments if a.name == "name"]
    assert assigns[0].declared_type == "str"


# ---------------------------------------------------------------------------
# Type environment: variable -> inferred type
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_type_env_annotated_variables():
    src = textwrap.dedent("""\
        x: int = 5
        name: str = "hello"
        flag: bool = True
    """)
    env = _env(src)
    assert env.get("x") == "int"
    assert env.get("name") == "str"
    assert env.get("flag") == "bool"


@pytest.mark.level1
def test_type_env_constructor_call():
    src = textwrap.dedent("""\
        class User:
            pass

        u = User()
    """)
    env = _env(src)
    assert env.get("u") == "User"


@pytest.mark.level1
def test_type_env_empty_for_plain_assignment():
    src = "x = 5"
    env = _env(src)
    # No annotation — not in type env (or maps to None/"")
    assert env.get("x") in (None, "", "int")  # None or inferred


@pytest.mark.level1
def test_type_env_cross_file_constructor(tmp_project):
    """from models import User; u = User() -> u: User"""
    from vector_graph.parse.python_parser import parse_file
    from vector_graph.parse.python_types import extract_type_env

    src = textwrap.dedent("""\
        from .models import User

        u = User()
    """)
    result = parse_file("views.py", src)
    env = extract_type_env(result)
    assert env.get("u") == "User"


@pytest.mark.level1
def test_type_env_multiple_constructors():
    src = textwrap.dedent("""\
        class Foo:
            pass

        class Bar:
            pass

        a = Foo()
        b = Bar()
    """)
    env = _env(src)
    assert env.get("a") == "Foo"
    assert env.get("b") == "Bar"


@pytest.mark.level1
def test_type_env_parameter_types_from_function():
    """Parameters with annotations contribute to type env within function scope."""
    src = textwrap.dedent("""\
        def process(items: list[str], count: int) -> bool:
            pass
    """)
    result = _parse(src)
    fn = result.functions[0]
    assert fn.parameter_types == ("list[str]", "int")
    assert fn.return_type == "bool"
