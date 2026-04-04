"""Multi-phase analysis pipeline.

Phase 1: Walk filesystem, create File nodes
Phase 2: Parse each .py file
Phase 3: Register symbols in SymbolTable
Phase 4: Resolve imports, create IMPORTS edges
Phase 5: Build call edges via ResolutionContext
Phase 6: Detect communities
Phase 7: Detect execution flows
Phase 8: (Future) ROS2 extraction
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Callable

from vector_graph._types import (
    AnalysisResult,
    Edge,
    EdgeType,
    ExtractedFunction,
    ExtractedImport,
    FileParseResult,
    GraphNode,
    NodeLabel,
    NodeProperties,
    SymbolDef,
)
from vector_graph.graph.knowledge_graph import KnowledgeGraph
from vector_graph.graph.resolution import ResolutionContext
from vector_graph.graph.symbol_table import SymbolTable
from vector_graph.parse.python_imports import resolve_import
from vector_graph.parse.python_parser import parse_file


# ---------------------------------------------------------------------------
# Node ID helpers
# ---------------------------------------------------------------------------

def _file_node_id(file_path: str) -> str:
    h = hashlib.md5(file_path.encode()).hexdigest()[:8]
    return f"file:{h}"


def _fn_node_id(name: str, file_path: str, start_line: int) -> str:
    raw = f"fn:{file_path}:{name}:{start_line}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _class_node_id(name: str, file_path: str, start_line: int) -> str:
    raw = f"cls:{file_path}:{name}:{start_line}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _edge_id(source_id: str, target_id: str, edge_type: EdgeType) -> str:
    raw = f"{source_id}-{edge_type.value}->{target_id}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Phase helpers
# ---------------------------------------------------------------------------

def _is_test_file(file_path: str) -> bool:
    basename = os.path.basename(file_path)
    name_no_ext = os.path.splitext(basename)[0]
    return basename.startswith("test_") or name_no_ext.endswith("_test")


_SKIP_DIRS: frozenset[str] = frozenset({
    ".venv", ".venv-nano", "venv", "env",
    ".git", ".hg", ".svn",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "node_modules", ".tox", ".nox",
    "build", "dist", ".eggs", "*.egg-info",
    ".history", ".sisyphus",
})


def _walk_python_files(root: Path) -> list[str]:
    """Return all .py file paths under root, skipping non-source directories."""
    results: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip dirs in-place
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.endswith(".egg-info")]
        for fname in filenames:
            if fname.endswith(".py"):
                results.append(os.path.join(dirpath, fname))
    return results


def _phase1_create_file_nodes(
    graph: KnowledgeGraph,
    file_paths: list[str],
) -> None:
    """Create File nodes for each Python file."""
    for fp in file_paths:
        node_id = _file_node_id(fp)
        props = NodeProperties(
            name=os.path.basename(fp),
            file_path=fp,
        )
        graph.add_node(GraphNode(id=node_id, label=NodeLabel.FILE, properties=props))


def _phase2_parse_files(file_paths: list[str]) -> dict[str, FileParseResult]:
    """Parse all Python files and return file_path -> FileParseResult."""
    return {fp: parse_file(fp) for fp in file_paths}


def _phase3_register_symbols(
    graph: KnowledgeGraph,
    symbol_table: SymbolTable,
    parse_results: dict[str, FileParseResult],
) -> None:
    """Register symbols from parse results into graph and symbol table."""
    for file_path, result in parse_results.items():
        # Register functions
        for fn in result.functions:
            label = NodeLabel.METHOD if fn.is_method else NodeLabel.FUNCTION
            node_id = _fn_node_id(fn.name, file_path, fn.start_line)
            params = fn.parameters
            props = NodeProperties(
                name=fn.name,
                file_path=file_path,
                start_line=fn.start_line,
                end_line=fn.end_line,
                is_async=fn.is_async,
                return_type=fn.return_type,
                parameters=params,
                parameter_count=len(params),
                decorators=fn.decorators,
                docstring=fn.docstring,
            )
            node = GraphNode(id=node_id, label=label, properties=props)
            graph.add_node(node)

            sym = SymbolDef(
                node_id=node_id,
                name=fn.name,
                file_path=file_path,
                label=label,
                parameter_count=len(params),
            )
            symbol_table.register(sym)

        # Register classes
        for cls in result.classes:
            node_id = _class_node_id(cls.name, file_path, cls.start_line)
            props = NodeProperties(
                name=cls.name,
                file_path=file_path,
                start_line=cls.start_line,
                end_line=cls.end_line,
                bases=cls.bases,
                decorators=cls.decorators,
                docstring=cls.docstring,
            )
            node = GraphNode(id=node_id, label=NodeLabel.CLASS, properties=props)
            graph.add_node(node)

            sym = SymbolDef(
                node_id=node_id,
                name=cls.name,
                file_path=file_path,
                label=NodeLabel.CLASS,
            )
            symbol_table.register(sym)

        # Create HAS_METHOD edges: Class -> Method
        for fn in result.functions:
            if fn.is_method and fn.owner_class:
                method_id = _fn_node_id(fn.name, file_path, fn.start_line)
                # Find the owning class node
                for cls in result.classes:
                    if cls.name == fn.owner_class:
                        class_id = _class_node_id(cls.name, file_path, cls.start_line)
                        eid = _edge_id(class_id, method_id, EdgeType.HAS_METHOD)
                        graph.add_edge(Edge(
                            id=eid,
                            source_id=class_id,
                            target_id=method_id,
                            edge_type=EdgeType.HAS_METHOD,
                            confidence=0.95,
                        ))
                        break


def _phase4_resolve_imports(
    graph: KnowledgeGraph,
    resolution: ResolutionContext,
    parse_results: dict[str, FileParseResult],
    all_files: set[str],
    root: str,
) -> int:
    """Resolve imports, register in resolution context, create IMPORTS edges."""
    import_count = 0
    for file_path, result in parse_results.items():
        file_node_id = _file_node_id(file_path)
        for imp in result.imports:
            resolved_path = resolve_import(imp, file_path, root, all_files)
            if resolved_path is None:
                continue

            import_count += 1

            # Register in resolution context
            if imp.is_from and imp.names:
                for name in imp.names:
                    resolution.register_named_import(file_path, name, resolved_path)
            else:
                resolution.register_import(file_path, resolved_path)

            # Create IMPORTS edge: file -> resolved file node
            target_file_node_id = _file_node_id(resolved_path)
            if graph.get_node(target_file_node_id) is None:
                continue
            eid = _edge_id(file_node_id, target_file_node_id, EdgeType.IMPORTS)
            edge = Edge(
                id=eid,
                source_id=file_node_id,
                target_id=target_file_node_id,
                edge_type=EdgeType.IMPORTS,
                confidence=1.0,
            )
            graph.add_edge(edge)

    return import_count


def _phase5_build_call_edges(
    graph: KnowledgeGraph,
    resolution: ResolutionContext,
    parse_results: dict[str, FileParseResult],
) -> int:
    """Build call edges using a resolution-context adapter."""
    from vector_graph.analysis.call_graph import build_call_edges

    # Adapt ResolutionContext to the duck-typed interface expected by build_call_edges:
    # build_call_edges calls resolution.resolve(file_path, name)
    # but ResolutionContext.resolve(name, from_file) has swapped arguments
    class _ResolutionAdapter:
        def __init__(self, ctx: ResolutionContext) -> None:
            self._ctx = ctx

        def resolve(self, file_path: str, name: str):
            result = self._ctx.resolve(name, file_path)
            if result.is_empty:
                return None
            return list(result.candidates), result.tier

    adapter = _ResolutionAdapter(resolution)
    edges = build_call_edges(graph, parse_results, adapter)
    for edge in edges:
        graph.add_edge(edge)
    return len(edges)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_pipeline(
    root: str | Path,
    *,
    progress_callback: Callable[[str], None] | None = None,
) -> tuple[KnowledgeGraph, AnalysisResult]:
    """Multi-phase analysis pipeline.

    Parameters
    ----------
    root:
        Root directory to analyse.
    progress_callback:
        Optional callable invoked with a status string at each phase.
    """
    root_path = Path(root).resolve()
    root_str = str(root_path)

    def _progress(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)

    graph = KnowledgeGraph()
    symbol_table = SymbolTable()
    resolution = ResolutionContext(symbol_table)

    # Phase 1
    _progress("phase1: walking filesystem")
    file_paths = _walk_python_files(root_path)
    _phase1_create_file_nodes(graph, file_paths)

    # Phase 2
    _progress("phase2: parsing Python files")
    parse_results = _phase2_parse_files(file_paths)

    # Phase 3
    _progress("phase3: registering symbols")
    _phase3_register_symbols(graph, symbol_table, parse_results)

    # Phase 4
    _progress("phase4: resolving imports")
    all_files = set(file_paths)
    import_count = _phase4_resolve_imports(
        graph, resolution, parse_results, all_files, root_str
    )

    # Phase 5
    _progress("phase5: building call edges")
    call_count = _phase5_build_call_edges(graph, resolution, parse_results)

    # Phase 6
    _progress("phase6: detecting communities")
    from vector_graph.analysis.community import detect_communities
    communities = detect_communities(graph)

    # Phase 7
    _progress("phase7: detecting execution flows")
    from vector_graph.analysis.execution_flow import detect_execution_flows
    flows = detect_execution_flows(graph)

    # Phase 8: ROS2 extraction (future)
    _progress("phase8: skipped (ROS2 extraction pending)")

    # Tally counts
    file_count = sum(
        1 for _ in graph.get_nodes_by_label(NodeLabel.FILE)
    )
    function_count = sum(
        1 for _ in graph.get_nodes_by_label(NodeLabel.FUNCTION)
    ) + sum(
        1 for _ in graph.get_nodes_by_label(NodeLabel.METHOD)
    )
    class_count = sum(
        1 for _ in graph.get_nodes_by_label(NodeLabel.CLASS)
    )

    result = AnalysisResult(
        root=root_str,
        node_count=graph.node_count,
        edge_count=graph.edge_count,
        file_count=file_count,
        function_count=function_count,
        class_count=class_count,
        import_count=import_count,
        call_count=call_count,
        community_count=len(communities),
        process_count=len(flows),
    )

    return graph, result
