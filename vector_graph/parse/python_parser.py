"""Python source parser using stdlib ast.

Extracts functions, classes, imports, calls, and assignments from a Python file.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from vector_graph._types import (
    ExtractedAssignment,
    ExtractedCall,
    ExtractedClass,
    ExtractedFunction,
    ExtractedImport,
    FileParseResult,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_file(file_path: str, source: str | None = None) -> FileParseResult:
    """Parse a Python file using stdlib ast.

    Args:
        file_path: Absolute path to the Python file.
        source:    Source text. If None the file is read from disk.

    Returns:
        FileParseResult with all extracted elements, or an empty result on
        SyntaxError / IO error.
    """
    if source is None:
        try:
            source = Path(file_path).read_text(encoding="utf-8")
        except OSError:
            return FileParseResult(file_path=file_path)

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return FileParseResult(file_path=file_path)

    visitor = _Visitor(file_path)
    try:
        visitor.visit(tree)
    except RecursionError:
        return FileParseResult(file_path=file_path)

    return FileParseResult(
        file_path=file_path,
        functions=tuple(visitor.functions),
        classes=tuple(visitor.classes),
        imports=tuple(visitor.imports),
        calls=tuple(visitor.calls),
        assignments=tuple(visitor.assignments),
    )


# ---------------------------------------------------------------------------
# AST visitor
# ---------------------------------------------------------------------------

class _Visitor(ast.NodeVisitor):
    """Walk the AST and collect extracted elements."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

        self.functions: list[ExtractedFunction] = []
        self.classes: list[ExtractedClass] = []
        self.imports: list[ExtractedImport] = []
        self.calls: list[ExtractedCall] = []
        self.assignments: list[ExtractedAssignment] = []

        # Scope stack: each entry is {"name": str, "kind": "function"|"class"}
        self._scope: list[dict[str, str]] = []

    # ------------------------------------------------------------------
    # Scope helpers
    # ------------------------------------------------------------------

    def _current_function(self) -> str | None:
        for frame in reversed(self._scope):
            if frame["kind"] == "function":
                return frame["name"]
        return None

    def _current_class(self) -> str | None:
        for frame in reversed(self._scope):
            if frame["kind"] == "class":
                return frame["name"]
        return None

    # ------------------------------------------------------------------
    # Functions
    # ------------------------------------------------------------------

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        is_async = isinstance(node, ast.AsyncFunctionDef)
        owner_class = self._current_class()
        is_method = owner_class is not None

        params, param_types = _extract_params(node)
        return_type = _unparse_annotation(node.returns)
        decorators = _extract_decorators(node)
        docstring = ast.get_docstring(node)

        self.functions.append(
            ExtractedFunction(
                name=node.name,
                file_path=self.file_path,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                is_method=is_method,
                is_async=is_async,
                owner_class=owner_class,
                parameters=tuple(params),
                parameter_types=tuple(param_types),
                return_type=return_type,
                decorators=tuple(decorators),
                docstring=docstring,
            )
        )

        self._scope.append({"name": node.name, "kind": "function"})
        self.generic_visit(node)
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    # ------------------------------------------------------------------
    # Classes
    # ------------------------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        bases = _extract_bases(node)
        decorators = _extract_decorators(node)
        docstring = ast.get_docstring(node)

        self.classes.append(
            ExtractedClass(
                name=node.name,
                file_path=self.file_path,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                bases=tuple(bases),
                decorators=tuple(decorators),
                docstring=docstring,
            )
        )

        self._scope.append({"name": node.name, "kind": "class"})
        self.generic_visit(node)
        self._scope.pop()

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            aliases: tuple[str, ...] = (alias.asname,) if alias.asname else ()
            self.imports.append(
                ExtractedImport(
                    module=alias.name,
                    names=(),
                    aliases=aliases,
                    is_from=False,
                    level=0,
                    file_path=self.file_path,
                    line=node.lineno,
                )
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        names: list[str] = []
        aliases: list[str] = []
        for alias in node.names:
            names.append(alias.name)
            if alias.asname:
                aliases.append(alias.asname)
        self.imports.append(
            ExtractedImport(
                module=module,
                names=tuple(names),
                aliases=tuple(aliases),
                is_from=True,
                level=node.level,
                file_path=self.file_path,
                line=node.lineno,
            )
        )
        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Calls
    # ------------------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        caller_name = self._current_function()
        caller_class = self._current_class()
        arg_count = len(node.args) + len(node.keywords)

        func = node.func
        if isinstance(func, ast.Name):
            self.calls.append(
                ExtractedCall(
                    callee_name=func.id,
                    file_path=self.file_path,
                    line=node.lineno,
                    caller_name=caller_name,
                    caller_class=caller_class,
                    arg_count=arg_count,
                    is_attribute=False,
                    receiver=None,
                )
            )
        elif isinstance(func, ast.Attribute):
            receiver = _unparse_expr(func.value)
            self.calls.append(
                ExtractedCall(
                    callee_name=func.attr,
                    file_path=self.file_path,
                    line=node.lineno,
                    caller_name=caller_name,
                    caller_class=caller_class,
                    arg_count=arg_count,
                    is_attribute=True,
                    receiver=receiver,
                )
            )
        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Assignments
    # ------------------------------------------------------------------

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Handle `name: Type = value` assignments."""
        declared_type = _unparse_annotation(node.annotation)
        name = _target_name(node.target)
        if name:
            self.assignments.append(
                ExtractedAssignment(
                    name=name,
                    file_path=self.file_path,
                    line=node.lineno,
                    declared_type=declared_type,
                    value_type=None,
                )
            )
        # Do NOT generic_visit into annotation expressions — they can be deeply nested

    def visit_Assign(self, node: ast.Assign) -> None:
        """Handle `name = value` assignments (no annotation)."""
        value_type = _infer_value_type(node.value)
        for target in node.targets:
            name = _target_name(target)
            if name:
                self.assignments.append(
                    ExtractedAssignment(
                        name=name,
                        file_path=self.file_path,
                        line=node.lineno,
                        declared_type=None,
                        value_type=value_type,
                    )
                )
        # Do NOT generic_visit into value expressions — they can be deeply nested


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _unparse_annotation(node: ast.expr | None) -> str | None:
    """Convert an annotation AST node to a string using ast.unparse."""
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _unparse_expr(node: ast.expr) -> str | None:
    """Convert an expression AST node to string."""
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _extract_params(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[list[str], list[str]]:
    """Return (param_names, param_types) from a function definition.

    Only includes non-self/cls parameters in the type list when annotations
    are present.  For unannotated parameters the type string is "".
    """
    args = node.args
    all_args = args.args + args.posonlyargs + args.kwonlyargs
    if args.vararg:
        all_args.append(args.vararg)
    if args.kwarg:
        all_args.append(args.kwarg)

    param_names: list[str] = []
    param_types: list[str] = []

    has_any_annotation = any(
        a.annotation is not None for a in all_args
    )

    for arg in args.args:
        param_names.append(arg.arg)
        if has_any_annotation:
            ann = _unparse_annotation(arg.annotation) or ""
            param_types.append(ann)

    return param_names, param_types


def _extract_decorators(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> list[str]:
    """Return decorator names/expressions."""
    result: list[str] = []
    for dec in node.decorator_list:
        try:
            result.append(ast.unparse(dec))
        except Exception:
            pass
    return result


def _extract_bases(node: ast.ClassDef) -> list[str]:
    """Return base class names."""
    result: list[str] = []
    for base in node.bases:
        try:
            result.append(ast.unparse(base))
        except Exception:
            pass
    return result


def _target_name(target: ast.expr) -> str | None:
    """Extract the variable name from an assignment target."""
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def _infer_value_type(value: ast.expr | None) -> str | None:
    """Infer value type from the RHS of an assignment (best-effort)."""
    if value is None:
        return None
    if isinstance(value, ast.Call):
        func = value.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
    return None
