"""Incremental file watcher for the vector-graph knowledge graph.

Watches a directory tree for Python file changes and applies incremental
updates to a KnowledgeGraph:

  - File created  -> parse + register symbols in graph
  - File modified -> remove_nodes_by_file + re-parse + re-register
  - File deleted  -> remove_nodes_by_file only

Debouncing prevents bursts of filesystem events (e.g. editor save storms)
from triggering redundant re-parses.

Thread safety: all graph mutations happen under a lock in the handler thread.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from vector_graph._types import (
    Edge,
    EdgeType,
    FileParseResult,
    GraphNode,
    NodeLabel,
    NodeProperties,
    SymbolDef,
)
from vector_graph.graph.knowledge_graph import KnowledgeGraph
from vector_graph.graph.resolution import ResolutionContext
from vector_graph.graph.symbol_table import SymbolTable
from vector_graph.parse.python_parser import parse_file

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node-ID helpers  (mirrors pipeline.py so IDs are consistent)
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
# Internal helpers
# ---------------------------------------------------------------------------

def _is_python_file(path: str) -> bool:
    return path.endswith(".py")


def _register_file_in_graph_from_result(
    file_path: str,
    result: FileParseResult,
    graph: KnowledgeGraph,
    symbol_table: SymbolTable,
) -> None:
    """Register symbols from a pre-parsed FileParseResult into graph + symbol_table.

    Mirrors _register_file_in_graph but accepts an already-parsed result
    (no disk I/O). Used by _process_event_with_source for test support.
    """
    has_symbols = bool(result.functions or result.classes)
    if not has_symbols:
        return

    file_node_id = _file_node_id(file_path)
    file_props = NodeProperties(
        name=os.path.basename(file_path),
        file_path=file_path,
    )
    graph.add_node(GraphNode(id=file_node_id, label=NodeLabel.FILE, properties=file_props))

    for fn in result.functions:
        label = NodeLabel.METHOD if fn.is_method else NodeLabel.FUNCTION
        node_id = _fn_node_id(fn.name, file_path, fn.start_line)
        props = NodeProperties(
            name=fn.name,
            file_path=file_path,
            start_line=fn.start_line,
            end_line=fn.end_line,
            is_async=fn.is_async,
            return_type=fn.return_type,
            parameters=fn.parameters,
            parameter_count=len(fn.parameters),
            decorators=fn.decorators,
            docstring=fn.docstring,
        )
        graph.add_node(GraphNode(id=node_id, label=label, properties=props))
        symbol_table.register(
            SymbolDef(
                node_id=node_id,
                name=fn.name,
                file_path=file_path,
                label=label,
                parameter_count=len(fn.parameters),
            )
        )

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
        graph.add_node(GraphNode(id=node_id, label=NodeLabel.CLASS, properties=props))
        symbol_table.register(
            SymbolDef(
                node_id=node_id,
                name=cls.name,
                file_path=file_path,
                label=NodeLabel.CLASS,
            )
        )


def _register_file_in_graph(
    file_path: str,
    graph: KnowledgeGraph,
    symbol_table: SymbolTable,
) -> None:
    """Parse file_path and add all symbols to graph + symbol_table.

    Errors (IO, syntax) are caught and logged — the watcher must not crash.
    Only adds nodes when the file actually contains parseable symbols (functions,
    classes).  Empty files and files with only syntax errors leave no trace.
    """
    try:
        result = parse_file(file_path)
    except Exception:
        log.exception("Unexpected error parsing %s", file_path)
        return

    # Only register if there are symbols to record
    has_symbols = bool(result.functions or result.classes)
    if not has_symbols:
        return

    # File node — only added when the file has symbols
    file_node_id = _file_node_id(file_path)
    file_props = NodeProperties(
        name=os.path.basename(file_path),
        file_path=file_path,
    )
    graph.add_node(GraphNode(id=file_node_id, label=NodeLabel.FILE, properties=file_props))

    # Functions & methods
    for fn in result.functions:
        label = NodeLabel.METHOD if fn.is_method else NodeLabel.FUNCTION
        node_id = _fn_node_id(fn.name, file_path, fn.start_line)
        props = NodeProperties(
            name=fn.name,
            file_path=file_path,
            start_line=fn.start_line,
            end_line=fn.end_line,
            is_async=fn.is_async,
            return_type=fn.return_type,
            parameters=fn.parameters,
            parameter_count=len(fn.parameters),
            decorators=fn.decorators,
            docstring=fn.docstring,
        )
        graph.add_node(GraphNode(id=node_id, label=label, properties=props))
        symbol_table.register(
            SymbolDef(
                node_id=node_id,
                name=fn.name,
                file_path=file_path,
                label=label,
                parameter_count=len(fn.parameters),
            )
        )

    # Classes
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
        graph.add_node(GraphNode(id=node_id, label=NodeLabel.CLASS, properties=props))
        symbol_table.register(
            SymbolDef(
                node_id=node_id,
                name=cls.name,
                file_path=file_path,
                label=NodeLabel.CLASS,
            )
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class GraphWatcher:
    """Watch a filesystem tree for Python file changes and update a KnowledgeGraph.

    On file change:
      1. graph.remove_nodes_by_file(changed_path) + symbol_table.remove_file
      2. Re-parse changed file with python_parser
      3. Re-register symbols in graph + symbol_table
      4. Notify callbacks

    On file delete: step 1 + notify callbacks only.
    On file create: steps 1-4 (handles overwrite-create as well).
    """

    def __init__(
        self,
        root: str | Path,
        graph: KnowledgeGraph,
        debounce_sec: float = 0.3,
    ) -> None:
        self._root = Path(root).resolve()
        self._graph = graph
        self._debounce_sec = debounce_sec
        self._symbol_table = SymbolTable()
        self._lock = threading.Lock()
        self._callbacks: list[Callable[[str, str], None]] = []

        # Edge-rebuild state (populated by from_pipeline or lazily on first use)
        self._resolution: ResolutionContext = ResolutionContext(self._symbol_table)
        self._parse_results: dict[str, FileParseResult] = {}
        self._all_files: set[str] = set()
        self._type_map = None  # TypeMap | None — imported lazily to avoid circular deps

        self._observer: Observer | None = None
        # Pending events: file_path -> event_type (latest wins within debounce window)
        self._pending: dict[str, str] = {}
        self._pending_lock = threading.Lock()
        self._timer: threading.Timer | None = None

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_pipeline(
        cls,
        root: str | Path,
        graph: KnowledgeGraph,
        symbol_table: SymbolTable,
        resolution: ResolutionContext,
        parse_results: dict[str, FileParseResult],
        type_map=None,
        debounce_sec: float = 0.3,
    ) -> "GraphWatcher":
        """Create a watcher pre-populated with pipeline state for incremental updates.

        Parameters
        ----------
        root:
            Root directory being watched.
        graph:
            Fully-built KnowledgeGraph from the pipeline.
        symbol_table:
            Populated SymbolTable from the pipeline.
        resolution:
            ResolutionContext populated with import bindings from the pipeline.
        parse_results:
            Mapping of file_path -> FileParseResult from the pipeline.
        type_map:
            Optional TypeMap for type-aware call resolution.
        debounce_sec:
            Debounce window in seconds (default 0.3).
        """
        watcher = cls(root, graph, debounce_sec)
        watcher._symbol_table = symbol_table
        watcher._resolution = resolution
        watcher._parse_results = dict(parse_results)
        watcher._all_files = set(parse_results.keys())
        watcher._type_map = type_map
        return watcher

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start watching. Non-blocking (runs in background thread)."""
        handler = self._Handler(self)
        self._observer = Observer()
        self._observer.schedule(handler, str(self._root), recursive=True)
        self._observer.start()
        log.debug("GraphWatcher started on %s", self._root)

    def stop(self) -> None:
        """Stop watching and clean up."""
        # Cancel any pending debounce timer
        with self._pending_lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None
        log.debug("GraphWatcher stopped")

    def on_change(self, callback: Callable[[str, str], None]) -> None:
        """Register callback(file_path, event_type) for graph changes."""
        self._callbacks.append(callback)

    # ------------------------------------------------------------------
    # Internal: debounce + processing
    # ------------------------------------------------------------------

    def _schedule_event(self, file_path: str, event_type: str) -> None:
        """Accumulate events and reset debounce timer."""
        with self._pending_lock:
            # "deleted" always wins over "modified"/"created"
            existing = self._pending.get(file_path)
            if existing == "deleted" and event_type != "deleted":
                pass  # do not overwrite delete with a later create during same window
            else:
                self._pending[file_path] = event_type

            # Reset timer
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce_sec, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        """Process all pending events once debounce window expires."""
        with self._pending_lock:
            batch = dict(self._pending)
            self._pending.clear()
            self._timer = None

        for file_path, event_type in batch.items():
            self._process_event(file_path, event_type)

    def _process_event(self, file_path: str, event_type: str) -> None:
        """Apply a single file event to the graph (called from timer thread)."""
        with self._lock:
            try:
                # Remove stale nodes and symbols for this file
                self._graph.remove_nodes_by_file(file_path)
                self._symbol_table.remove_file(file_path)

                if event_type != "deleted":
                    # Re-parse from disk and re-register
                    _register_file_in_graph(file_path, self._graph, self._symbol_table)

                    # Update parse results cache and rebuild cross-file edges
                    try:
                        new_result = parse_file(file_path)
                        self._parse_results[file_path] = new_result
                        self._all_files.add(file_path)
                        self._rebuild_edges_for_file(file_path)
                    except Exception:
                        log.exception("Error rebuilding edges for %s", file_path)
                else:
                    # Clean up cache
                    self._parse_results.pop(file_path, None)
                    self._all_files.discard(file_path)
            except Exception:
                log.exception("Error processing event %s on %s", event_type, file_path)

        # Notify callbacks outside the lock
        for cb in list(self._callbacks):
            try:
                cb(file_path, event_type)
            except Exception:
                log.exception("Error in change callback for %s", file_path)

    def _process_event_with_source(
        self, file_path: str, event_type: str, source: str
    ) -> None:
        """Apply a file event using an in-memory source string instead of disk I/O.

        Used exclusively in tests to simulate watcher events without real filesystem
        writes.  Calls the same graph-mutation logic as _process_event but obtains
        the parsed result from ``source`` rather than reading from disk.
        """
        with self._lock:
            try:
                self._graph.remove_nodes_by_file(file_path)
                self._symbol_table.remove_file(file_path)

                if event_type != "deleted":
                    # Re-register using parse result from in-memory source
                    result = parse_file(file_path, source=source)
                    self._parse_results[file_path] = result
                    self._all_files.add(file_path)

                    # Register symbols (mirrors _register_file_in_graph)
                    _register_file_in_graph_from_result(
                        file_path, result, self._graph, self._symbol_table
                    )

                    # Rebuild cross-file edges
                    self._rebuild_edges_for_file(file_path)
                else:
                    self._parse_results.pop(file_path, None)
                    self._all_files.discard(file_path)
            except Exception:
                log.exception(
                    "Error processing event %s on %s", event_type, file_path
                )

        for cb in list(self._callbacks):
            try:
                cb(file_path, event_type)
            except Exception:
                log.exception("Error in change callback for %s", file_path)

    def _rebuild_edges_for_file(self, file_path: str) -> None:
        """Rebuild IMPORTS and CALLS edges involving file_path.

        Called after re-parsing a file.  Removes all IMPORTS and CALLS edges
        where the source node belongs to file_path, then re-runs import and call
        resolution for that file only.

        Structural edges (CONTAINS, HAS_METHOD, EXTENDS, DECORATES) are NOT
        removed here — they are rebuilt by _register_file_in_graph / the symbol
        registration phase.
        """
        # 1. Collect node IDs for nodes that belong to this file
        file_node_ids: set[str] = {
            node.id for node in self._graph.get_nodes_by_file(file_path)
        }

        # 2. Collect IMPORTS / CALLS edges whose *source* is in this file
        #    (we only own outgoing cross-file edges from the changed file)
        _CROSS_FILE_EDGE_TYPES = frozenset({EdgeType.CALLS, EdgeType.IMPORTS})
        edges_to_remove: list[str] = [
            edge.id
            for edge in list(self._graph.iter_edges())
            if edge.edge_type in _CROSS_FILE_EDGE_TYPES
            and edge.source_id in file_node_ids
        ]
        for eid in edges_to_remove:
            self._graph.remove_edge(eid)

        # 3. Re-run import resolution for this file
        if file_path not in self._parse_results:
            return

        result = self._parse_results[file_path]
        file_node_id = _file_node_id(file_path)
        root_str = str(self._root)

        from vector_graph.parse.python_imports import resolve_import

        for imp in result.imports:
            resolved_path = resolve_import(imp, file_path, root_str, self._all_files)
            if resolved_path is None:
                continue

            # Register in resolution context
            if imp.is_from and imp.names:
                for name in imp.names:
                    self._resolution.register_named_import(file_path, name, resolved_path)
            else:
                self._resolution.register_import(file_path, resolved_path)

            # Create IMPORTS edge: file_a -> file_b (both must be in the graph)
            target_file_node_id = _file_node_id(resolved_path)
            if self._graph.get_node(target_file_node_id) is None:
                # Target file not yet in graph — add a file node so the edge can land
                from vector_graph._types import GraphNode, NodeLabel, NodeProperties
                import os
                target_props = NodeProperties(
                    name=os.path.basename(resolved_path),
                    file_path=resolved_path,
                )
                self._graph.add_node(
                    GraphNode(
                        id=target_file_node_id,
                        label=NodeLabel.FILE,
                        properties=target_props,
                    )
                )

            eid = _edge_id(file_node_id, target_file_node_id, EdgeType.IMPORTS)
            edge = Edge(
                id=eid,
                source_id=file_node_id,
                target_id=target_file_node_id,
                edge_type=EdgeType.IMPORTS,
                confidence=1.0,
            )
            self._graph.add_edge(edge)

        # 4. Re-run call resolution for calls originating in this file
        from vector_graph.analysis.call_graph import build_call_edges

        class _ResolutionAdapter:
            def __init__(self, ctx: ResolutionContext) -> None:
                self._ctx = ctx

            def resolve(self, fp: str, name: str):
                r = self._ctx.resolve(name, fp)
                if r.is_empty:
                    return None
                return list(r.candidates), r.tier

        adapter = _ResolutionAdapter(self._resolution)
        single_file_results = {file_path: result}
        call_edges = build_call_edges(
            self._graph,
            single_file_results,
            adapter,
            type_map=self._type_map,
            symbol_table=self._symbol_table,
        )
        for edge in call_edges:
            self._graph.add_edge(edge)

    # ------------------------------------------------------------------
    # Internal event handler
    # ------------------------------------------------------------------

    class _Handler(FileSystemEventHandler):
        """Watchdog handler that filters non-.py events and debounces."""

        def __init__(self, owner: GraphWatcher) -> None:
            super().__init__()
            self._owner = owner

        def on_created(self, event: FileSystemEvent) -> None:
            if not event.is_directory and _is_python_file(str(event.src_path)):
                self._owner._schedule_event(str(event.src_path), "created")

        def on_modified(self, event: FileSystemEvent) -> None:
            if not event.is_directory and _is_python_file(str(event.src_path)):
                self._owner._schedule_event(str(event.src_path), "modified")

        def on_deleted(self, event: FileSystemEvent) -> None:
            if not event.is_directory and _is_python_file(str(event.src_path)):
                self._owner._schedule_event(str(event.src_path), "deleted")

        def on_moved(self, event: FileSystemEvent) -> None:
            # Treat move as: delete src + create dst
            if not event.is_directory:
                src = str(event.src_path)
                dst = str(event.dest_path)
                if _is_python_file(src):
                    self._owner._schedule_event(src, "deleted")
                if _is_python_file(dst):
                    self._owner._schedule_event(dst, "created")
