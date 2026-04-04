"""Build call graph edges from parsed data + resolution context."""

from __future__ import annotations

import hashlib

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


def _edge_id(source_id: str, target_id: str, line: int) -> str:
    """Deterministic edge ID from source, target, and call site."""
    raw = f"{source_id}->{target_id}@{line}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _find_caller_node_id(
    graph: object,
    caller_name: str | None,
    file_path: str,
) -> str | None:
    """Find the node ID for the calling function in the graph."""
    if caller_name is None:
        return None
    for node in graph.iter_nodes():  # type: ignore[attr-defined]
        if (
            node.label in (NodeLabel.FUNCTION, NodeLabel.METHOD)
            and node.properties.name == caller_name
            and node.properties.file_path == file_path
        ):
            return node.id
    return None


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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_call_edges(
    graph: object,
    parse_results: dict[str, FileParseResult],
    resolution: object,
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
    """
    edges: list[Edge] = []
    seen_ids: set[str] = set()

    for file_path, parse_result in parse_results.items():
        for call in parse_result.calls:
            _process_call(graph, call, resolution, edges, seen_ids)

    return edges


def _process_call(
    graph: object,
    call: ExtractedCall,
    resolution: object,
    edges: list[Edge],
    seen_ids: set[str],
) -> None:
    """Process a single extracted call and append resolved edges."""
    # Find caller node in graph
    caller_id = _find_caller_node_id(graph, call.caller_name, call.file_path)
    if caller_id is None:
        return  # cannot locate caller — skip

    # Resolve callee
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
