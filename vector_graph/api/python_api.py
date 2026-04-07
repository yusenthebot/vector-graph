"""Python API for code analysis.

Main entry point for programmatic use and CLI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vector_graph._types import (
    AnalysisResult,
    GraphNode,
    ImpactResult,
    NodeLabel,
    ProcessTrace,
    QueryResult,
)
from vector_graph.graph.knowledge_graph import KnowledgeGraph


class CodeGraph:
    """Main entry point for code analysis.

    Usage::

        cg = CodeGraph("/path/to/project")
        result = cg.analyze()
        print(result.function_count)

        impact = cg.impact("validate_email", direction="upstream")
        print(impact.risk)
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._graph: KnowledgeGraph | None = None
        self._result: AnalysisResult | None = None

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def analyze(self) -> AnalysisResult:
        """Run the full analysis pipeline and cache the result."""
        from vector_graph.pipeline import run_pipeline

        self._graph, self._result = run_pipeline(self._root)
        return self._result

    def _ensure_analyzed(self) -> None:
        """Analyze if not already done."""
        if self._graph is None or self._result is None:
            self.analyze()

    def impact(
        self,
        target: str,
        direction: str = "upstream",
        max_depth: int = 3,
    ) -> ImpactResult:
        """Blast radius analysis for a named symbol.

        Parameters
        ----------
        target:
            Function/class name to analyse.
        direction:
            'upstream' (who calls target) or 'downstream' (what target calls).
        max_depth:
            Maximum BFS depth.
        """
        self._ensure_analyzed()
        from vector_graph.analysis.impact import analyze_impact

        graph = self._graph
        assert graph is not None

        # Find the target node by name
        target_id = _find_node_id_by_name(graph, target)
        if target_id is None:
            # Return empty result
            return _empty_impact(target, direction)

        return analyze_impact(graph, target_id, direction=direction, max_depth=max_depth)

    def trace(self, entry: str) -> list[ProcessTrace]:
        """Execution flow traces starting from a named entry point.

        Parameters
        ----------
        entry:
            Name of the entry point function.
        """
        self._ensure_analyzed()
        from vector_graph.analysis.execution_flow import detect_execution_flows

        graph = self._graph
        assert graph is not None

        # Filter traces that start from the named entry point
        all_traces = detect_execution_flows(graph, min_steps=1)
        entry_id = _find_node_id_by_name(graph, entry)
        if entry_id is None:
            return []
        return [t for t in all_traces if t.entry_point_id == entry_id]

    def cycles(self) -> list:
        """Detect dependency cycles in the codebase.

        Returns
        -------
        list[CycleInfo]
            Each entry describes one strongly-connected component that forms
            a cycle (CALLS, IMPORTS, or EXTENDS edges only).
        """
        self._ensure_analyzed()
        from vector_graph.analysis.cycles import detect_cycles

        assert self._graph is not None
        return detect_cycles(self._graph)

    def orphans(self) -> list[GraphNode]:
        """Find unreachable functions/classes."""
        self._ensure_analyzed()
        from vector_graph.analysis.orphan import find_orphans

        graph = self._graph
        assert graph is not None
        return find_orphans(graph)

    def query(self, query_type: str, **kwargs: str) -> QueryResult:
        """Execute a structured query against the graph.

        Parameters
        ----------
        query_type:
            One of: callers_of, callees_of, subclasses_of, implementations_of,
            path_between, by_file, by_pattern, by_decorator.
        **kwargs:
            Query-specific parameters (name, source, target, file_path, pattern, decorator).

        Returns
        -------
        QueryResult with .nodes, .edges, .count populated.
        Returns empty QueryResult for unknown query types.
        """
        self._ensure_analyzed()
        from vector_graph.analysis.query import execute_query

        assert self._graph is not None
        return execute_query(self._graph, query_type, **kwargs)

    def health(self, root_path: str | None = None) -> "HealthReport":
        """Compute codebase health metrics.

        Parameters
        ----------
        root_path:
            Project root for grouping nodes by directory. Defaults to self._root.

        Returns
        -------
        HealthReport
            Full report with per-function complexity scores and per-module health.
        """
        self._ensure_analyzed()
        from vector_graph.analysis.complexity import HealthReport, build_health_report

        assert self._graph is not None
        return build_health_report(self._graph, root_path or str(self._root))

    def export(self, format: str = "json") -> str:
        """Export the graph to a string format.

        Parameters
        ----------
        format:
            "json" (default) or "dot".

        Returns
        -------
        str
            Serialised graph as a JSON or DOT string.
        """
        self._ensure_analyzed()
        from vector_graph.analysis.export import export_dot, export_json

        graph = self._graph
        assert graph is not None
        if format == "dot":
            return export_dot(graph)
        return export_json(graph)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_node_id_by_name(graph: KnowledgeGraph, name: str) -> str | None:
    """Find the first node whose properties.name matches name."""
    for node in graph.iter_nodes():
        if node.properties.name == name and node.label in (
            NodeLabel.FUNCTION,
            NodeLabel.METHOD,
            NodeLabel.CLASS,
        ):
            return node.id
    return None


def _empty_impact(target_name: str, direction: str) -> ImpactResult:
    """Return an empty ImpactResult for an unresolvable target."""
    from vector_graph._types import ImpactResult
    return ImpactResult(
        target_name=target_name,
        target_file="",
        direction=direction,
        risk="LOW",
        entries=(),
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point: vector-graph <root> [--serve] [--watch] [--tui] [--impact NAME] ..."""
    parser = argparse.ArgumentParser(
        prog="vector-graph",
        description="Python code knowledge graph analyser",
    )
    parser.add_argument("root", nargs="?", default=".", help="Project root directory (default: .)")
    parser.add_argument("--serve", action="store_true", help="Start web visualization at localhost")
    parser.add_argument("--port", type=int, default=5555, help="Web server port (default: 5555)")
    parser.add_argument("--max-nodes", type=int, default=2000, help="Max nodes in visualization (default: 2000)")
    parser.add_argument("--watch", action="store_true", help="Watch for file changes")
    parser.add_argument("--tui", action="store_true", help="Terminal UI dashboard (requires rich)")
    parser.add_argument("--impact", metavar="NAME", help="Run impact analysis on NAME")
    parser.add_argument(
        "--direction",
        choices=["upstream", "downstream"],
        default="upstream",
        help="Impact direction (default: upstream)",
    )
    parser.add_argument("--orphans", action="store_true", help="List orphan functions/classes")
    parser.add_argument("--depth", type=int, default=3, metavar="N", help="Max BFS depth (default: 3)")
    parser.add_argument(
        "--export",
        choices=["json", "dot"],
        metavar="FORMAT",
        help="Export graph to FORMAT (json or dot) and print to stdout",
    )
    parser.add_argument("--install-hook", action="store_true", help="Install Claude Code PreToolUse hook")
    parser.add_argument("--dev", action="store_true", help="Dev mode: auto-reload on file changes")
    args = parser.parse_args()

    # Handle --install-hook before anything else
    if args.install_hook:
        from vector_graph.hooks.install import install_hook_auto
        install_hook_auto()
        return

    from vector_graph.api.visualize import print_summary, print_impact

    root_path = Path(args.root).expanduser().resolve()
    if not root_path.is_dir():
        print(f"Error: '{args.root}' is not a valid directory", file=sys.stderr)
        sys.exit(1)

    cg = CodeGraph(root_path)
    result = cg.analyze()
    print_summary(result)

    if args.export:
        print(cg.export(args.export))

    if args.impact:
        impact = cg.impact(args.impact, direction=args.direction, max_depth=args.depth)
        print_impact(impact)

    if args.orphans:
        orphan_nodes = cg.orphans()
        print(f"\nOrphans ({len(orphan_nodes)}):")
        for node in orphan_nodes:
            print(f"  {node.label.value}  {node.properties.name}  ({node.properties.file_path})")

    # --watch mode: start file watcher, optionally serve and/or run TUI
    if args.watch:
        import threading
        import time as _time
        from vector_graph.watch.file_watcher import GraphWatcher
        from vector_graph.watch.change_tracker import ChangeTracker

        assert cg._graph is not None

        watcher = GraphWatcher(cg._root, cg._graph)
        tracker = ChangeTracker(cg._graph)
        watcher.change_tracker = tracker
        watcher.start()

        try:
            if args.serve:
                from vector_graph.api.web_server import serve
                server_thread = threading.Thread(
                    target=serve,
                    args=(cg._graph,),
                    kwargs={
                        "root_path": str(cg._root),
                        "port": args.port,
                        "max_nodes": args.max_nodes,
                        "change_tracker": tracker,
                        "dev": args.dev,
                    },
                    daemon=True,
                )
                server_thread.start()
                print(f"Web radar at http://127.0.0.1:{args.port}")

            if args.tui:
                from vector_graph.api.tui import run_tui
                run_tui(tracker, result)
            elif not args.serve:
                # Plain watch mode — print change events to stdout
                tracker.on_change(
                    lambda e: print(
                        f"[{e.change_type}] {e.file_path.split('/')[-1]} "
                        f"risk={e.risk} affected={e.affected_count}"
                    )
                )
                print("Watching for changes... (Ctrl+C to stop)")
                try:
                    while True:
                        _time.sleep(1)
                except KeyboardInterrupt:
                    pass
            else:
                # --watch --serve: block until interrupted
                try:
                    while True:
                        _time.sleep(1)
                except KeyboardInterrupt:
                    pass
        finally:
            watcher.stop()
        return

    # --serve without --watch: static web view
    if args.serve:
        from vector_graph.api.web_server import serve
        serve(cg._graph, root_path=str(cg._root), port=args.port, max_nodes=args.max_nodes, dev=args.dev)
