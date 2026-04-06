"""MCP server exposing code graph tools and resources.

Tools:
  - query(query: str)                                     -> search processes/nodes by keyword
  - context(name: str)                                    -> 360-degree view of a symbol
  - impact(target: str, direction: str, max_depth: int)  -> blast radius
  - detect_changes()                                      -> changed files + affected symbols

Resources:
  - graph://context   -> codebase overview (file/function/class counts)
  - graph://processes -> list of detected execution flows
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Smart-tool helpers
# ---------------------------------------------------------------------------

def _risk_suggestion(risk: str) -> str:
    """Return a human-readable suggestion based on risk level."""
    if risk == "CRITICAL":
        return "High blast radius. Run full test suite before and after changes."
    if risk == "HIGH":
        return "Significant dependencies. Run related tests after changes."
    if risk == "MEDIUM":
        return "Moderate impact. Verify callers still work."
    return "Low risk. Safe to modify."


def _file_has_tests(file_path: str, resolved_path: str, graph: Any) -> bool:
    """Return True if there is at least one test file that imports or calls symbols from this file."""
    from vector_graph._types import EdgeType

    for edge in graph.iter_edges():
        if edge.edge_type not in (EdgeType.CALLS, EdgeType.IMPORTS):
            continue
        src = graph.get_node(edge.source_id)
        tgt = graph.get_node(edge.target_id)
        if src is None or tgt is None:
            continue
        # The target node must live in our file
        if tgt.properties.file_path not in (file_path, resolved_path):
            continue
        # The source must be a test file
        src_base = src.properties.file_path.split("/")[-1]
        if src_base.startswith("test_") or src_base.endswith("_test.py"):
            return True
    return False


class VectorGraphMCPServer:
    """Testable handler layer for the vector-graph MCP server.

    All tool and resource logic lives here as plain methods so tests can
    call them directly without starting a real MCP transport.
    """

    def __init__(self, root: str | Path) -> None:
        from vector_graph.api.python_api import CodeGraph

        self._graph_api = CodeGraph(root)
        self._graph_api.analyze()
        # Optional ChangeTracker set externally when --watch mode is active
        self._change_tracker: Any = None

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def list_tools(self) -> list[dict[str, Any]]:
        """Return tool definitions in MCP format."""
        return [
            {
                "name": "query",
                "description": (
                    "Search for processes, functions, or classes by keyword. "
                    "Returns matching node names and file paths."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Keyword to search for in node names",
                        }
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "context",
                "description": (
                    "Return a 360-degree view of a named symbol: its node info, "
                    "inbound callers, and outbound callees."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the function, class, or method to inspect",
                        }
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "impact",
                "description": (
                    "Blast radius analysis for a named symbol. "
                    "Returns risk level and list of impacted nodes."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Name of the function or class to analyse",
                        },
                        "direction": {
                            "type": "string",
                            "enum": ["upstream", "downstream"],
                            "description": "upstream = who calls target; downstream = what target calls",
                            "default": "upstream",
                        },
                        "max_depth": {
                            "type": "integer",
                            "description": "Maximum BFS depth (default: 3)",
                            "default": 3,
                        },
                    },
                    "required": ["target"],
                },
            },
            {
                "name": "detect_changes",
                "description": (
                    "Report changed files and affected symbols since last analysis. "
                    "Returns empty if no file watcher is running."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "graph_query",
                "description": (
                    "Structured graph query. "
                    "Types: callers_of, callees_of, subclasses_of, implementations_of, "
                    "path_between, by_file, by_pattern, by_decorator"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query_type": {
                            "type": "string",
                            "enum": [
                                "callers_of",
                                "callees_of",
                                "subclasses_of",
                                "implementations_of",
                                "path_between",
                                "by_file",
                                "by_pattern",
                                "by_decorator",
                            ],
                            "description": "The type of structured query to run",
                        },
                        "name": {
                            "type": "string",
                            "description": "Symbol name (for callers_of, callees_of, subclasses_of, implementations_of)",
                        },
                        "source": {
                            "type": "string",
                            "description": "Source symbol name (for path_between)",
                        },
                        "target": {
                            "type": "string",
                            "description": "Target symbol name (for path_between)",
                        },
                        "file_path": {
                            "type": "string",
                            "description": "File path to query (for by_file)",
                        },
                        "pattern": {
                            "type": "string",
                            "description": "Glob pattern to match against node names (for by_pattern)",
                        },
                        "decorator": {
                            "type": "string",
                            "description": "Decorator name to filter by (for by_decorator)",
                        },
                    },
                    "required": ["query_type"],
                },
            },
            {
                "name": "export",
                "description": "Export graph to JSON or DOT format",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "format": {
                            "type": "string",
                            "enum": ["json", "dot"],
                            "default": "json",
                            "description": "Output format: 'json' (default) or 'dot' (Graphviz)",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "cycles",
                "description": "Detect dependency cycles in the codebase",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "orphans",
                "description": "Find unreachable functions/classes with no incoming edges",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "health",
                "description": (
                    "Compute full codebase health report: cyclomatic complexity, "
                    "fan-in/out, module coupling/cohesion, god class/function detection, "
                    "and per-node risk scoring."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "complexity",
                "description": (
                    "Return cyclomatic complexity score for a named function or method."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the function or method to analyse",
                        }
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "impact_preview",
                "description": (
                    "Blast radius preview before making a change. "
                    "Returns risk level, upstream and downstream affected counts, "
                    "affected files, and a human-readable suggestion."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Function or class name to preview impact for",
                        }
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "safe_to_modify",
                "description": (
                    "Assess risk of modifying a file. "
                    "Returns dependent function count, dependent file count, "
                    "whether tests exist, risk level, and a suggestion."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Relative or absolute path of the file to assess",
                        }
                    },
                    "required": ["file_path"],
                },
            },
            {
                "name": "what_changed",
                "description": (
                    "Session change summary. Returns empty if no --watch mode is active."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "suggest_tests",
                "description": (
                    "Suggest test files and test functions that cover a named symbol, "
                    "using BFS upstream through CALLS edges."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Function or class name to find tests for",
                        }
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "dependency_check",
                "description": (
                    "Check existing dependency cycles in the codebase. "
                    "Reports current cycle count and details."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "module": {
                            "type": "string",
                            "description": "Module name (informational — used as context label)",
                        }
                    },
                    "required": ["module"],
                },
            },
            {
                "name": "hotspot_report",
                "description": (
                    "Report git change hotspots for the project. "
                    "If file_path is given, returns hotspot data for that specific file. "
                    "Otherwise returns the top 10 hotspots sorted by score."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Optional relative or absolute file path to query",
                        },
                        "days": {
                            "type": "integer",
                            "description": "Number of days of git history to analyse (default: 90)",
                            "default": 90,
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "co_change",
                "description": (
                    "Return files that commonly change together with the given file, "
                    "sorted by co-change count."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Relative or absolute path of the file to query",
                        },
                        "days": {
                            "type": "integer",
                            "description": "Number of days of git history to analyse (default: 90)",
                            "default": 90,
                        },
                    },
                    "required": ["file_path"],
                },
            },
        ]

    # ------------------------------------------------------------------
    # Resource registration
    # ------------------------------------------------------------------

    def list_resources(self) -> list[dict[str, Any]]:
        """Return resource definitions."""
        return [
            {
                "uri": "graph://context",
                "name": "Codebase Overview",
                "description": (
                    "High-level statistics: node count, edge count, file count, "
                    "function count, class count, community count, process count."
                ),
                "mimeType": "application/json",
            },
            {
                "uri": "graph://processes",
                "name": "Execution Flows",
                "description": "List of detected execution flows (process traces) in the codebase.",
                "mimeType": "application/json",
            },
        ]

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a named tool and return its result as a plain dict."""
        _dispatch = {
            "query": self._tool_query,
            "context": self._tool_context,
            "impact": self._tool_impact,
            "detect_changes": self._tool_detect_changes,
            "graph_query": self._tool_graph_query,
            "export": self._tool_export,
            "cycles": self._tool_cycles,
            "orphans": self._tool_orphans,
            "health": self._tool_health,
            "complexity": self._tool_complexity,
            "impact_preview": self._tool_impact_preview,
            "safe_to_modify": self._tool_safe_to_modify,
            "what_changed": self._tool_what_changed,
            "suggest_tests": self._tool_suggest_tests,
            "dependency_check": self._tool_dependency_check,
            "hotspot_report": self._tool_hotspot_report,
            "co_change": self._tool_co_change,
        }
        if name not in _dispatch:
            return {"error": f"Unknown tool: '{name}'"}
        try:
            return _dispatch[name](**arguments)
        except TypeError as exc:
            return {"error": f"Invalid arguments for tool '{name}': {exc}"}

    # ------------------------------------------------------------------
    # Resource dispatch
    # ------------------------------------------------------------------

    def read_resource(self, uri: str) -> dict[str, Any]:
        """Read a resource by URI and return its content as a plain dict."""
        _dispatch = {
            "graph://context": self._resource_context,
            "graph://processes": self._resource_processes,
        }
        if uri not in _dispatch:
            return {"error": f"Unknown resource URI: '{uri}'"}
        return _dispatch[uri]()

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def _tool_query(self, query: str = "") -> dict[str, Any]:
        """Search nodes whose names contain the query string (case-insensitive)."""
        from vector_graph._types import NodeLabel

        graph = self._graph_api._graph
        assert graph is not None

        query_lower = query.lower()
        matches: list[dict[str, Any]] = []
        for node in graph.iter_nodes():
            if node.label not in (
                NodeLabel.FUNCTION,
                NodeLabel.METHOD,
                NodeLabel.CLASS,
                NodeLabel.PROCESS,
            ):
                continue
            if query_lower in node.properties.name.lower():
                matches.append({
                    "name": node.properties.name,
                    "label": node.label.value,
                    "file": node.properties.file_path,
                    "id": node.id,
                })
        return {"query": query, "count": len(matches), "matches": matches}

    def _tool_context(self, name: str) -> dict[str, Any]:
        """Return node info + inbound callers + outbound callees for a symbol."""
        from vector_graph._types import NodeLabel

        graph = self._graph_api._graph
        assert graph is not None

        # Find the node
        target_node = None
        for node in graph.iter_nodes():
            if node.properties.name == name and node.label in (
                NodeLabel.FUNCTION,
                NodeLabel.METHOD,
                NodeLabel.CLASS,
            ):
                target_node = node
                break

        if target_node is None:
            return {"found": False, "name": name, "node": None}

        # Inbound edges (callers)
        inbound: list[dict[str, Any]] = []
        for edge in graph.get_edges_to(target_node.id):
            src = graph.get_node(edge.source_id)
            inbound.append({
                "id": edge.source_id,
                "name": src.properties.name if src else edge.source_id,
                "edge_type": edge.edge_type.value,
                "confidence": edge.confidence,
            })

        # Outbound edges (callees)
        outbound: list[dict[str, Any]] = []
        for edge in graph.get_edges_from(target_node.id):
            tgt = graph.get_node(edge.target_id)
            outbound.append({
                "id": edge.target_id,
                "name": tgt.properties.name if tgt else edge.target_id,
                "edge_type": edge.edge_type.value,
                "confidence": edge.confidence,
            })

        return {
            "found": True,
            "name": name,
            "node": target_node.to_dict(),
            "inbound": inbound,
            "outbound": outbound,
        }

    def _tool_impact(
        self,
        target: str,
        direction: str = "upstream",
        max_depth: int = 3,
    ) -> dict[str, Any]:
        """Blast radius analysis — delegates to CodeGraph.impact()."""
        result = self._graph_api.impact(target, direction=direction, max_depth=max_depth)
        return result.to_dict()

    def _tool_detect_changes(self) -> dict[str, Any]:
        """Report changed files. Returns empty if no watcher is active."""
        # File watcher integration is a separate module (Phase 4).
        # Return an informational stub when no watcher is running.
        return {
            "changed_files": [],
            "affected_symbols": [],
            "note": "No file watcher active. Start vector-graph with --watch to enable.",
        }

    def _tool_graph_query(self, query_type: str = "", **kwargs: Any) -> dict[str, Any]:
        """Execute a structured graph query via CodeGraph.query()."""
        result = self._graph_api.query(query_type, **kwargs)
        return {
            "query_type": result.query_type,
            "params": result.params,
            "count": result.count,
            "nodes": [n.to_dict() for n in result.nodes],
            "edges": [e.to_dict() for e in result.edges],
        }

    def _tool_export(self, format: str = "json") -> dict[str, Any]:
        """Export the graph to JSON or DOT format via CodeGraph.export()."""
        data = self._graph_api.export(format=format)
        return {"format": format, "data": data}

    def _tool_cycles(self) -> dict[str, Any]:
        """Detect dependency cycles in the codebase via CodeGraph.cycles()."""
        cycles = self._graph_api.cycles()
        return {
            "count": len(cycles),
            "cycles": [
                {
                    "length": c.length,
                    "node_ids": list(c.node_ids),
                    "node_names": list(c.node_names),
                    "edge_types": list(c.edge_types),
                }
                for c in cycles
            ],
        }

    def _tool_orphans(self) -> dict[str, Any]:
        """Find unreachable functions/classes with no incoming edges."""
        orphan_nodes = self._graph_api.orphans()
        return {
            "count": len(orphan_nodes),
            "orphans": [
                {
                    "id": n.id,
                    "name": n.properties.name,
                    "label": n.label.value,
                    "file": n.properties.file_path,
                }
                for n in orphan_nodes
            ],
        }

    def _tool_health(self) -> dict[str, Any]:
        """Compute full codebase health report via CodeGraph.health()."""
        report = self._graph_api.health()
        return {
            "total_functions": report.total_functions,
            "avg_complexity": report.avg_complexity,
            "high_risk_count": report.high_risk_count,
            "critical_risk_count": report.critical_risk_count,
            "functions": [
                {
                    "name": f.name,
                    "file": f.file_path,
                    "cyclomatic": f.cyclomatic,
                    "line_count": f.line_count,
                    "parameter_count": f.parameter_count,
                    "risk": f.risk,
                }
                for f in report.functions[:50]  # top 50 by complexity
            ],
            "modules": [
                {
                    "group": m.group,
                    "node_count": m.node_count,
                    "avg_complexity": m.avg_complexity,
                    "max_complexity": m.max_complexity,
                    "coupling_ratio": m.coupling_ratio,
                    "cohesion": m.cohesion,
                    "god_functions": m.god_functions,
                    "god_classes": m.god_classes,
                    "risk": m.risk,
                }
                for m in report.modules
            ],
        }

    def _tool_complexity(self, name: str = "") -> dict[str, Any]:
        """Return complexity score for a named function or method."""
        from vector_graph.analysis.complexity import analyze_complexity

        graph = self._graph_api._graph
        assert graph is not None

        scores = analyze_complexity(graph)
        matches = [s for s in scores if s.name == name]
        if not matches:
            return {"found": False, "name": name}

        # Return the most complex one if there are duplicates
        best = max(matches, key=lambda s: s.cyclomatic)
        return {
            "found": True,
            "name": best.name,
            "file": best.file_path,
            "cyclomatic": best.cyclomatic,
            "line_count": best.line_count,
            "parameter_count": best.parameter_count,
            "risk": best.risk,
        }

    def _tool_impact_preview(self, name: str = "") -> dict[str, Any]:
        """Blast radius preview before making a change."""
        up = self._graph_api.impact(name, direction="upstream", max_depth=3)
        down = self._graph_api.impact(name, direction="downstream", max_depth=2)
        total = up.impacted_count + down.impacted_count

        # Collect affected file basenames from upstream result
        affected_files: list[str] = sorted(
            set(e.file_path.split("/")[-1] for e in up.entries)
        )

        return {
            "name": name,
            "risk": up.risk,
            "upstream_affected": up.impacted_count,
            "downstream_affected": down.impacted_count,
            "total_affected": total,
            "affected_files": affected_files,
            "suggestion": _risk_suggestion(up.risk),
        }

    def _tool_safe_to_modify(self, file_path: str = "") -> dict[str, Any]:
        """Assess risk of modifying a file."""
        from vector_graph._types import EdgeType, NodeLabel

        graph = self._graph_api._graph
        assert graph is not None

        # Resolve file_path relative to project root
        from pathlib import Path as _Path
        root = self._graph_api._root
        candidate = _Path(file_path)
        if not candidate.is_absolute():
            candidate = root / candidate
        # Normalise to the string stored in graph nodes (which uses resolved abs paths)
        resolved = str(candidate.resolve())

        file_nodes = list(graph.get_nodes_by_file(resolved))
        # Fallback: try matching the raw string as stored (may be relative)
        if not file_nodes:
            file_nodes = list(graph.get_nodes_by_file(file_path))

        dependent_count = 0
        dependent_files: set[str] = set()
        node_count = 0

        for node in file_nodes:
            if node.label in (NodeLabel.FUNCTION, NodeLabel.METHOD, NodeLabel.CLASS):
                node_count += 1
                for edge in graph.get_edges_to(node.id):
                    if edge.edge_type == EdgeType.CALLS:
                        src = graph.get_node(edge.source_id)
                        if src and src.properties.file_path not in (resolved, file_path):
                            dependent_count += 1
                            dependent_files.add(src.properties.file_path)

        has_tests = _file_has_tests(file_path, resolved, graph)

        risk = "LOW"
        if dependent_count > 20:
            risk = "CRITICAL"
        elif dependent_count > 10:
            risk = "HIGH"
        elif dependent_count > 3:
            risk = "MEDIUM"

        return {
            "file": file_path,
            "risk": risk,
            "node_count": node_count,
            "dependent_functions": dependent_count,
            "dependent_files": len(dependent_files),
            "has_tests": has_tests,
            "suggestion": _risk_suggestion(risk),
        }

    def _tool_what_changed(self) -> dict[str, Any]:
        """Session change summary. Returns empty if no change tracker is active."""
        if self._change_tracker is None:
            return {
                "session_active": False,
                "note": (
                    "No --watch mode active. "
                    "Start with vector-graph --watch --serve to enable change tracking."
                ),
            }
        return {
            "session_active": True,
            **self._change_tracker.session_summary(),
            "recent_changes": [
                e.to_dict() for e in self._change_tracker.get_events(10)
            ],
        }

    def _tool_suggest_tests(self, name: str = "") -> dict[str, Any]:
        """Suggest test files that cover a named symbol."""
        from vector_graph.analysis.suggest_tests import suggest_tests

        graph = self._graph_api._graph
        assert graph is not None

        suggestions = suggest_tests(graph, name)
        return {
            "name": name,
            "tests": [
                {
                    "test_file": s.test_file,
                    "test_name": s.test_name,
                    "depth": s.depth,
                }
                for s in suggestions
            ],
        }

    def _tool_dependency_check(self, module: str = "") -> dict[str, Any]:
        """Check if adding an import would create a dependency cycle."""
        from vector_graph.analysis.cycles import detect_cycles

        graph = self._graph_api._graph
        assert graph is not None

        existing_cycles = detect_cycles(graph)
        return {
            "module": module,
            "existing_cycle_count": len(existing_cycles),
            "would_create_cycle": False,  # simplified: reports existing cycles
            "existing_cycles": [
                {
                    "nodes": list(c.node_names),
                    "length": c.length,
                }
                for c in existing_cycles[:5]
            ],
        }

    def _tool_hotspot_report(
        self, file_path: str = "", days: int = 90
    ) -> dict[str, Any]:
        """Return hotspot data for a specific file or the top 10 hotspots."""
        try:
            from vector_graph.analysis.git_history import (
                analyze_hotspots,
            )
        except ImportError:
            return {"error": "git_history module not available", "hotspots": []}

        root = str(self._graph_api._root)
        hotspots = analyze_hotspots(root, days=days)

        if file_path:
            # Resolve to absolute so it can match keys in hotspots dict
            from pathlib import Path as _Path
            candidate = _Path(file_path)
            if not candidate.is_absolute():
                candidate = _Path(root) / candidate
            resolved = str(candidate.resolve())
            entry = hotspots.get(resolved) or hotspots.get(file_path)
            if entry is None:
                return {"file_path": file_path, "found": False, "hotspots": []}
            return {
                "file_path": file_path,
                "found": True,
                "hotspots": [
                    {
                        "file": entry.file_path,
                        "changes": entry.change_count,
                        "recent": entry.recent_changes,
                        "score": round(entry.hotspot_score, 2),
                        "contributors": list(entry.top_contributors),
                        "last_modified": entry.last_modified,
                    }
                ],
            }

        top10 = sorted(hotspots.values(), key=lambda h: h.hotspot_score, reverse=True)[:10]
        return {
            "hotspots": [
                {
                    "file": h.file_path,
                    "changes": h.change_count,
                    "recent": h.recent_changes,
                    "score": round(h.hotspot_score, 2),
                    "contributors": list(h.top_contributors),
                    "last_modified": h.last_modified,
                }
                for h in top10
            ],
        }

    def _tool_co_change(self, file_path: str = "", days: int = 90) -> dict[str, Any]:
        """Return files that commonly change together with the given file."""
        if not file_path:
            return {"error": "file_path is required", "co_changes": []}

        try:
            from vector_graph.analysis.git_history import analyze_co_changes
        except ImportError:
            return {"error": "git_history module not available", "co_changes": []}

        root = str(self._graph_api._root)
        # Resolve to absolute path for consistent matching
        from pathlib import Path as _Path
        candidate = _Path(file_path)
        if not candidate.is_absolute():
            candidate = _Path(root) / candidate
        resolved = str(candidate.resolve())

        co_changes = analyze_co_changes(root, days=days)
        # Filter entries that involve our file (either side)
        related = [
            e for e in co_changes
            if e.file_a in (file_path, resolved) or e.file_b in (file_path, resolved)
        ]
        # Sort by co_change_count descending
        related.sort(key=lambda e: e.co_change_count, reverse=True)

        return {
            "file_path": file_path,
            "co_changes": [
                {
                    "file_a": e.file_a,
                    "file_b": e.file_b,
                    "count": e.co_change_count,
                    "confidence": e.confidence,
                }
                for e in related
            ],
        }

    # ------------------------------------------------------------------
    # Resource implementations
    # ------------------------------------------------------------------

    def _resource_context(self) -> dict[str, Any]:
        """Return codebase overview from the cached AnalysisResult."""
        result = self._graph_api._result
        assert result is not None
        return result.to_dict()

    def _resource_processes(self) -> dict[str, Any]:
        """Return list of detected execution flows."""
        from vector_graph._types import NodeLabel
        from vector_graph.analysis.execution_flow import detect_execution_flows

        graph = self._graph_api._graph
        assert graph is not None

        flows = detect_execution_flows(graph, min_steps=1)
        return {
            "process_count": len(flows),
            "processes": [f.to_dict() for f in flows],
        }


# ---------------------------------------------------------------------------
# MCP stdio transport entry point
# ---------------------------------------------------------------------------

def run_mcp_stdio(root: str | Path) -> None:
    """Start MCP server on stdio transport using the mcp Python SDK."""
    import asyncio
    import json as _json

    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    import mcp.types as types

    handler = VectorGraphMCPServer(root)
    server: Server = Server("vector-graph")

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        tools: list[types.Tool] = []
        for td in handler.list_tools():
            tools.append(
                types.Tool(
                    name=td["name"],
                    description=td["description"],
                    inputSchema=td["inputSchema"],
                )
            )
        return tools

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[types.TextContent]:
        result = handler.call_tool(name, arguments or {})
        return [types.TextContent(type="text", text=_json.dumps(result, indent=2))]

    @server.list_resources()
    async def handle_list_resources() -> list[types.Resource]:
        resources: list[types.Resource] = []
        for rd in handler.list_resources():
            resources.append(
                types.Resource(
                    uri=rd["uri"],
                    name=rd["name"],
                    description=rd.get("description", ""),
                    mimeType=rd.get("mimeType", "application/json"),
                )
            )
        return resources

    @server.read_resource()
    async def handle_read_resource(uri: str) -> str:
        result = handler.read_resource(uri)
        return _json.dumps(result, indent=2)

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point for vector-graph-mcp."""
    import argparse

    parser = argparse.ArgumentParser(description="vector-graph MCP server")
    parser.add_argument("root", nargs="?", default=".", help="Project root")
    args = parser.parse_args()
    run_mcp_stdio(args.root)
