"""Suggest test files for a given function/class based on the call graph.

Strategy: BFS upstream through CALLS edges from the target node, collecting
any nodes whose file path looks like a test file (contains 'test_' or ends
with '_test.py').  Returns test file paths + test function names sorted by
relevance (direct callers first, then transitive).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from vector_graph._types import EdgeType, NodeLabel
from vector_graph.graph.protocols import GraphProtocol


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_test_file(file_path: str) -> bool:
    """Return True if file_path looks like a test file."""
    basename = file_path.split("/")[-1]
    return basename.startswith("test_") or basename.endswith("_test.py")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TestSuggestion:
    """A single test suggestion entry."""
    test_file: str
    test_name: str
    depth: int  # BFS depth from target — lower is more directly related


def suggest_tests(graph: GraphProtocol, name: str) -> list[TestSuggestion]:
    """Find test functions that call or reference the named symbol.

    Parameters
    ----------
    graph:
        Knowledge graph satisfying GraphProtocol.
    name:
        Function, method, or class name to find tests for.

    Returns
    -------
    List of TestSuggestion sorted by depth (ascending), then test_name.
    """
    # 1. Find the target node
    target_node = None
    for node in graph.iter_nodes():
        if (
            node.properties.name == name
            and node.label in (NodeLabel.FUNCTION, NodeLabel.METHOD, NodeLabel.CLASS)
        ):
            target_node = node
            break

    if target_node is None:
        return []

    suggestions: list[TestSuggestion] = []
    visited: set[str] = {target_node.id}
    queue: deque[tuple[str, int]] = deque([(target_node.id, 0)])

    while queue:
        current_id, depth = queue.popleft()

        # Walk upstream through CALLS edges (who calls current_id)
        for edge in graph.get_edges_to(current_id):
            if edge.edge_type != EdgeType.CALLS:
                continue
            src_id = edge.source_id
            if src_id in visited:
                continue
            visited.add(src_id)

            src_node = graph.get_node(src_id)
            if src_node is None:
                continue

            if _is_test_file(src_node.properties.file_path):
                suggestions.append(TestSuggestion(
                    test_file=src_node.properties.file_path,
                    test_name=src_node.properties.name,
                    depth=depth + 1,
                ))
            else:
                # Keep traversing upstream — maybe a test calls this helper
                queue.append((src_id, depth + 1))

    # Deduplicate while preserving lowest depth per (file, name) pair
    seen: dict[tuple[str, str], int] = {}
    for s in suggestions:
        key = (s.test_file, s.test_name)
        if key not in seen or s.depth < seen[key]:
            seen[key] = s.depth

    result = [
        TestSuggestion(test_file=file, test_name=test_name, depth=d)
        for (file, test_name), d in seen.items()
    ]
    return sorted(result, key=lambda s: (s.depth, s.test_name))
