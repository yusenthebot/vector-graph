"""ROS2 node extractor — ast-based, no rclpy dependency.

Extracts ROS2 node definitions from Python source files by inspecting the AST
for classes that inherit from Node (rclpy.node.Node) and their create_publisher,
create_subscription, create_service, declare_parameter, and ActionServer calls.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Data types (all frozen)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PublisherInfo:
    """A publisher extracted from create_publisher()."""

    msg_type: str
    topic: str
    qos: str | None = None


@dataclass(frozen=True)
class SubscriberInfo:
    """A subscriber extracted from create_subscription()."""

    msg_type: str
    topic: str
    callback: str | None = None
    qos: str | None = None


@dataclass(frozen=True)
class ServiceInfo:
    """A service server extracted from create_service()."""

    srv_type: str
    service_name: str
    callback: str | None = None


@dataclass(frozen=True)
class ActionInfo:
    """An action server/client extracted from ActionServer/ActionClient instantiation."""

    action_type: str
    action_name: str
    is_server: bool = True


@dataclass(frozen=True)
class ParameterInfo:
    """A parameter extracted from declare_parameter()."""

    param_name: str
    default_value: str | None = None


@dataclass(frozen=True)
class ROS2NodeInfo:
    """Complete information about a ROS2 node class found in a Python file."""

    class_name: str
    node_name: str | None  # from super().__init__('name')
    file_path: str
    publishers: tuple[PublisherInfo, ...]
    subscribers: tuple[SubscriberInfo, ...]
    services: tuple[ServiceInfo, ...]
    actions: tuple[ActionInfo, ...]
    parameters: tuple[ParameterInfo, ...]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_ros2_nodes(file_path: str, source: str | None = None) -> list[ROS2NodeInfo]:
    """Parse a Python file and extract ROS2 node definitions.

    Args:
        file_path: Path to the Python source file.
        source:    Source text; if None the file is read from disk.

    Returns:
        List of ROS2NodeInfo (one per class that inherits from Node).
        Returns [] on SyntaxError or IO error.
    """
    if source is None:
        try:
            source = Path(file_path).read_text(encoding="utf-8")
        except OSError:
            return []

    if not source.strip():
        return []

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return []

    extractor = _NodeExtractor(file_path)
    extractor.visit(tree)
    return extractor.results


# ---------------------------------------------------------------------------
# AST visitor
# ---------------------------------------------------------------------------

# Names that identify a ROS2 Node base class
_NODE_BASE_NAMES = {"Node", "rclpy.node.Node", "LifecycleNode", "rclpy_lifecycle.node.LifecycleNode"}


def _is_ros2_node_base(base: ast.expr) -> bool:
    """Return True if the base class expression refers to a ROS2 Node."""
    try:
        unparsed = ast.unparse(base)
    except Exception:
        return False
    return unparsed in _NODE_BASE_NAMES


class _NodeExtractor(ast.NodeVisitor):
    """Walk the module-level AST and find ROS2 node classes."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.results: list[ROS2NodeInfo] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if any(_is_ros2_node_base(b) for b in node.bases):
            info = _extract_node_info(node, self.file_path)
            self.results.append(info)
        # Do NOT recurse into class body via generic_visit — we handle it in
        # _extract_node_info so we process only the correct class scope.


# ---------------------------------------------------------------------------
# Per-class extraction
# ---------------------------------------------------------------------------

def _extract_node_info(class_node: ast.ClassDef, file_path: str) -> ROS2NodeInfo:
    """Extract all ROS2 metadata from a class definition."""
    visitor = _ClassBodyVisitor()
    visitor.visit(class_node)

    return ROS2NodeInfo(
        class_name=class_node.name,
        node_name=visitor.node_name,
        file_path=file_path,
        publishers=tuple(visitor.publishers),
        subscribers=tuple(visitor.subscribers),
        services=tuple(visitor.services),
        actions=tuple(visitor.actions),
        parameters=tuple(visitor.parameters),
    )


class _ClassBodyVisitor(ast.NodeVisitor):
    """Visit a class body to collect ROS2 calls."""

    def __init__(self) -> None:
        self.node_name: str | None = None
        self.publishers: list[PublisherInfo] = []
        self.subscribers: list[SubscriberInfo] = []
        self.services: list[ServiceInfo] = []
        self.actions: list[ActionInfo] = []
        self.parameters: list[ParameterInfo] = []

    # ------------------------------------------------------------------
    # Call dispatch
    # ------------------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute):
            name = func.attr
            receiver_src = _unparse(func.value)
            if name == "create_publisher" and _is_self(receiver_src):
                self._handle_publisher(node)
            elif name == "create_subscription" and _is_self(receiver_src):
                self._handle_subscription(node)
            elif name == "create_service" and _is_self(receiver_src):
                self._handle_service(node)
            elif name == "declare_parameter" and _is_self(receiver_src):
                self._handle_parameter(node)
            elif name == "__init__":
                # super().__init__('node_name')
                self._handle_super_init(node)
        elif isinstance(func, ast.Name):
            # ActionServer(...) — top-level name
            if func.id in ("ActionServer", "ActionClient"):
                self._handle_action(node, func.id)
        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_publisher(self, node: ast.Call) -> None:
        """create_publisher(MsgType, '/topic', qos_profile=...)"""
        msg_type = _get_pos_arg_name(node, 0)
        topic = _get_pos_arg_str(node, 1)
        qos = _get_kwarg_str(node, "qos_profile")
        if msg_type and topic:
            self.publishers.append(PublisherInfo(msg_type=msg_type, topic=topic, qos=qos))

    def _handle_subscription(self, node: ast.Call) -> None:
        """create_subscription(MsgType, '/topic', callback, qos)"""
        msg_type = _get_pos_arg_name(node, 0)
        topic = _get_pos_arg_str(node, 1)
        callback = _get_pos_arg_name(node, 2)
        if msg_type and topic:
            self.subscribers.append(
                SubscriberInfo(msg_type=msg_type, topic=topic, callback=callback)
            )

    def _handle_service(self, node: ast.Call) -> None:
        """create_service(SrvType, '/service', callback)"""
        srv_type = _get_pos_arg_name(node, 0)
        service_name = _get_pos_arg_str(node, 1)
        callback = _get_pos_arg_name(node, 2)
        if srv_type and service_name:
            self.services.append(
                ServiceInfo(srv_type=srv_type, service_name=service_name, callback=callback)
            )

    def _handle_parameter(self, node: ast.Call) -> None:
        """declare_parameter('name', default_value)"""
        param_name = _get_pos_arg_str(node, 0)
        default_val = _get_pos_arg_repr(node, 1)
        if param_name:
            self.parameters.append(
                ParameterInfo(param_name=param_name, default_value=default_val)
            )

    def _handle_super_init(self, node: ast.Call) -> None:
        """super().__init__('node_name') — capture the node name string."""
        name = _get_pos_arg_str(node, 0)
        if name and self.node_name is None:
            self.node_name = name

    def _handle_action(self, node: ast.Call, constructor_name: str) -> None:
        """ActionServer(self, ActionType, 'action_name', callback)"""
        # ActionServer(self, Navigate, 'navigate', self._execute_cb)
        # arg 0 = self (skip), arg 1 = action type, arg 2 = action name
        action_type = _get_pos_arg_name(node, 1)
        action_name = _get_pos_arg_str(node, 2)
        if action_type and action_name:
            self.actions.append(
                ActionInfo(
                    action_type=action_type,
                    action_name=action_name,
                    is_server=(constructor_name == "ActionServer"),
                )
            )


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _unparse(node: ast.expr) -> str | None:
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _is_self(receiver: str | None) -> bool:
    return receiver == "self"


def _get_pos_arg_name(call: ast.Call, index: int) -> str | None:
    """Return the Name identifier at positional arg index, or None."""
    args = call.args
    if index >= len(args):
        return None
    arg = args[index]
    if isinstance(arg, ast.Name):
        return arg.id
    if isinstance(arg, ast.Attribute):
        # e.g. self._cmd_callback -> attr name only
        return arg.attr
    try:
        return ast.unparse(arg)
    except Exception:
        return None


def _get_pos_arg_str(call: ast.Call, index: int) -> str | None:
    """Return the string literal at positional arg index, or None."""
    args = call.args
    if index >= len(args):
        return None
    arg = args[index]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None


def _get_pos_arg_repr(call: ast.Call, index: int) -> str | None:
    """Return ast.unparse() of positional arg index, or None."""
    args = call.args
    if index >= len(args):
        return None
    try:
        return ast.unparse(args[index])
    except Exception:
        return None


def _get_kwarg_str(call: ast.Call, keyword: str) -> str | None:
    """Return string value of a keyword argument, or None."""
    for kw in call.keywords:
        if kw.arg == keyword:
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
            try:
                return ast.unparse(kw.value)
            except Exception:
                return None
    return None
