"""Blast radius (impact) analysis via BFS traversal of the knowledge graph."""

from __future__ import annotations

from collections import deque

from vector_graph._types import (
    EdgeType,
    ImpactEntry,
    ImpactResult,
)


# ---------------------------------------------------------------------------
# Risk thresholds (ported from GitNexus local-backend.ts)
# ---------------------------------------------------------------------------

_RISK_THRESHOLDS: list[tuple[int, int, str]] = [
    # (min_total, min_direct, label)
    (20, 8, "CRITICAL"),
    (6, 4, "HIGH"),
    (3, 1, "MEDIUM"),
    (0, 0, "LOW"),
]


def _compute_risk(entries: list[ImpactEntry]) -> str:
    total = len(entries)
    direct = sum(1 for e in entries if e.depth == 1)
    for min_total, min_direct, label in _RISK_THRESHOLDS:
        if total >= min_total and direct >= min_direct:
            return label
    return "LOW"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_impact(
    graph: object,
    target_id: str,
    direction: str = "upstream",
    max_depth: int = 3,
    min_confidence: float = 0.0,
    relation_types: set[EdgeType] | None = None,
) -> ImpactResult:
    """BFS blast radius analysis.

    Parameters
    ----------
    graph:
        Duck-typed graph object — must implement get_node, get_edges_from,
        get_edges_to.
    target_id:
        Node ID to analyse.
    direction:
        'upstream' — who calls/depends-on target.
        'downstream' — what target calls/depends-on.
    max_depth:
        Maximum BFS depth to explore.
    min_confidence:
        Edges below this confidence are skipped.
    relation_types:
        If given, only traverse edges of these types.
    """
    target_node = graph.get_node(target_id)  # type: ignore[attr-defined]

    # Provide sensible defaults even for unknown targets
    target_name = target_node.properties.name if target_node else target_id
    target_file = target_node.properties.file_path if target_node else ""

    if target_node is None:
        return ImpactResult(
            target_name=target_name,
            target_file=target_file,
            direction=direction,
            risk="LOW",
            entries=(),
        )

    entries: list[ImpactEntry] = []
    visited: set[str] = {target_id}

    # BFS queue: (node_id, depth, edge_type, confidence)
    queue: deque[tuple[str, int, str, float]] = deque()

    # For Class nodes: also seed from all methods (HAS_METHOD edges)
    seed_ids = [target_id]
    if target_node is not None and target_node.label.value == "Class":
        for edge in graph.get_edges_from(target_id):  # type: ignore[attr-defined]
            if edge.edge_type == EdgeType.HAS_METHOD:
                seed_ids.append(edge.target_id)
                visited.add(edge.target_id)

    # Seed from direct neighbors of all seed IDs
    for sid in seed_ids:
        if direction == "upstream":
            seed_edges = graph.get_edges_to(sid)  # type: ignore[attr-defined]
        else:
            seed_edges = graph.get_edges_from(sid)  # type: ignore[attr-defined]
        _enqueue_edges(queue, seed_edges, depth=1, direction=direction,
                       min_confidence=min_confidence, relation_types=relation_types,
                       visited=visited)

    while queue:
        node_id, depth, edge_type, confidence = queue.popleft()

        node = graph.get_node(node_id)  # type: ignore[attr-defined]
        if node is None:
            continue

        entries.append(ImpactEntry(
            node_id=node_id,
            name=node.properties.name,
            file_path=node.properties.file_path,
            depth=depth,
            edge_type=edge_type,
            confidence=confidence,
        ))

        if depth < max_depth:
            if direction == "upstream":
                next_edges = graph.get_edges_to(node_id)  # type: ignore[attr-defined]
            else:
                next_edges = graph.get_edges_from(node_id)  # type: ignore[attr-defined]
            _enqueue_edges(queue, next_edges, depth=depth + 1, direction=direction,
                           min_confidence=min_confidence, relation_types=relation_types,
                           visited=visited)

    risk = _compute_risk(entries)
    return ImpactResult(
        target_name=target_name,
        target_file=target_file,
        direction=direction,
        risk=risk,
        entries=tuple(entries),
    )


def _enqueue_edges(
    queue: deque[tuple[str, int, str, float]],
    edges: list,
    depth: int,
    direction: str,
    min_confidence: float,
    relation_types: set[EdgeType] | None,
    visited: set[str],
) -> None:
    """Filter and enqueue edges for BFS traversal."""
    for edge in edges:
        if edge.confidence < min_confidence:
            continue
        if relation_types is not None and edge.edge_type not in relation_types:
            continue

        neighbor_id = edge.source_id if direction == "upstream" else edge.target_id
        if neighbor_id in visited:
            continue

        visited.add(neighbor_id)
        queue.append((neighbor_id, depth, edge.edge_type.value, edge.confidence))
