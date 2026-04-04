"""L1 tests for python_imports.py — TDD RED phase first."""

from __future__ import annotations

from pathlib import Path

import pytest

from vector_graph._types import ExtractedImport


def _resolve(imp: ExtractedImport, from_file: str, project_root: str, all_files: set[str]) -> str | None:
    from vector_graph.parse.python_imports import resolve_import
    return resolve_import(imp, from_file, project_root, all_files)


def _from_import(module: str, names: tuple[str, ...] = (), level: int = 0, file_path: str = "") -> ExtractedImport:
    return ExtractedImport(module=module, names=names, is_from=True, level=level, file_path=file_path)


def _bare_import(module: str, file_path: str = "") -> ExtractedImport:
    return ExtractedImport(module=module, is_from=False, level=0, file_path=file_path)


# ---------------------------------------------------------------------------
# Relative import resolution
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_resolve_relative_import_same_package(tmp_project: Path):
    """from .models import User in views.py -> models.py"""
    views = str(tmp_project / "myproject" / "views.py")
    models = str(tmp_project / "myproject" / "models.py")
    all_files = {
        str(tmp_project / "myproject" / "models.py"),
        str(tmp_project / "myproject" / "utils.py"),
        str(tmp_project / "myproject" / "views.py"),
    }
    imp = _from_import(module="models", names=("User",), level=1, file_path=views)
    result = _resolve(imp, views, str(tmp_project), all_files)
    assert result == models


@pytest.mark.level1
def test_resolve_relative_import_utils(tmp_project: Path):
    """from .utils import validate_email in views.py -> utils.py"""
    views = str(tmp_project / "myproject" / "views.py")
    utils = str(tmp_project / "myproject" / "utils.py")
    all_files = {
        str(tmp_project / "myproject" / "models.py"),
        str(tmp_project / "myproject" / "utils.py"),
        str(tmp_project / "myproject" / "views.py"),
    }
    imp = _from_import(module="utils", names=("validate_email",), level=1, file_path=views)
    result = _resolve(imp, views, str(tmp_project), all_files)
    assert result == utils


@pytest.mark.level1
def test_resolve_relative_two_dots(tmp_project: Path):
    """from ..utils import helper — navigate up two directories."""
    deep_file = str(tmp_project / "myproject" / "sub" / "deep.py")
    utils = str(tmp_project / "myproject" / "utils.py")
    all_files = {
        str(tmp_project / "myproject" / "utils.py"),
        str(tmp_project / "myproject" / "models.py"),
        deep_file,
    }
    imp = _from_import(module="utils", names=("helper",), level=2, file_path=deep_file)
    result = _resolve(imp, deep_file, str(tmp_project), all_files)
    assert result == utils


@pytest.mark.level1
def test_resolve_relative_empty_module(tmp_project: Path):
    """from . import something — level=1, module='' -> package dir __init__.py or None"""
    views = str(tmp_project / "myproject" / "views.py")
    init = str(tmp_project / "myproject" / "__init__.py")
    all_files = {
        str(tmp_project / "myproject" / "models.py"),
        str(tmp_project / "myproject" / "utils.py"),
        str(tmp_project / "myproject" / "views.py"),
        init,
    }
    imp = _from_import(module="", names=("something",), level=1, file_path=views)
    result = _resolve(imp, views, str(tmp_project), all_files)
    # Resolves to __init__.py of the package
    assert result == init


# ---------------------------------------------------------------------------
# Bare import — stdlib should return None
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_stdlib_bare_import_returns_none(tmp_project: Path):
    """import logging -> None (stdlib, not in project)"""
    views = str(tmp_project / "myproject" / "views.py")
    all_files = {
        str(tmp_project / "myproject" / "models.py"),
        str(tmp_project / "myproject" / "utils.py"),
        str(tmp_project / "myproject" / "views.py"),
    }
    imp = _bare_import("logging", file_path=views)
    result = _resolve(imp, views, str(tmp_project), all_files)
    assert result is None


@pytest.mark.level1
def test_stdlib_os_import_returns_none(tmp_project: Path):
    views = str(tmp_project / "myproject" / "views.py")
    all_files = {str(tmp_project / "myproject" / "views.py")}
    imp = _bare_import("os", file_path=views)
    result = _resolve(imp, views, str(tmp_project), all_files)
    assert result is None


# ---------------------------------------------------------------------------
# Proximity bare import — same directory
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_proximity_bare_import_same_dir(tmp_project: Path):
    """import models in same directory -> models.py"""
    views = str(tmp_project / "myproject" / "views.py")
    models = str(tmp_project / "myproject" / "models.py")
    all_files = {
        str(tmp_project / "myproject" / "models.py"),
        str(tmp_project / "myproject" / "utils.py"),
        str(tmp_project / "myproject" / "views.py"),
    }
    imp = _bare_import("models", file_path=views)
    result = _resolve(imp, views, str(tmp_project), all_files)
    assert result == models


# ---------------------------------------------------------------------------
# Package (dotted) import from project root
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_package_import_from_root(tmp_project: Path):
    """from myproject.models import User -> models.py"""
    views = str(tmp_project / "myproject" / "views.py")
    models = str(tmp_project / "myproject" / "models.py")
    all_files = {
        str(tmp_project / "myproject" / "models.py"),
        str(tmp_project / "myproject" / "utils.py"),
        str(tmp_project / "myproject" / "views.py"),
    }
    imp = _from_import(module="myproject.models", names=("User",), level=0, file_path=views)
    result = _resolve(imp, views, str(tmp_project), all_files)
    assert result == models


@pytest.mark.level1
def test_package_import_utils_from_root(tmp_project: Path):
    """from myproject.utils import validate_email -> utils.py"""
    views = str(tmp_project / "myproject" / "views.py")
    utils = str(tmp_project / "myproject" / "utils.py")
    all_files = {
        str(tmp_project / "myproject" / "models.py"),
        str(tmp_project / "myproject" / "utils.py"),
        str(tmp_project / "myproject" / "views.py"),
    }
    imp = _from_import(module="myproject.utils", names=("validate_email",), level=0, file_path=views)
    result = _resolve(imp, views, str(tmp_project), all_files)
    assert result == utils


# ---------------------------------------------------------------------------
# Nonexistent module returns None
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_nonexistent_module_returns_none(tmp_project: Path):
    views = str(tmp_project / "myproject" / "views.py")
    all_files = {str(tmp_project / "myproject" / "views.py")}
    imp = _from_import(module="does_not_exist", names=("Foo",), level=0, file_path=views)
    result = _resolve(imp, views, str(tmp_project), all_files)
    assert result is None


@pytest.mark.level1
def test_nonexistent_relative_returns_none(tmp_project: Path):
    views = str(tmp_project / "myproject" / "views.py")
    all_files = {str(tmp_project / "myproject" / "views.py")}
    imp = _from_import(module="ghost", names=("X",), level=1, file_path=views)
    result = _resolve(imp, views, str(tmp_project), all_files)
    assert result is None


# ---------------------------------------------------------------------------
# Circular imports don't infinite loop
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_circular_imports_dont_hang(tmp_project: Path):
    """Circular: a imports b, b imports a — resolver just returns path, no loop."""
    a = str(tmp_project / "myproject" / "models.py")
    b = str(tmp_project / "myproject" / "utils.py")
    all_files = {a, b}
    imp = _from_import(module="utils", names=("X",), level=1, file_path=a)
    result = _resolve(imp, a, str(tmp_project), all_files)
    assert result == b


# ---------------------------------------------------------------------------
# Suffix match fallback
# ---------------------------------------------------------------------------

@pytest.mark.level1
def test_suffix_match_fallback(tmp_project: Path):
    """If dotted module path suffix matches a file, use it."""
    some_file = str(tmp_project / "myproject" / "views.py")
    models = str(tmp_project / "myproject" / "models.py")
    all_files = {
        str(tmp_project / "myproject" / "models.py"),
        str(tmp_project / "myproject" / "utils.py"),
        str(tmp_project / "myproject" / "views.py"),
    }
    # "something.models" -> suffix "models" -> matches models.py in all_files
    imp = _from_import(module="something.models", names=("User",), level=0, file_path=some_file)
    result = _resolve(imp, some_file, str(tmp_project), all_files)
    assert result == models
