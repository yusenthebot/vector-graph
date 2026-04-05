"""Code complexity and health metrics.

Provides:
- compute_cyclomatic_complexity(source) -> int
- analyze_complexity(graph) -> list[ComplexityScore]
- analyze_fan(graph) -> dict[str, tuple[int, int]]
- analyze_module_health(graph, scores, root_path) -> list[ModuleHealth]
- build_health_report(graph, root_path) -> HealthReport
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path

from vector_graph._types import EdgeType, NodeLabel
from vector_graph.graph.protocols import GraphProtocol


# ---------------------------------------------------------------------------
# Frozen dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ComplexityScore:
    """Complexity metrics for a single function/method."""

    node_id: str
    name: str
    file_path: str
    cyclomatic: int        # McCabe complexity
    line_count: int        # function body line count
    parameter_count: int   # number of params
    risk: str              # LOW / MEDIUM / HIGH / CRITICAL


@dataclass(frozen=True)
class ModuleHealth:
    """Health metrics for a module (directory group)."""

    group: str
    node_count: int
    avg_complexity: float
    max_complexity: int
    coupling_ratio: float   # cross-group edges / total edges from group
    cohesion: float         # internal CALLS / possible internal edges
    god_functions: int      # functions with cyclomatic > 10
    god_classes: int        # classes with > 20 methods
    risk: str               # LOW / MEDIUM / HIGH / CRITICAL


@dataclass(frozen=True)
class HealthReport:
    """Full codebase health report."""

    total_functions: int
    avg_complexity: float
    high_risk_count: int
    critical_risk_count: int
    functions: tuple[ComplexityScore, ...]
    modules: tuple[ModuleHealth, ...]


# ---------------------------------------------------------------------------
# Cyclomatic complexity
# ---------------------------------------------------------------------------

def compute_cyclomatic_complexity(source: str) -> int:
    """Count decision points in a Python source string.

    Uses McCabe's definition: start at 1, add 1 for each branch point.

    Decision points counted:
    - ast.If, ast.IfExp (ternary)
    - ast.For, ast.AsyncFor
    - ast.While
    - ast.ExceptHandler
    - ast.Assert
    - ast.BoolOp: adds len(values) - 1
    - ast.comprehension: adds len(ifs)
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 1  # unparseable → base complexity

    count = 1  # base path
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.IfExp)):
            count += 1
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            count += 1
        elif isinstance(node, ast.While):
            count += 1
        elif isinstance(node, ast.ExceptHandler):
            count += 1
        elif isinstance(node, ast.Assert):
            count += 1
        elif isinstance(node, ast.BoolOp):
            # 'a and b' → 2 values → 1 decision point; 'a and b and c' → 2
            count += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            count += len(node.ifs)

    return count


def _risk_from_complexity(cyclomatic: int, line_count: int) -> str:
    """Assign risk level based on complexity and function size."""
    if cyclomatic > 20 or line_count > 200:
        return "CRITICAL"
    if cyclomatic > 10 or line_count > 100:
        return "HIGH"
    if cyclomatic > 5 or line_count > 50:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# Per-node analysis
# ---------------------------------------------------------------------------

def analyze_complexity(graph: GraphProtocol) -> list[ComplexityScore]:
    """Compute cyclomatic complexity for all functions/methods in the graph.

    Reads the function source from disk using the node's file_path,
    start_line, and end_line properties.
    """
    scores: list[ComplexityScore] = []

    for node in graph.iter_nodes():
        if node.label not in (NodeLabel.FUNCTION, NodeLabel.METHOD):
            continue
        if not node.properties.file_path or not node.properties.start_line:
            continue

        try:
            lines = Path(node.properties.file_path).read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        except OSError:
            continue

        start = max(0, node.properties.start_line - 1)
        end = node.properties.end_line or (start + 1)
        source = "\n".join(lines[start:end])

        cc = compute_cyclomatic_complexity(source)
        line_count = (node.properties.end_line or 0) - (node.properties.start_line or 0) + 1
        param_count = node.properties.parameter_count or 0
        risk = _risk_from_complexity(cc, line_count)

        scores.append(ComplexityScore(
            node_id=node.id,
            name=node.properties.name,
            file_path=node.properties.file_path,
            cyclomatic=cc,
            line_count=line_count,
            parameter_count=param_count,
            risk=risk,
        ))

    return scores


# ---------------------------------------------------------------------------
# Fan-in / fan-out
# ---------------------------------------------------------------------------

def analyze_fan(graph: GraphProtocol) -> dict[str, tuple[int, int]]:
    """Return {node_id: (fan_in, fan_out)} for all function/method nodes.

    Only CALLS edges are counted.
    """
    fan: dict[str, tuple[int, int]] = {}

    for node in graph.iter_nodes():
        if node.label not in (NodeLabel.FUNCTION, NodeLabel.METHOD):
            continue
        fan_in = sum(
            1 for e in graph.get_edges_to(node.id)
            if e.edge_type == EdgeType.CALLS
        )
        fan_out = sum(
            1 for e in graph.get_edges_from(node.id)
            if e.edge_type == EdgeType.CALLS
        )
        fan[node.id] = (fan_in, fan_out)

    return fan


# ---------------------------------------------------------------------------
# Module health
# ---------------------------------------------------------------------------

def analyze_module_health(
    graph: GraphProtocol,
    complexity_scores: list[ComplexityScore],
    root_path: str = "",
) -> list[ModuleHealth]:
    """Compute health metrics per module (directory group).

    Groups nodes by their first two directory levels relative to root_path.
    """
    # Group nodes by directory
    groups: dict[str, list[str]] = {}     # group_name -> [node_ids]
    node_group: dict[str, str] = {}       # node_id -> group_name

    for node in graph.iter_nodes():
        if node.label not in (NodeLabel.FUNCTION, NodeLabel.METHOD, NodeLabel.CLASS):
            continue
        fp = node.properties.file_path or ""
        if root_path and fp:
            try:
                rel = os.path.relpath(fp, root_path)
                parts = rel.replace("\\", "/").split("/")
                dir_parts = parts[:-1]  # drop filename
                if not dir_parts:
                    group = "root"
                else:
                    group = "/".join(dir_parts[:2])
            except ValueError:
                group = "other"
        else:
            group = "other"

        groups.setdefault(group, []).append(node.id)
        node_group[node.id] = group

    # Complexity lookup
    cc_map: dict[str, ComplexityScore] = {s.node_id: s for s in complexity_scores}

    results: list[ModuleHealth] = []

    for group_name, node_ids in groups.items():
        node_set = set(node_ids)

        # Complexity stats (only for FUNCTION/METHOD nodes)
        complexities = [cc_map[nid].cyclomatic for nid in node_ids if nid in cc_map]
        avg_cc = sum(complexities) / len(complexities) if complexities else 0.0
        max_cc = max(complexities) if complexities else 0

        # Coupling: cross-group CALLS/IMPORTS edges / total CALLS/IMPORTS edges
        total_edges = 0
        cross_edges = 0
        for nid in node_ids:
            for edge in graph.get_edges_from(nid):
                if edge.edge_type in (EdgeType.CALLS, EdgeType.IMPORTS):
                    total_edges += 1
                    if edge.target_id not in node_set:
                        cross_edges += 1
        coupling = cross_edges / total_edges if total_edges > 0 else 0.0

        # Cohesion: internal CALLS / possible internal edges
        internal = 0
        for nid in node_ids:
            for edge in graph.get_edges_from(nid):
                if edge.target_id in node_set and edge.edge_type == EdgeType.CALLS:
                    internal += 1
        n = len(node_ids)
        max_possible = n * (n - 1) if n > 1 else 1
        cohesion = internal / max_possible

        # God functions: CC > 10
        god_fns = sum(
            1 for nid in node_ids
            if nid in cc_map and cc_map[nid].cyclomatic > 10
        )

        # God classes: classes with > 20 HAS_METHOD edges
        god_cls = 0
        for nid in node_ids:
            nd = graph.get_node(nid)
            if nd and nd.label == NodeLabel.CLASS:
                method_count = sum(
                    1 for e in graph.get_edges_from(nid)
                    if e.edge_type == EdgeType.HAS_METHOD
                )
                if method_count > 20:
                    god_cls += 1

        # Module risk
        if max_cc > 20 or god_fns > 3:
            risk = "CRITICAL"
        elif max_cc > 10 or coupling > 0.8:
            risk = "HIGH"
        elif avg_cc > 5 or coupling > 0.6:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        results.append(ModuleHealth(
            group=group_name,
            node_count=len(node_ids),
            avg_complexity=round(avg_cc, 1),
            max_complexity=max_cc,
            coupling_ratio=round(coupling, 2),
            cohesion=round(cohesion, 3),
            god_functions=god_fns,
            god_classes=god_cls,
            risk=risk,
        ))

    return results


# ---------------------------------------------------------------------------
# Full health report
# ---------------------------------------------------------------------------

def build_health_report(
    graph: GraphProtocol,
    root_path: str = "",
) -> HealthReport:
    """Build a complete codebase health report."""
    scores = analyze_complexity(graph)
    modules = analyze_module_health(graph, scores, root_path)

    high_risk = sum(1 for s in scores if s.risk == "HIGH")
    critical_risk = sum(1 for s in scores if s.risk == "CRITICAL")
    avg_cc = sum(s.cyclomatic for s in scores) / len(scores) if scores else 0.0

    return HealthReport(
        total_functions=len(scores),
        avg_complexity=round(avg_cc, 1),
        high_risk_count=high_risk,
        critical_risk_count=critical_risk,
        functions=tuple(sorted(scores, key=lambda s: s.cyclomatic, reverse=True)),
        modules=tuple(sorted(modules, key=lambda m: m.avg_complexity, reverse=True)),
    )
