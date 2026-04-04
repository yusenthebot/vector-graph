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

    def orphans(self) -> list[GraphNode]:
        """Find unreachable functions/classes."""
        self._ensure_analyzed()
        from vector_graph.analysis.orphan import find_orphans

        graph = self._graph
        assert graph is not None
        return find_orphans(graph)


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
    """CLI entry point: vector-graph <root> [--serve] [--impact NAME] [--orphans]."""
    parser = argparse.ArgumentParser(
        prog="vector-graph",
        description="Python code knowledge graph analyser",
    )
    parser.add_argument("root", nargs="?", default=".", help="Project root directory (default: .)")
    parser.add_argument("--serve", action="store_true", help="Start web visualization at localhost")
    parser.add_argument("--port", type=int, default=5555, help="Web server port (default: 5555)")
    parser.add_argument("--max-nodes", type=int, default=400, help="Max nodes in visualization (default: 400)")
    parser.add_argument("--impact", metavar="NAME", help="Run impact analysis on NAME")
    parser.add_argument(
        "--direction",
        choices=["upstream", "downstream"],
        default="upstream",
        help="Impact direction (default: upstream)",
    )
    parser.add_argument("--orphans", action="store_true", help="List orphan functions/classes")
    parser.add_argument("--depth", type=int, default=3, metavar="N", help="Max BFS depth (default: 3)")
    args = parser.parse_args()

    from vector_graph.api.visualize import print_summary, print_impact

    cg = CodeGraph(args.root)
    result = cg.analyze()
    print_summary(result)

    if args.impact:
        impact = cg.impact(args.impact, direction=args.direction, max_depth=args.depth)
        print_impact(impact)

    if args.serve:
        from vector_graph.api.web_server import serve
        serve(cg._graph, root_path=str(cg._root), port=args.port, max_nodes=args.max_nodes)

    if args.orphans:
        orphan_nodes = cg.orphans()
        print(f"\nOrphans ({len(orphan_nodes)}):")
        for node in orphan_nodes:
            print(f"  {node.label.value}  {node.properties.name}  ({node.properties.file_path})")
