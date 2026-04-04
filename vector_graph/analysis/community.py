"""Community detection via label propagation (networkx optional).

Falls back to a pure-Python connected-components algorithm when networkx
is unavailable.
"""

from __future__ import annotations

import os
from collections import defaultdict

from vector_graph._types import (
    CommunityInfo,
    EdgeType,
    NodeLabel,
)
from vector_graph.graph.protocols import GraphProtocol

# ---------------------------------------------------------------------------
# networkx optional import
# ---------------------------------------------------------------------------

try:
    import networkx as _nx  # type: ignore

    _HAS_NETWORKX = _nx is not None
except (ImportError, TypeError):
    _HAS_NETWORKX = False


# ---------------------------------------------------------------------------
# Pure-Python fallback: union-find connected components
# ---------------------------------------------------------------------------

class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self._parent.setdefault(x, x)
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, x: str, y: str) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self._parent[rx] = ry

    def groups(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = defaultdict(list)
        for node in list(self._parent):
            result[self.find(node)].append(node)
        return dict(result)


def _fallback_communities(
    node_ids: list[str],
    edges: list[tuple[str, str]],
) -> list[list[str]]:
    """Connected components via union-find (undirected)."""
    uf = _UnionFind()
    for nid in node_ids:
        uf.find(nid)  # register
    for src, tgt in edges:
        uf.union(src, tgt)
    return list(uf.groups().values())


def _networkx_communities(
    node_ids: list[str],
    edges: list[tuple[str, str]],
) -> list[list[str]]:
    """Label propagation via networkx."""
    import networkx as nx  # type: ignore

    g = nx.Graph()
    g.add_nodes_from(node_ids)
    g.add_edges_from(edges)

    try:
        from networkx.algorithms.community import label_propagation_communities
        raw = list(label_propagation_communities(g))
        return [list(c) for c in raw]
    except Exception:
        # Fall back to connected components if label propagation fails
        return [list(c) for c in nx.connected_components(g)]


# ---------------------------------------------------------------------------
# Label derivation
# ---------------------------------------------------------------------------

def _community_label(members: list[str], graph: GraphProtocol) -> str:
    """Derive a label from the common file path directory of members."""
    paths: list[str] = []
    for mid in members:
        node = graph.get_node(mid)
        if node:
            paths.append(node.properties.file_path)

    if not paths:
        return "community"

    # Find common directory prefix
    parts_list = [p.split("/") for p in paths]
    if not parts_list:
        return "community"

    common = parts_list[0]
    for parts in parts_list[1:]:
        new_common = []
        for a, b in zip(common, parts):
            if a == b:
                new_common.append(a)
            else:
                break
        common = new_common

    # Use last non-empty segment as label
    label_parts = [p for p in common if p]
    if label_parts:
        return label_parts[-1]

    # Fall back to file stem of first member
    node = graph.get_node(members[0])
    if node:
        return os.path.splitext(os.path.basename(node.properties.file_path))[0]

    return "community"


def _compute_cohesion(members: list[str], edge_index: dict[str, set[str]]) -> float:
    """Internal edge ratio using pre-built adjacency index."""
    n = len(members)
    if n <= 1:
        return 1.0
    member_set = set(members)
    internal = 0
    for m in members:
        for neighbor in edge_index.get(m, set()):
            if neighbor in member_set:
                internal += 1
    max_possible = n * (n - 1)
    return internal / max_possible if max_possible > 0 else 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_communities(
    graph: GraphProtocol,
    min_confidence: float = 0.5,
) -> list[CommunityInfo]:
    """Detect code communities/clusters.

    Uses label propagation (networkx) or union-find connected components
    (pure Python fallback).

    Parameters
    ----------
    graph:
        Duck-typed graph object.
    min_confidence:
        Edges below this confidence are excluded from community calculation.
    """
    # Collect nodes that are functions/methods/classes (skip file/folder nodes)
    valid_labels = {NodeLabel.FUNCTION, NodeLabel.METHOD, NodeLabel.CLASS}
    node_ids = [
        n.id for n in graph.iter_nodes()
        if n.label in valid_labels
    ]

    if not node_ids:
        return []

    # Collect high-confidence edges between valid nodes
    node_set = set(node_ids)
    edges: list[tuple[str, str]] = []
    for edge in graph.iter_edges():
        if edge.confidence < min_confidence:
            continue
        if edge.source_id in node_set and edge.target_id in node_set:
            edges.append((edge.source_id, edge.target_id))

    # Use fast fallback for large graphs — networkx label_propagation is slow on 4000+ nodes
    if len(node_ids) > 2000 or not _HAS_NETWORKX:
        raw_groups = _fallback_communities(node_ids, edges)
    else:
        raw_groups = _networkx_communities(node_ids, edges)

    # Build adjacency index for fast cohesion computation
    edge_index: dict[str, set[str]] = defaultdict(set)
    for src, tgt in edges:
        edge_index[src].add(tgt)
        edge_index[tgt].add(src)

    # Build CommunityInfo for each group with size > 1 (skip singletons)
    communities: list[CommunityInfo] = []
    for idx, members in enumerate(raw_groups):
        if len(members) <= 1:
            continue

        label = _community_label(members, graph)
        cohesion = _compute_cohesion(members, edge_index)

        comm = CommunityInfo(
            id=f"comm_{idx}",
            label=label,
            cohesion=cohesion,
            members=tuple(sorted(members)),
        )
        communities.append(comm)

    return communities
