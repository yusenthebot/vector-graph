"""Structural Protocol definitions for graph objects.

These Protocols allow analysis modules to express precise type constraints
without coupling to the concrete KnowledgeGraph implementation.
"""

from __future__ import annotations

from typing import Iterator, Protocol, runtime_checkable

from vector_graph._types import Edge, GraphNode, NodeLabel


@runtime_checkable
class GraphProtocol(Protocol):
    """Structural protocol for any graph object used in analysis modules.

    KnowledgeGraph satisfies this protocol without explicit inheritance —
    structural (duck-type) conformance only.
    """

    def get_node(self, node_id: str) -> GraphNode | None: ...

    def get_edges_from(self, source_id: str) -> Iterator[Edge]: ...

    def get_edges_to(self, target_id: str) -> Iterator[Edge]: ...

    def iter_nodes(self) -> Iterator[GraphNode]: ...

    def iter_edges(self) -> Iterator[Edge]: ...

    def get_nodes_by_label(self, label: NodeLabel) -> Iterator[GraphNode]: ...

    def get_nodes_by_file(self, file_path: str) -> Iterator[GraphNode]: ...

    @property
    def node_count(self) -> int: ...

    @property
    def edge_count(self) -> int: ...
