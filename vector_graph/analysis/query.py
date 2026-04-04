"""Graph query engine — structured queries against the knowledge graph.

Supports 8 query types via a single dispatch function:
  callers_of, callees_of, subclasses_of, implementations_of,
  path_between, by_file, by_pattern, by_decorator
"""

from __future__ import annotations

import fnmatch
from collections import deque

from vector_graph._types import Edge, EdgeType, GraphNode, NodeLabel, QueryResult
from vector_graph.graph.protocols import GraphProtocol


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def execute_query(
    graph: GraphProtocol,
    query_type: str,
    **kwargs: str,
) -> QueryResult:
    """Execute a structured query against the graph.

    Parameters
    ----------
    graph:
        Any object satisfying GraphProtocol (e.g. KnowledgeGraph).
    query_type:
        One of: callers_of, callees_of, subclasses_of, implementations_of,
        path_between, by_file, by_pattern, by_decorator.
    **kwargs:
        Query-specific parameters:
          - callers_of / callees_of / subclasses_of / implementations_of: name=
          - path_between: source=, target=
          - by_file: file_path=
          - by_pattern: pattern=
          - by_decorator: decorator=

    Returns
    -------
    QueryResult with .nodes, .edges, .count, .query_type, .params populated.
    Unknown query_type returns an empty QueryResult (no exception raised).
    """
    _dispatch = {
        "callers_of": _callers_of,
        "callees_of": _callees_of,
        "subclasses_of": _subclasses_of,
        "implementations_of": _implementations_of,
        "path_between": _path_between,
        "by_file": _by_file,
        "by_pattern": _by_pattern,
        "by_decorator": _by_decorator,
    }
    handler = _dispatch.get(query_type)
    if handler is None:
        return QueryResult(query_type=query_type, params=dict(kwargs))
    return handler(graph, **kwargs)


# ---------------------------------------------------------------------------
# Query handlers
# ---------------------------------------------------------------------------


def _callers_of(graph: GraphProtocol, name: str = "", **_: str) -> QueryResult:
    """Return nodes that have a CALLS edge pointing TO the named node."""
    target = _find_node_by_name(graph, name)
    if target is None:
        return QueryResult(query_type="callers_of", params={"name": name})

    caller_nodes: list[GraphNode] = []
    for edge in graph.get_edges_to(target.id):
        if edge.edge_type == EdgeType.CALLS:
            node = graph.get_node(edge.source_id)
            if node is not None:
                caller_nodes.append(node)

    return QueryResult(
        query_type="callers_of",
        params={"name": name},
        nodes=tuple(caller_nodes),
    )


def _callees_of(graph: GraphProtocol, name: str = "", **_: str) -> QueryResult:
    """Return nodes that the named node calls (CALLS edges outward)."""
    source = _find_node_by_name(graph, name)
    if source is None:
        return QueryResult(query_type="callees_of", params={"name": name})

    callee_nodes: list[GraphNode] = []
    for edge in graph.get_edges_from(source.id):
        if edge.edge_type == EdgeType.CALLS:
            node = graph.get_node(edge.target_id)
            if node is not None:
                callee_nodes.append(node)

    return QueryResult(
        query_type="callees_of",
        params={"name": name},
        nodes=tuple(callee_nodes),
    )


def _subclasses_of(graph: GraphProtocol, name: str = "", **_: str) -> QueryResult:
    """Return class nodes that extend (EXTENDS edge to) the named class."""
    target = _find_class_by_name(graph, name)
    if target is None:
        return QueryResult(query_type="subclasses_of", params={"name": name})

    subclass_nodes: list[GraphNode] = []
    for edge in graph.get_edges_to(target.id):
        if edge.edge_type == EdgeType.EXTENDS:
            node = graph.get_node(edge.source_id)
            if node is not None:
                subclass_nodes.append(node)

    return QueryResult(
        query_type="subclasses_of",
        params={"name": name},
        nodes=tuple(subclass_nodes),
    )


def _implementations_of(graph: GraphProtocol, name: str = "", **_: str) -> QueryResult:
    """Return all Method nodes whose name matches the given name.

    This captures overrides/implementations since any method sharing the name
    in a subclass is considered an implementation/override.
    """
    impl_nodes: list[GraphNode] = []
    for node in graph.get_nodes_by_label(NodeLabel.METHOD):
        if node.properties.name == name:
            impl_nodes.append(node)

    return QueryResult(
        query_type="implementations_of",
        params={"name": name},
        nodes=tuple(impl_nodes),
    )


def _path_between(
    graph: GraphProtocol,
    source: str = "",
    target: str = "",
    **_: str,
) -> QueryResult:
    """Find shortest path between two named nodes using undirected BFS.

    Both forward (get_edges_from) and backward (get_edges_to) edges are
    followed so that structural edges like EXTENDS are traversable in reverse.

    Returns QueryResult with path nodes (in order) and connecting edges.
    Returns empty QueryResult when either node is not found or no path exists.
    """
    params = {"source": source, "target": target}

    src_node = _find_node_by_name(graph, source)
    tgt_node = _find_node_by_name(graph, target)
    if src_node is None or tgt_node is None:
        return QueryResult(query_type="path_between", params=params)

    # Trivial case: same node
    if src_node.id == tgt_node.id:
        return QueryResult(
            query_type="path_between",
            params=params,
            nodes=(src_node,),
        )

    # BFS — state: (current_node_id, node_id_path, edge_path)
    queue: deque[tuple[str, list[str], list[Edge]]] = deque(
        [(src_node.id, [src_node.id], [])]
    )
    visited: set[str] = {src_node.id}

    while queue:
        current_id, node_path, edge_path = queue.popleft()

        if current_id == tgt_node.id:
            path_nodes = tuple(
                n for nid in node_path if (n := graph.get_node(nid)) is not None
            )
            return QueryResult(
                query_type="path_between",
                params=params,
                nodes=path_nodes,
                edges=tuple(edge_path),
            )

        # Follow forward edges
        for edge in graph.get_edges_from(current_id):
            if edge.target_id not in visited:
                visited.add(edge.target_id)
                queue.append((
                    edge.target_id,
                    node_path + [edge.target_id],
                    edge_path + [edge],
                ))

        # Follow backward edges (undirected traversal)
        for edge in graph.get_edges_to(current_id):
            if edge.source_id not in visited:
                visited.add(edge.source_id)
                queue.append((
                    edge.source_id,
                    node_path + [edge.source_id],
                    edge_path + [edge],
                ))

    return QueryResult(query_type="path_between", params=params)


def _by_file(graph: GraphProtocol, file_path: str = "", **_: str) -> QueryResult:
    """Return all nodes belonging to file_path."""
    nodes = tuple(graph.get_nodes_by_file(file_path))
    return QueryResult(
        query_type="by_file",
        params={"file_path": file_path},
        nodes=nodes,
    )


def _by_pattern(graph: GraphProtocol, pattern: str = "", **_: str) -> QueryResult:
    """Return nodes whose name matches the fnmatch glob pattern."""
    matched: list[GraphNode] = [
        node
        for node in graph.iter_nodes()
        if fnmatch.fnmatch(node.properties.name, pattern)
    ]
    return QueryResult(
        query_type="by_pattern",
        params={"pattern": pattern},
        nodes=tuple(matched),
    )


def _by_decorator(graph: GraphProtocol, decorator: str = "", **_: str) -> QueryResult:
    """Return nodes that have the given decorator in their properties.decorators."""
    matched: list[GraphNode] = [
        node
        for node in graph.iter_nodes()
        if decorator in node.properties.decorators
    ]
    return QueryResult(
        query_type="by_decorator",
        params={"decorator": decorator},
        nodes=tuple(matched),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_node_by_name(graph: GraphProtocol, name: str) -> GraphNode | None:
    """Find the first Function, Method, or Class node matching name."""
    _callable_labels = (NodeLabel.FUNCTION, NodeLabel.METHOD, NodeLabel.CLASS)
    for node in graph.iter_nodes():
        if node.properties.name == name and node.label in _callable_labels:
            return node
    return None


def _find_class_by_name(graph: GraphProtocol, name: str) -> GraphNode | None:
    """Find the first Class node matching name."""
    for node in graph.get_nodes_by_label(NodeLabel.CLASS):
        if node.properties.name == name:
            return node
    return None
