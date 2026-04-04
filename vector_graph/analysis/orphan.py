"""Find unreachable functions/classes with no incoming edges."""

from __future__ import annotations

import os

from vector_graph._types import (
    EdgeType,
    GraphNode,
    NodeLabel,
)
from vector_graph.graph.protocols import GraphProtocol

# ---------------------------------------------------------------------------
# Entry point names that are never considered orphans
# ---------------------------------------------------------------------------

_ENTRY_POINT_NAMES: frozenset[str] = frozenset({
    "main",
    "__init__",
    "__new__",
    "__call__",
    "__enter__",
    "__exit__",
    "setup",
    "teardown",
})

_ENTRY_POINT_PREFIXES: tuple[str, ...] = (
    "on_",
    "handle_",
    "test_",
)

# Edge types that count as "incoming reference" (node is reachable)
_INCOMING_EDGE_TYPES: frozenset[EdgeType] = frozenset({
    EdgeType.CALLS,
    EdgeType.IMPORTS,
    EdgeType.EXTENDS,
    EdgeType.IMPLEMENTS,
    EdgeType.HAS_METHOD,
    EdgeType.HAS_PROPERTY,
    EdgeType.DECORATES,
})


def _is_test_file(file_path: str) -> bool:
    """Return True if the file is a test file."""
    basename = os.path.basename(file_path)
    name_no_ext = os.path.splitext(basename)[0]
    return basename.startswith("test_") or name_no_ext.endswith("_test")


def _is_entry_point(node: GraphNode) -> bool:
    """Return True if the node is a conventional entry point."""
    name = node.properties.name
    if name in _ENTRY_POINT_NAMES:
        return True
    for prefix in _ENTRY_POINT_PREFIXES:
        if name.startswith(prefix):
            return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_orphans(graph: GraphProtocol) -> list[GraphNode]:
    """Find unreachable functions/classes with no incoming edges.

    A node is an orphan if:
    - It is a FUNCTION, METHOD, or CLASS
    - It is not in a test file
    - It is not a conventional entry point (main, __init__, on_*, handle_*)
    - It has no incoming edges of any meaningful type

    Parameters
    ----------
    graph:
        Duck-typed graph object.
    """
    valid_labels = {NodeLabel.FUNCTION, NodeLabel.METHOD, NodeLabel.CLASS}

    # Build set of nodes that have at least one qualifying incoming edge
    has_incoming: set[str] = set()
    for edge in graph.iter_edges():
        if edge.edge_type in _INCOMING_EDGE_TYPES:
            has_incoming.add(edge.target_id)

    orphans: list[GraphNode] = []
    for node in graph.iter_nodes():
        if node.label not in valid_labels:
            continue
        if _is_test_file(node.properties.file_path):
            continue
        if _is_entry_point(node):
            continue
        if node.id in has_incoming:
            continue
        orphans.append(node)

    return orphans
