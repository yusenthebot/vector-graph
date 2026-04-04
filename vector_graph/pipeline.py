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


def _node_id(raw: str) -> str:
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

        # Register module-level variables/assignments as Variable nodes
        for assign in result.assignments:
            if assign.declared_type or assign.value_type:
                var_id = _node_id(f"var:{assign.name}:{file_path}:{assign.line}")
                props = NodeProperties(
                    name=assign.name,
                    file_path=file_path,
                    start_line=assign.line,
                    declared_type=assign.declared_type or assign.value_type,
                )
                graph.add_node(GraphNode(id=var_id, label=NodeLabel.VARIABLE, properties=props))

        file_node_id = _file_node_id(file_path)

        # CONTAINS edges: File -> Function/Class (top-level symbols)
        for fn in result.functions:
            if not fn.is_method:  # only top-level functions, not methods
                fn_id = _fn_node_id(fn.name, file_path, fn.start_line)
                eid = _edge_id(file_node_id, fn_id, EdgeType.CONTAINS)
                graph.add_edge(Edge(id=eid, source_id=file_node_id, target_id=fn_id,
                                    edge_type=EdgeType.CONTAINS, confidence=1.0))
        for cls in result.classes:
            cls_id = _class_node_id(cls.name, file_path, cls.start_line)
            eid = _edge_id(file_node_id, cls_id, EdgeType.CONTAINS)
            graph.add_edge(Edge(id=eid, source_id=file_node_id, target_id=cls_id,
                                edge_type=EdgeType.CONTAINS, confidence=1.0))

        # HAS_METHOD edges: Class -> Method
        class_id_map: dict[str, str] = {}
        for cls in result.classes:
            class_id_map[cls.name] = _class_node_id(cls.name, file_path, cls.start_line)

        for fn in result.functions:
            if fn.is_method and fn.owner_class and fn.owner_class in class_id_map:
                method_id = _fn_node_id(fn.name, file_path, fn.start_line)
                cls_id = class_id_map[fn.owner_class]
                eid = _edge_id(cls_id, method_id, EdgeType.HAS_METHOD)
                graph.add_edge(Edge(id=eid, source_id=cls_id, target_id=method_id,
                                    edge_type=EdgeType.HAS_METHOD, confidence=0.95))



def _phase3b_resolve_heritage(
    graph: KnowledgeGraph,
    symbol_table: SymbolTable,
    parse_results: dict[str, FileParseResult],
) -> None:
    """Resolve EXTENDS and DECORATES edges now that all symbols are registered."""
    for file_path, result in parse_results.items():
        # Build class ID map for this file
        class_id_map: dict[str, str] = {}
        for cls in result.classes:
            class_id_map[cls.name] = _class_node_id(cls.name, file_path, cls.start_line)

        # EXTENDS: Class -> Base Class
        for cls in result.classes:
            if not cls.bases:
                continue
            child_id = class_id_map[cls.name]
            for base_name in cls.bases:
                clean_base = base_name.split(".")[-1]
                base_syms = symbol_table.lookup_global(clean_base)
                base_sym = next((s for s in base_syms if s.label == NodeLabel.CLASS), None)
                if base_sym and base_sym.node_id != child_id:
                    eid = _edge_id(child_id, base_sym.node_id, EdgeType.EXTENDS)
                    graph.add_edge(Edge(id=eid, source_id=child_id, target_id=base_sym.node_id,
                                        edge_type=EdgeType.EXTENDS, confidence=0.85))

        # DECORATES: Decorator -> decorated Function/Class
        for fn in result.functions:
            if not fn.decorators:
                continue
            fn_id = _fn_node_id(fn.name, file_path, fn.start_line)
            for dec_name in fn.decorators:
                clean_name = dec_name.split("(")[0].split(".")[-1]
                dec_syms = symbol_table.lookup_global(clean_name)
                dec_sym = next(
                    (s for s in dec_syms if s.label in (NodeLabel.FUNCTION, NodeLabel.CLASS)),
                    None,
                )
                if dec_sym and dec_sym.node_id != fn_id:
                    eid = _edge_id(dec_sym.node_id, fn_id, EdgeType.DECORATES)
                    graph.add_edge(Edge(id=eid, source_id=dec_sym.node_id, target_id=fn_id,
                                        edge_type=EdgeType.DECORATES, confidence=0.8))

        for cls in result.classes:
            if not cls.decorators:
                continue
            cls_id = class_id_map[cls.name]
            for dec_name in cls.decorators:
                clean_name = dec_name.split("(")[0].split(".")[-1]
                dec_syms = symbol_table.lookup_global(clean_name)
                dec_sym = next(
                    (s for s in dec_syms if s.label in (NodeLabel.FUNCTION, NodeLabel.CLASS)),
                    None,
                )
                if dec_sym and dec_sym.node_id != cls_id:
                    eid = _edge_id(dec_sym.node_id, cls_id, EdgeType.DECORATES)
                    graph.add_edge(Edge(id=eid, source_id=dec_sym.node_id, target_id=cls_id,
                                        edge_type=EdgeType.DECORATES, confidence=0.8))


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
    type_map=None,
    symbol_table: SymbolTable | None = None,
) -> int:
    """Build call edges using a resolution-context adapter.

    When type_map and symbol_table are provided, attribute calls are resolved
    against the inferred receiver type first (phase 3c type-aware resolution).
    """
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
    edges = build_call_edges(
        graph, parse_results, adapter,
        type_map=type_map, symbol_table=symbol_table,
    )
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

    # Phase 3b: EXTENDS + DECORATES (need all symbols registered first)
    _progress("phase3b: resolving inheritance + decorators")
    _phase3b_resolve_heritage(graph, symbol_table, parse_results)

    # Phase 3c: Type inference
    _progress("phase3c: inferring variable types")
    from vector_graph.analysis.type_inference import build_type_map
    type_map = build_type_map(parse_results, symbol_table)

    # Phase 4
    _progress("phase4: resolving imports")
    all_files = set(file_paths)
    import_count = _phase4_resolve_imports(
        graph, resolution, parse_results, all_files, root_str
    )

    # Phase 5
    _progress("phase5: building call edges")
    call_count = _phase5_build_call_edges(
        graph, resolution, parse_results,
        type_map=type_map, symbol_table=symbol_table,
    )

    # Phase 6
    _progress("phase6: detecting communities")
    from vector_graph.analysis.community import detect_communities
    communities = detect_communities(graph)

    # Phase 7
    _progress("phase7: detecting execution flows")
    from vector_graph.analysis.execution_flow import detect_execution_flows
    flows = detect_execution_flows(graph)

    # Phase 8: ROS2 extraction
    _progress("phase8: extracting ROS2 nodes/topics/services")
    try:
        from vector_graph.ros2.node_extractor import extract_ros2_nodes
        from vector_graph.ros2.ros2_graph import build_ros2_overlay
        from vector_graph.ros2.launch_parser import parse_launch_file
        from vector_graph.ros2.msg_parser import parse_msg_file, parse_srv_file

        all_ros2_nodes = []
        all_launch_info = []
        all_msg_defs = []
        for fp in file_paths:
            try:
                ros2_nodes = extract_ros2_nodes(fp)
                if ros2_nodes:
                    all_ros2_nodes.extend(ros2_nodes)
            except Exception:
                pass
            # Parse launch files
            if "launch" in os.path.basename(fp).lower():
                try:
                    li = parse_launch_file(fp)
                    if li.nodes:
                        all_launch_info.append(li)
                except Exception:
                    pass

        # Parse .msg and .srv files
        msg_dir = Path(root)
        for msg_file in msg_dir.rglob("*.msg"):
            try:
                all_msg_defs.append(parse_msg_file(str(msg_file)))
            except Exception:
                pass
        for srv_file in msg_dir.rglob("*.srv"):
            try:
                from vector_graph.ros2.msg_parser import parse_srv_file
                all_msg_defs.append(parse_srv_file(str(srv_file)))
            except Exception:
                pass

        if all_ros2_nodes:
            build_ros2_overlay(graph, all_ros2_nodes, all_launch_info)
            _progress(f"phase8: found {len(all_ros2_nodes)} ROS2 nodes")
        else:
            _progress("phase8: no ROS2 nodes found")
    except ImportError:
        _progress("phase8: ROS2 modules not available, skipping")

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
