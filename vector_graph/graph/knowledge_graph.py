"""Dict-based knowledge graph with O(1) operations.

Ported from GitNexus graph.ts. Two primary dicts:
- _nodes: dict[str, GraphNode]
- _edges: dict[str, Edge]

Secondary indexes for fast queries:
- _file_index: dict[str, set[str]]       # file_path -> node_ids
- _edges_from: dict[str, set[str]]       # source_id -> edge_ids
- _edges_to: dict[str, set[str]]         # target_id -> edge_ids
- _label_index: dict[NodeLabel, set[str]] # label -> node_ids
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterator

from vector_graph._types import Edge, GraphNode, NodeLabel


class KnowledgeGraph:
    """In-memory knowledge graph with secondary indexes for fast queries."""

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, Edge] = {}
        # Secondary indexes
        self._file_index: dict[str, set[str]] = defaultdict(set)
        self._edges_from: dict[str, set[str]] = defaultdict(set)
        self._edges_to: dict[str, set[str]] = defaultdict(set)
        self._label_index: dict[NodeLabel, set[str]] = defaultdict(set)

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    def add_node(self, node: GraphNode) -> None:
        """Add or overwrite a node. Updates all secondary indexes."""
        existing = self._nodes.get(node.id)
        if existing is not None:
            self._remove_node_from_indexes(existing)
        self._nodes[node.id] = node
        self._file_index[node.properties.file_path].add(node.id)
        self._label_index[node.label].add(node.id)

    def get_node(self, node_id: str) -> GraphNode | None:
        return self._nodes.get(node_id)

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    def remove_node(self, node_id: str) -> None:
        """Remove a node and cascade-delete all incident edges."""
        node = self._nodes.get(node_id)
        if node is None:
            return
        # Collect all incident edge ids before mutation
        incident = (
            set(self._edges_from.get(node_id, set())) |
            set(self._edges_to.get(node_id, set()))
        )
        for edge_id in incident:
            edge = self._edges.get(edge_id)
            if edge is not None:
                self._remove_edge_from_indexes(edge)
                del self._edges[edge_id]
        # Clean up edge index entries for this node
        self._edges_from.pop(node_id, None)
        self._edges_to.pop(node_id, None)
        # Remove node from secondary indexes
        self._remove_node_from_indexes(node)
        del self._nodes[node_id]

    def remove_nodes_by_file(self, file_path: str) -> None:
        """Remove all nodes belonging to file_path and cascade edges."""
        node_ids = list(self._file_index.get(file_path, set()))
        for node_id in node_ids:
            self.remove_node(node_id)

    # ------------------------------------------------------------------
    # Edge operations
    # ------------------------------------------------------------------

    def add_edge(self, edge: Edge) -> None:
        """Add an edge and update adjacency indexes."""
        self._edges[edge.id] = edge
        self._edges_from[edge.source_id].add(edge.id)
        self._edges_to[edge.target_id].add(edge.id)

    def get_edge(self, edge_id: str) -> Edge | None:
        return self._edges.get(edge_id)

    def remove_edge(self, edge_id: str) -> None:
        """Remove an edge by ID and update adjacency indexes. Idempotent."""
        edge = self._edges.get(edge_id)
        if edge is None:
            return
        self._remove_edge_from_indexes(edge)
        del self._edges[edge_id]

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    # ------------------------------------------------------------------
    # Iteration
    # ------------------------------------------------------------------

    def iter_nodes(self) -> Iterator[GraphNode]:
        return iter(self._nodes.values())

    def iter_edges(self) -> Iterator[Edge]:
        return iter(self._edges.values())

    # ------------------------------------------------------------------
    # Adjacency queries
    # ------------------------------------------------------------------

    def get_edges_from(self, source_id: str) -> Iterator[Edge]:
        """Yield all edges whose source is source_id."""
        for edge_id in self._edges_from.get(source_id, set()):
            edge = self._edges.get(edge_id)
            if edge is not None:
                yield edge

    def get_edges_to(self, target_id: str) -> Iterator[Edge]:
        """Yield all edges whose target is target_id."""
        for edge_id in self._edges_to.get(target_id, set()):
            edge = self._edges.get(edge_id)
            if edge is not None:
                yield edge

    # ------------------------------------------------------------------
    # Label / file queries
    # ------------------------------------------------------------------

    def get_nodes_by_label(self, label: NodeLabel) -> Iterator[GraphNode]:
        """Yield all nodes with the given label."""
        for node_id in self._label_index.get(label, set()):
            node = self._nodes.get(node_id)
            if node is not None:
                yield node

    def get_nodes_by_file(self, file_path: str) -> Iterator[GraphNode]:
        """Yield all nodes belonging to file_path."""
        for node_id in self._file_index.get(file_path, set()):
            node = self._nodes.get(node_id)
            if node is not None:
                yield node

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _remove_node_from_indexes(self, node: GraphNode) -> None:
        fp = node.properties.file_path
        self._file_index[fp].discard(node.id)
        if not self._file_index[fp]:
            del self._file_index[fp]
        self._label_index[node.label].discard(node.id)
        if not self._label_index[node.label]:
            del self._label_index[node.label]

    def _remove_edge_from_indexes(self, edge: Edge) -> None:
        self._edges_from[edge.source_id].discard(edge.id)
        if not self._edges_from[edge.source_id]:
            del self._edges_from[edge.source_id]
        self._edges_to[edge.target_id].discard(edge.id)
        if not self._edges_to[edge.target_id]:
            del self._edges_to[edge.target_id]
