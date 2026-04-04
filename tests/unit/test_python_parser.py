"""L1 tests for python_parser.py — TDD RED phase first."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from vector_graph._types import (
    ExtractedFunction,
    ExtractedClass,
    ExtractedImport,
    ExtractedCall,
    ExtractedAssignment,
    FileParseResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse(source: str, path: str = "test.py"):
    from vector_graph.parse.python_parser import parse_file
    return parse_file(path, source)


# ---------------------------------------------------------------------------
# Basic file-level sanity
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_returns_file_parse_result():
    result = _parse("x = 1")
    assert isinstance(result, FileParseResult)


@pytest.mark.level1
def test_empty_file_returns_empty_result():
    result = _parse("")
    assert result.functions == ()
    assert result.classes == ()
    assert result.imports == ()
    assert result.calls == ()
    assert result.assignments == ()


@pytest.mark.level1
def test_syntax_error_returns_empty_no_crash():
    result = _parse("def foo(: broken syntax !!!")
    assert isinstance(result, FileParseResult)
    assert result.functions == ()
    assert result.classes == ()


@pytest.mark.level1
def test_file_path_preserved():
    result = _parse("x = 1", path="/some/file.py")
    assert result.file_path == "/some/file.py"


# ---------------------------------------------------------------------------
# Parse models.py via tmp_project
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_models_finds_user_class(tmp_project: Path):
    from vector_graph.parse.python_parser import parse_file
    models = tmp_project / "myproject" / "models.py"
    result = parse_file(str(models))
    names = {c.name for c in result.classes}
    assert "User" in names


@pytest.mark.level1
def test_models_finds_post_class(tmp_project: Path):
    from vector_graph.parse.python_parser import parse_file
    models = tmp_project / "myproject" / "models.py"
    result = parse_file(str(models))
    names = {c.name for c in result.classes}
    assert "Post" in names


@pytest.mark.level1
def test_models_finds_full_name_method(tmp_project: Path):
    from vector_graph.parse.python_parser import parse_file
    models = tmp_project / "myproject" / "models.py"
    result = parse_file(str(models))
    names = {f.name for f in result.functions}
    assert "full_name" in names


@pytest.mark.level1
def test_models_finds_summary_method(tmp_project: Path):
    from vector_graph.parse.python_parser import parse_file
    models = tmp_project / "myproject" / "models.py"
    result = parse_file(str(models))
    names = {f.name for f in result.functions}
    assert "summary" in names


@pytest.mark.level1
def test_models_full_name_is_method(tmp_project: Path):
    from vector_graph.parse.python_parser import parse_file
    models = tmp_project / "myproject" / "models.py"
    result = parse_file(str(models))
    fn = next(f for f in result.functions if f.name == "full_name")
    assert fn.is_method is True


@pytest.mark.level1
def test_models_full_name_owner_class(tmp_project: Path):
    from vector_graph.parse.python_parser import parse_file
    models = tmp_project / "myproject" / "models.py"
    result = parse_file(str(models))
    fn = next(f for f in result.functions if f.name == "full_name")
    assert fn.owner_class == "User"


# ---------------------------------------------------------------------------
# Parse utils.py
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_utils_finds_validate_email(tmp_project: Path):
    from vector_graph.parse.python_parser import parse_file
    utils = tmp_project / "myproject" / "utils.py"
    result = parse_file(str(utils))
    names = {f.name for f in result.functions}
    assert "validate_email" in names


@pytest.mark.level1
def test_utils_finds_format_name(tmp_project: Path):
    from vector_graph.parse.python_parser import parse_file
    utils = tmp_project / "myproject" / "utils.py"
    result = parse_file(str(utils))
    names = {f.name for f in result.functions}
    assert "format_name" in names


@pytest.mark.level1
def test_utils_finds_internal_helper(tmp_project: Path):
    from vector_graph.parse.python_parser import parse_file
    utils = tmp_project / "myproject" / "utils.py"
    result = parse_file(str(utils))
    names = {f.name for f in result.functions}
    assert "_internal_helper" in names


# ---------------------------------------------------------------------------
# Parse views.py
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_views_finds_create_user(tmp_project: Path):
    from vector_graph.parse.python_parser import parse_file
    views = tmp_project / "myproject" / "views.py"
    result = parse_file(str(views))
    names = {f.name for f in result.functions}
    assert "create_user" in names


@pytest.mark.level1
def test_views_finds_create_post(tmp_project: Path):
    from vector_graph.parse.python_parser import parse_file
    views = tmp_project / "myproject" / "views.py"
    result = parse_file(str(views))
    names = {f.name for f in result.functions}
    assert "create_post" in names


@pytest.mark.level1
def test_views_finds_render_feed(tmp_project: Path):
    from vector_graph.parse.python_parser import parse_file
    views = tmp_project / "myproject" / "views.py"
    result = parse_file(str(views))
    names = {f.name for f in result.functions}
    assert "render_feed" in names


# ---------------------------------------------------------------------------
# Function extraction: metadata fields
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_function_start_and_end_line():
    src = textwrap.dedent("""\
        def foo():
            return 1
    """)
    result = _parse(src)
    fn = result.functions[0]
    assert fn.start_line == 1
    assert fn.end_line == 2


@pytest.mark.level1
def test_function_parameters():
    src = "def foo(x, y, z): pass"
    result = _parse(src)
    fn = result.functions[0]
    assert "x" in fn.parameters
    assert "y" in fn.parameters
    assert "z" in fn.parameters


@pytest.mark.level1
def test_function_parameter_types():
    src = "def foo(x: int, y: str) -> bool: pass"
    result = _parse(src)
    fn = result.functions[0]
    assert fn.parameter_types == ("int", "str")


@pytest.mark.level1
def test_function_return_type():
    src = "def foo() -> bool: pass"
    result = _parse(src)
    fn = result.functions[0]
    assert fn.return_type == "bool"


@pytest.mark.level1
def test_function_no_return_type():
    src = "def foo(): pass"
    result = _parse(src)
    fn = result.functions[0]
    assert fn.return_type is None


@pytest.mark.level1
def test_function_docstring():
    src = textwrap.dedent('''\
        def foo():
            """This is a docstring."""
            pass
    ''')
    result = _parse(src)
    fn = result.functions[0]
    assert fn.docstring == "This is a docstring."


@pytest.mark.level1
def test_function_no_docstring():
    src = "def foo(): pass"
    result = _parse(src)
    fn = result.functions[0]
    assert fn.docstring is None


@pytest.mark.level1
def test_function_is_not_method_by_default():
    src = "def foo(): pass"
    result = _parse(src)
    fn = result.functions[0]
    assert fn.is_method is False


@pytest.mark.level1
def test_function_decorator_property():
    src = textwrap.dedent("""\
        class Foo:
            @property
            def bar(self) -> int:
                return 1
    """)
    result = _parse(src)
    fn = next(f for f in result.functions if f.name == "bar")
    assert "property" in fn.decorators


@pytest.mark.level1
def test_function_decorator_dataclass_frozen():
    src = textwrap.dedent("""\
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class Foo:
            x: int
    """)
    result = _parse(src)
    cls = next(c for c in result.classes if c.name == "Foo")
    assert any("dataclass" in d for d in cls.decorators)


# ---------------------------------------------------------------------------
# Async function detection
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_async_function_is_async():
    src = "async def fetch(): pass"
    result = _parse(src)
    fn = result.functions[0]
    assert fn.is_async is True


@pytest.mark.level1
def test_sync_function_is_not_async():
    src = "def fetch(): pass"
    result = _parse(src)
    fn = result.functions[0]
    assert fn.is_async is False


# ---------------------------------------------------------------------------
# Class extraction
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_class_name():
    src = "class MyClass: pass"
    result = _parse(src)
    assert result.classes[0].name == "MyClass"


@pytest.mark.level1
def test_class_bases():
    src = "class Child(Parent, Mixin): pass"
    result = _parse(src)
    cls = result.classes[0]
    assert "Parent" in cls.bases
    assert "Mixin" in cls.bases


@pytest.mark.level1
def test_class_docstring():
    src = textwrap.dedent('''\
        class Foo:
            """Foo docstring."""
            pass
    ''')
    result = _parse(src)
    assert result.classes[0].docstring == "Foo docstring."


@pytest.mark.level1
def test_class_start_end_line():
    src = textwrap.dedent("""\
        class Foo:
            x: int = 1
            y: str = "hello"
    """)
    result = _parse(src)
    cls = result.classes[0]
    assert cls.start_line == 1
    assert cls.end_line == 3


# ---------------------------------------------------------------------------
# Import extraction
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_import_bare():
    src = "import logging"
    result = _parse(src)
    imp = result.imports[0]
    assert imp.module == "logging"
    assert imp.is_from is False
    assert imp.level == 0


@pytest.mark.level1
def test_import_from():
    src = "from pathlib import Path"
    result = _parse(src)
    imp = result.imports[0]
    assert imp.module == "pathlib"
    assert "Path" in imp.names
    assert imp.is_from is True


@pytest.mark.level1
def test_import_from_relative():
    src = "from .models import User"
    result = _parse(src)
    imp = result.imports[0]
    assert imp.is_from is True
    assert imp.level == 1
    assert "User" in imp.names


@pytest.mark.level1
def test_import_multiple_names():
    src = "from os.path import join, exists, dirname"
    result = _parse(src)
    imp = result.imports[0]
    assert "join" in imp.names
    assert "exists" in imp.names
    assert "dirname" in imp.names


@pytest.mark.level1
def test_import_alias():
    src = "import numpy as np"
    result = _parse(src)
    imp = result.imports[0]
    assert imp.module == "numpy"
    assert "np" in imp.aliases


# ---------------------------------------------------------------------------
# Call extraction
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_call_bare_function():
    src = textwrap.dedent("""\
        def caller():
            foo()
    """)
    result = _parse(src)
    calls = [c for c in result.calls if c.callee_name == "foo"]
    assert len(calls) == 1
    assert calls[0].is_attribute is False


@pytest.mark.level1
def test_call_method():
    src = textwrap.dedent("""\
        def caller():
            obj.method()
    """)
    result = _parse(src)
    calls = [c for c in result.calls if c.callee_name == "method"]
    assert len(calls) == 1
    assert calls[0].is_attribute is True
    assert calls[0].receiver == "obj"


@pytest.mark.level1
def test_call_caller_attribution():
    src = textwrap.dedent("""\
        def my_func():
            helper()
    """)
    result = _parse(src)
    calls = [c for c in result.calls if c.callee_name == "helper"]
    assert calls[0].caller_name == "my_func"


@pytest.mark.level1
def test_call_arg_count():
    src = textwrap.dedent("""\
        def caller():
            foo(1, 2, 3)
    """)
    result = _parse(src)
    calls = [c for c in result.calls if c.callee_name == "foo"]
    assert calls[0].arg_count == 3


# ---------------------------------------------------------------------------
# Assignment extraction
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_annotated_assignment_type():
    src = "x: int = 5"
    result = _parse(src)
    assigns = [a for a in result.assignments if a.name == "x"]
    assert len(assigns) == 1
    assert assigns[0].declared_type == "int"


@pytest.mark.level1
def test_bare_assignment_no_type():
    src = "x = 5"
    result = _parse(src)
    assigns = [a for a in result.assignments if a.name == "x"]
    assert len(assigns) == 1
    assert assigns[0].declared_type is None


@pytest.mark.level1
def test_multiple_functions_extracted():
    src = textwrap.dedent("""\
        def alpha(): pass
        def beta(): pass
        def gamma(): pass
    """)
    result = _parse(src)
    names = {f.name for f in result.functions}
    assert names == {"alpha", "beta", "gamma"}
