"""Build call graph edges from parsed data + resolution context."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from vector_graph._types import (
    Edge,
    EdgeType,
    ExtractedCall,
    FileParseResult,
    NodeLabel,
    ResolutionTier,
    SymbolDef,
    TIER_CONFIDENCE,
)
from vector_graph.graph.protocols import GraphProtocol

if TYPE_CHECKING:
    from vector_graph.analysis.type_inference import TypeMap
    from vector_graph.graph.symbol_table import SymbolTable


def _edge_id(source_id: str, target_id: str, line: int) -> str:
    """Deterministic edge ID from source, target, and call site."""
    raw = f"{source_id}->{target_id}@{line}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _find_caller_node_id(
    graph: GraphProtocol,
    caller_name: str | None,
    file_path: str,
) -> str | None:
    """Find the node ID for the calling function in the graph.

    Kept for backward compatibility — no longer called by build_call_edges.
    Prefer _build_caller_index() + dict.get() for O(1) lookup.
    """
    if caller_name is None:
        return None
    for node in graph.iter_nodes():
        if (
            node.label in (NodeLabel.FUNCTION, NodeLabel.METHOD)
            and node.properties.name == caller_name
            and node.properties.file_path == file_path
        ):
            return node.id
    return None


def _build_caller_index(graph: GraphProtocol) -> dict[tuple[str, str], str]:
    """Build (name, file_path) -> node_id index for Function/Method nodes.

    Replaces O(N) linear scan with O(1) dict lookup per call site.
    Called once per build_call_edges invocation — O(N) total instead of O(N*M).
    """
    index: dict[tuple[str, str], str] = {}
    for node in graph.iter_nodes():
        if node.label in (NodeLabel.FUNCTION, NodeLabel.METHOD):
            key = (node.properties.name, node.properties.file_path)
            index[key] = node.id
    return index


def _arity_matches(symbol: SymbolDef, arg_count: int) -> bool:
    """Return True if the symbol's parameter count is compatible with arg_count."""
    if symbol.parameter_count is None:
        return True  # unknown — don't filter
    # Allow off-by-one for 'self' parameter in methods
    return symbol.parameter_count == arg_count or symbol.parameter_count == arg_count + 1


def _resolve_call(
    call: ExtractedCall,
    resolution: object,
) -> tuple[list[SymbolDef], ResolutionTier] | None:
    """Resolve a call to a list of candidate symbols + tier."""
    result = resolution.resolve(call.file_path, call.callee_name)  # type: ignore[attr-defined]
    return result  # type: ignore[return-value]


def _find_methods_on_class_hierarchy(
    class_name: str,
    method_name: str,
    symbol_table: "SymbolTable",
    graph: GraphProtocol,
) -> list[SymbolDef]:
    """Find methods named method_name on class_name and its base classes.

    Performs a BFS over the class hierarchy following EXTENDS edges in the graph
    and base class names stored on NodeProperties.bases.
    """
    candidates: list[SymbolDef] = []
    visited_classes: set[str] = set()
    queue: list[str] = [class_name]

    while queue:
        cls = queue.pop(0)
        if cls in visited_classes:
            continue
        visited_classes.add(cls)

        # Look up all symbols named method_name — keep only METHODs belonging to cls
        for sym in symbol_table.lookup_global(method_name):
            if sym.label != NodeLabel.METHOD:
                continue
            # Verify this method is owned by cls via a HAS_METHOD edge
            for edge in graph.get_edges_to(sym.node_id):
                if edge.edge_type == EdgeType.HAS_METHOD:
                    parent_node = graph.get_node(edge.source_id)
                    if parent_node and parent_node.properties.name == cls:
                        candidates.append(sym)
                        break

        # Enqueue base classes by consulting the symbol table for cls's CLASS node
        for cls_sym in symbol_table.lookup_global(cls):
            if cls_sym.label != NodeLabel.CLASS:
                continue
            cls_node = graph.get_node(cls_sym.node_id)
            if cls_node and cls_node.properties.bases:
                for base in cls_node.properties.bases:
                    clean_base = base.split(".")[-1]
                    if clean_base not in visited_classes:
                        queue.append(clean_base)

    return candidates


def _resolve_typed_attribute_call(
    call: ExtractedCall,
    type_map: "TypeMap",
    symbol_table: "SymbolTable",
    graph: GraphProtocol,
) -> tuple[list[SymbolDef], float] | None:
    """Resolve obj.method() using receiver type info from TypeMap.

    Returns (candidates, confidence) or None if the receiver type is unknown.
    """
    if not call.is_attribute or not call.receiver:
        return None

    # For self.method() — use caller_class directly
    if call.receiver == "self" and call.caller_class:
        candidates = _find_methods_on_class_hierarchy(
            call.caller_class, call.callee_name, symbol_table, graph
        )
        if candidates:
            return candidates, 0.95
        return None

    # For self.attr.method() or x.method() — use TypeMap
    scope = call.caller_class or call.caller_name or "<module>"
    receiver_type = type_map.lookup_attribute(call.file_path, scope, call.receiver)
    if receiver_type is None:
        return None

    candidates = _find_methods_on_class_hierarchy(
        receiver_type, call.callee_name, symbol_table, graph
    )
    if candidates:
        return candidates, 0.95
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_call_edges(
    graph: GraphProtocol,
    parse_results: dict[str, FileParseResult],
    resolution: object,
    type_map: "TypeMap | None" = None,
    symbol_table: "SymbolTable | None" = None,
) -> list[Edge]:
    """Resolve extracted calls to graph edges via tiered resolution.

    Parameters
    ----------
    graph:
        Duck-typed knowledge graph.
    parse_results:
        Mapping of file_path -> FileParseResult.
    resolution:
        Duck-typed resolution context with a ``resolve(file_path, name)``
        method that returns ``(candidates, tier)`` or ``None``.
    type_map:
        Optional TypeMap for type-aware attribute call resolution.
        When provided (with symbol_table), attribute calls are resolved
        against the inferred receiver type first (confidence 0.95).
    symbol_table:
        Optional SymbolTable used together with type_map for class hierarchy
        traversal during typed attribute call resolution.
    """
    edges: list[Edge] = []
    seen_ids: set[str] = set()
    caller_index = _build_caller_index(graph)  # O(N) once — avoids O(N*M) repeated scans

    for file_path, parse_result in parse_results.items():
        for call in parse_result.calls:
            _process_call(
                graph, call, resolution, edges, seen_ids, caller_index,
                type_map=type_map, symbol_table=symbol_table,
            )

    return edges


def _process_call(
    graph: GraphProtocol,
    call: ExtractedCall,
    resolution: object,
    edges: list[Edge],
    seen_ids: set[str],
    caller_index: dict[tuple[str, str], str],
    type_map: "TypeMap | None" = None,
    symbol_table: "SymbolTable | None" = None,
) -> None:
    """Process a single extracted call and append resolved edges.

    For attribute calls, tries type-aware resolution first when type_map and
    symbol_table are provided. Falls back to the existing tiered resolution when
    type information is not available.
    """
    # Find caller node in graph via O(1) index lookup
    if call.caller_name is None:
        return  # cannot locate caller — skip
    caller_id = caller_index.get((call.caller_name, call.file_path))
    if caller_id is None:
        return  # caller not found in graph — skip

    # Try type-aware resolution first for attribute calls
    if call.is_attribute and type_map is not None and symbol_table is not None:
        typed_result = _resolve_typed_attribute_call(call, type_map, symbol_table, graph)
        if typed_result is not None:
            typed_candidates, typed_confidence = typed_result
            viable = [s for s in typed_candidates if _arity_matches(s, call.arg_count)]
            if viable:
                for symbol in viable:
                    eid = _edge_id(caller_id, symbol.node_id, call.line)
                    if eid in seen_ids:
                        continue
                    seen_ids.add(eid)
                    edges.append(Edge(
                        id=eid,
                        source_id=caller_id,
                        target_id=symbol.node_id,
                        edge_type=EdgeType.CALLS,
                        confidence=typed_confidence,
                        reason="type-inferred resolution",
                    ))
                return  # typed resolution succeeded — skip fallback

    # Fallback: existing tiered resolution
    resolved = _resolve_call(call, resolution)
    if resolved is None:
        return  # unresolvable

    candidates, tier = resolved
    confidence = TIER_CONFIDENCE[tier]

    # Arity filtering: remove candidates with incompatible param counts
    viable = [s for s in candidates if _arity_matches(s, call.arg_count)]
    if not viable:
        return

    for symbol in viable:
        eid = _edge_id(caller_id, symbol.node_id, call.line)
        if eid in seen_ids:
            continue
        seen_ids.add(eid)

        edge = Edge(
            id=eid,
            source_id=caller_id,
            target_id=symbol.node_id,
            edge_type=EdgeType.CALLS,
            confidence=confidence,
            reason=f"{tier.value} resolution",
        )
        edges.append(edge)
