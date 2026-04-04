"""Execution flow detection: entry point scoring + BFS trace.

Ported from GitNexus process-processor.ts.
"""

from __future__ import annotations

import hashlib
from collections import deque

from vector_graph._types import (
    EdgeType,
    NodeLabel,
    ProcessTrace,
)
from vector_graph.graph.protocols import GraphProtocol


# ---------------------------------------------------------------------------
# Entry point name patterns (higher score = more likely entry point)
# ---------------------------------------------------------------------------

_ENTRY_PATTERNS: list[tuple[str, float]] = [
    ("main", 3.0),
    ("run", 2.0),
    ("start", 2.0),
    ("execute", 1.5),
    ("handle_", 2.5),   # prefix
    ("on_", 2.0),       # prefix
    ("process_", 1.5),  # prefix
    ("dispatch_", 1.5), # prefix
]


def _name_score(name: str) -> float:
    score = 0.0
    lower = name.lower()
    for pattern, weight in _ENTRY_PATTERNS:
        if pattern.endswith("_"):
            if lower.startswith(pattern):
                score += weight
        else:
            if lower == pattern:
                score += weight
    return score


def _entry_point_score(node_id: str, graph: GraphProtocol) -> float:
    """Score how likely a node is to be an entry point.

    Score factors:
    - Number of outgoing CALLS edges (callees) — higher is better
    - Number of incoming CALLS edges (callers) — lower is better
    - Name pattern bonus
    """
    node = graph.get_node(node_id)
    if node is None:
        return 0.0

    # Only functions/methods can be entry points
    if node.label not in (NodeLabel.FUNCTION, NodeLabel.METHOD):
        return 0.0

    out_edges = [e for e in graph.get_edges_from(node_id)
                 if e.edge_type == EdgeType.CALLS]
    in_edges = [e for e in graph.get_edges_to(node_id)
                if e.edge_type == EdgeType.CALLS]

    callee_count = len(out_edges)
    caller_count = len(in_edges)

    if callee_count == 0:
        return 0.0  # leaf node, not an entry point

    # Penalise heavily if called by many others
    score = float(callee_count) - float(caller_count) * 1.5
    score += _name_score(node.properties.name)
    return score


def _trace_id(entry_id: str, trace_nodes: list[str]) -> str:
    """Deterministic ID for a trace path."""
    raw = f"{entry_id}:{'->'.join(trace_nodes)}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_execution_flows(
    graph: GraphProtocol,
    max_depth: int = 10,
    max_branching: int = 4,
    min_steps: int = 3,
    max_processes: int = 75,
) -> list[ProcessTrace]:
    """Entry point scoring + BFS trace.

    Parameters
    ----------
    graph:
        Duck-typed graph object.
    max_depth:
        Maximum trace depth.
    max_branching:
        Maximum children to follow per node per level.
    min_steps:
        Minimum number of steps (nodes) for a trace to be included.
    max_processes:
        Cap on number of returned traces.
    """
    # Collect all candidate entry points with their score
    all_nodes = list(graph.iter_nodes())
    candidates: list[tuple[float, str]] = []

    for node in all_nodes:
        score = _entry_point_score(node.id, graph)
        if score > 0.0:
            candidates.append((score, node.id))

    # Sort descending by score
    candidates.sort(key=lambda x: x[0], reverse=True)

    traces: list[ProcessTrace] = []
    seen_ids: set[str] = set()

    for _score, entry_id in candidates:
        if len(traces) >= max_processes:
            break

        new_traces = _bfs_trace(
            graph=graph,
            entry_id=entry_id,
            max_depth=max_depth,
            max_branching=max_branching,
        )

        for trace_nodes in new_traces:
            if len(trace_nodes) < min_steps:
                continue

            tid = _trace_id(entry_id, trace_nodes)
            if tid in seen_ids:
                continue
            seen_ids.add(tid)

            entry_node = graph.get_node(entry_id)
            entry_name = entry_node.properties.name if entry_node else entry_id
            terminal_id = trace_nodes[-1]

            process = ProcessTrace(
                id=tid,
                label=f"{entry_name} flow",
                entry_point_id=entry_id,
                terminal_id=terminal_id,
                step_count=len(trace_nodes),
                trace=tuple(trace_nodes),
            )
            traces.append(process)

            if len(traces) >= max_processes:
                break

    return traces


def _bfs_trace(
    graph: GraphProtocol,
    entry_id: str,
    max_depth: int,
    max_branching: int,
) -> list[list[str]]:
    """BFS from entry_id following CALLS edges.

    Returns a list of node-ID sequences, each representing one trace path.
    """
    # Each queue item: (current_node_id, path_so_far, depth)
    queue: deque[tuple[str, list[str], int]] = deque()
    queue.append((entry_id, [entry_id], 0))

    completed_traces: list[list[str]] = []

    while queue:
        node_id, path, depth = queue.popleft()

        if depth >= max_depth:
            completed_traces.append(path)
            continue

        out_edges = [
            e for e in graph.get_edges_from(node_id)
            if e.edge_type == EdgeType.CALLS
        ]

        # Sort by confidence descending, take top max_branching
        out_edges = sorted(out_edges, key=lambda e: e.confidence, reverse=True)
        out_edges = out_edges[:max_branching]

        # Only follow edges to nodes NOT already in path (avoid cycles in path)
        children = [
            e.target_id for e in out_edges
            if e.target_id not in path
        ]

        if not children:
            completed_traces.append(path)
        else:
            for child_id in children:
                queue.append((child_id, path + [child_id], depth + 1))

    return completed_traces
