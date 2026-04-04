"""ROS2 launch file parser — ast-based, no launch/rclpy dependency.

Parses Python ROS2 launch files (*.launch.py) and extracts:
- Node() instantiations with package, executable, name, parameters, remappings
- DeclareLaunchArgument() calls (argument names)
- LaunchConfiguration() references

All results are frozen dataclasses (immutable).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Data types (all frozen)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LaunchNodeInfo:
    """A Node() call extracted from a launch file."""

    package: str
    executable: str
    name: str | None = None
    parameters: tuple[str, ...] = ()
    remappings: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class LaunchFileInfo:
    """Complete parse result for a single launch file."""

    file_path: str
    nodes: tuple[LaunchNodeInfo, ...] = ()
    arguments: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_launch_file(file_path: str, source: str | None = None) -> LaunchFileInfo:
    """Parse a ROS2 Python launch file using ast.

    Args:
        file_path: Path to the launch file.
        source:    Source text; if None the file is read from disk.

    Returns:
        LaunchFileInfo.  On SyntaxError / IO error returns an empty result.
        If the file has no generate_launch_description() function, returns
        an empty result (nodes=(), arguments=()).
    """
    if source is None:
        try:
            source = Path(file_path).read_text(encoding="utf-8")
        except OSError:
            return LaunchFileInfo(file_path=file_path)

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return LaunchFileInfo(file_path=file_path)

    # Only parse files that contain generate_launch_description()
    if not _has_generate_launch_description(tree):
        return LaunchFileInfo(file_path=file_path)

    visitor = _LaunchVisitor()
    visitor.visit(tree)

    return LaunchFileInfo(
        file_path=file_path,
        nodes=tuple(visitor.nodes),
        arguments=tuple(visitor.arguments),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_generate_launch_description(tree: ast.Module) -> bool:
    """Return True if the module defines generate_launch_description()."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "generate_launch_description":
                return True
    return False


class _LaunchVisitor(ast.NodeVisitor):
    """Collect Node() and DeclareLaunchArgument() calls from a launch file."""

    def __init__(self) -> None:
        self.nodes: list[LaunchNodeInfo] = []
        self.arguments: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        func_name: str | None = None

        if isinstance(func, ast.Name):
            func_name = func.id
        elif isinstance(func, ast.Attribute):
            func_name = func.attr

        if func_name == "Node":
            info = _extract_launch_node(node)
            if info is not None:
                self.nodes.append(info)
        elif func_name == "DeclareLaunchArgument":
            arg_name = _get_pos_arg_str(node, 0)
            if arg_name:
                self.arguments.append(arg_name)

        self.generic_visit(node)


def _extract_launch_node(call: ast.Call) -> LaunchNodeInfo | None:
    """Extract LaunchNodeInfo from a Node(...) call node."""
    kwargs = {kw.arg: kw.value for kw in call.keywords if kw.arg is not None}

    package = _kwarg_str(kwargs, "package")
    executable = _kwarg_str(kwargs, "executable")
    if not package or not executable:
        return None

    name = _kwarg_str(kwargs, "name")
    parameters = _extract_parameters_list(kwargs.get("parameters"))
    remappings = _extract_remappings(kwargs.get("remappings"))

    return LaunchNodeInfo(
        package=package,
        executable=executable,
        name=name,
        parameters=tuple(parameters),
        remappings=tuple(remappings),
    )


def _kwarg_str(kwargs: dict[str, ast.expr], key: str) -> str | None:
    """Return the string value of a keyword argument dict entry."""
    val = kwargs.get(key)
    if val is None:
        return None
    if isinstance(val, ast.Constant) and isinstance(val.value, str):
        return val.value
    # Could be a Name or Attribute — return unparsed representation
    try:
        return ast.unparse(val)
    except Exception:
        return None


def _extract_parameters_list(node: ast.expr | None) -> list[str]:
    """Extract parameter keys from a parameters=[...] list."""
    if node is None:
        return []
    result: list[str] = []
    if not isinstance(node, ast.List):
        return result
    for elt in node.elts:
        if isinstance(elt, ast.Dict):
            for key in elt.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    result.append(key.value)
        elif isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            result.append(elt.value)
    return result


def _extract_remappings(node: ast.expr | None) -> list[tuple[str, str]]:
    """Extract remapping pairs from a remappings=[...] list."""
    if node is None:
        return []
    result: list[tuple[str, str]] = []
    if not isinstance(node, ast.List):
        return result
    for elt in node.elts:
        if isinstance(elt, ast.Tuple) and len(elt.elts) == 2:
            src = _const_str(elt.elts[0])
            dst = _const_str(elt.elts[1])
            if src is not None and dst is not None:
                result.append((src, dst))
    return result


def _const_str(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _get_pos_arg_str(call: ast.Call, index: int) -> str | None:
    """Return the string literal at positional arg index, or None."""
    if index >= len(call.args):
        return None
    arg = call.args[index]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None
