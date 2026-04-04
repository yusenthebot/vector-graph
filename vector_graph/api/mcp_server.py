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


class VectorGraphMCPServer:
    """Testable handler layer for the vector-graph MCP server.

    All tool and resource logic lives here as plain methods so tests can
    call them directly without starting a real MCP transport.
    """

    def __init__(self, root: str | Path) -> None:
        from vector_graph.api.python_api import CodeGraph

        self._graph_api = CodeGraph(root)
        self._graph_api.analyze()

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
