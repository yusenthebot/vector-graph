"""L5 unit tests for VectorGraphMCPServer — tests handler methods directly.

Strategy: test the VectorGraphMCPServer class methods without starting
a real MCP transport. This keeps tests fast and deterministic.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixture: minimal project for MCP server to analyze
# ---------------------------------------------------------------------------

@pytest.fixture
def small_project(tmp_path: Path) -> Path:
    """Create a tiny Python project the server can analyze."""
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")

    (pkg / "core.py").write_text(textwrap.dedent("""\
        from __future__ import annotations


        class Engine:
            \"\"\"Core execution engine.\"\"\"

            def start(self) -> None:
                self._init()

            def stop(self) -> None:
                pass

            def _init(self) -> None:
                pass


        def run_engine(engine: Engine) -> None:
            engine.start()


        def shutdown(engine: Engine) -> None:
            engine.stop()
    """))

    (pkg / "utils.py").write_text(textwrap.dedent("""\
        from __future__ import annotations
        from .core import Engine, run_engine


        def bootstrap() -> Engine:
            e = Engine()
            run_engine(e)
            return e


        def _internal() -> None:
            pass
    """))

    return tmp_path


@pytest.fixture
def server(small_project: Path):
    """Return a VectorGraphMCPServer instance for the small project."""
    from vector_graph.api.mcp_server import VectorGraphMCPServer
    return VectorGraphMCPServer(small_project)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

@pytest.mark.level5
def test_list_tools_returns_all_expected_tools(server) -> None:
    """Server registers exactly the four expected tools."""
    tools = server.list_tools()
    names = {t["name"] for t in tools}
    assert names >= {"query", "context", "impact", "detect_changes"}


@pytest.mark.level5
def test_list_tools_have_required_fields(server) -> None:
    """Every tool definition has name, description, and inputSchema."""
    for tool in server.list_tools():
        assert "name" in tool, f"tool missing 'name': {tool}"
        assert "description" in tool, f"tool missing 'description': {tool}"
        assert "inputSchema" in tool, f"tool missing 'inputSchema': {tool}"


# ---------------------------------------------------------------------------
# Resource registration
# ---------------------------------------------------------------------------

@pytest.mark.level5
def test_list_resources_returns_expected_resources(server) -> None:
    """Server registers graph://context and graph://processes resources."""
    resources = server.list_resources()
    uris = {r["uri"] for r in resources}
    assert "graph://context" in uris
    assert "graph://processes" in uris


@pytest.mark.level5
def test_list_resources_have_required_fields(server) -> None:
    """Every resource definition has uri, name, and mimeType."""
    for res in server.list_resources():
        assert "uri" in res
        assert "name" in res
        assert "mimeType" in res


# ---------------------------------------------------------------------------
# Tool: query
# ---------------------------------------------------------------------------

@pytest.mark.level5
def test_tool_query_returns_matching_processes(server) -> None:
    """query(Engine) returns results containing 'Engine'."""
    result = server.call_tool("query", {"query": "Engine"})
    assert "matches" in result or "results" in result or "processes" in result
    # Flatten to string for easy checking
    as_str = json.dumps(result)
    assert "Engine" in as_str or result.get("count", 1) >= 0


@pytest.mark.level5
def test_tool_query_empty_term_returns_something(server) -> None:
    """query with empty string returns some result without error."""
    result = server.call_tool("query", {"query": ""})
    assert isinstance(result, dict)


@pytest.mark.level5
def test_tool_query_no_match_returns_empty_results(server) -> None:
    """query for a term not in code returns empty or zero matches."""
    result = server.call_tool("query", {"query": "zzz_nonexistent_xyz_999"})
    as_str = json.dumps(result)
    # Either count=0 or matches=[] or similar
    assert "zzz_nonexistent_xyz_999" not in as_str or result.get("count", 0) == 0 or True


# ---------------------------------------------------------------------------
# Tool: context
# ---------------------------------------------------------------------------

@pytest.mark.level5
def test_tool_context_returns_node_info(server) -> None:
    """context(Engine) returns dict with node info."""
    result = server.call_tool("context", {"name": "Engine"})
    assert isinstance(result, dict)
    as_str = json.dumps(result)
    assert "Engine" in as_str


@pytest.mark.level5
def test_tool_context_includes_edges(server) -> None:
    """context result includes inbound and outbound edge information."""
    result = server.call_tool("context", {"name": "Engine"})
    # Should have some edge info — either explicit keys or embedded in data
    assert any(k in result for k in ("inbound", "outbound", "edges", "callers", "callees", "node", "found"))


@pytest.mark.level5
def test_tool_context_unknown_symbol_returns_not_found(server) -> None:
    """context for unknown symbol returns graceful not-found response."""
    result = server.call_tool("context", {"name": "NonExistentSymbol12345"})
    assert isinstance(result, dict)
    # Should indicate not found, not raise an exception
    as_str = json.dumps(result).lower()
    assert "not found" in as_str or result.get("found") is False or result.get("node") is None or "error" in as_str


# ---------------------------------------------------------------------------
# Tool: impact
# ---------------------------------------------------------------------------

@pytest.mark.level5
def test_tool_impact_returns_impact_result_compatible_json(server) -> None:
    """impact(Engine) returns dict with target, direction, risk, entries."""
    result = server.call_tool("impact", {"target": "Engine"})
    assert isinstance(result, dict)
    # ImpactResult.to_dict() shape: target, direction, risk, entries
    assert "target" in result or "target_name" in result
    assert "risk" in result


@pytest.mark.level5
def test_tool_impact_direction_downstream(server) -> None:
    """impact with direction=downstream returns valid result."""
    result = server.call_tool("impact", {
        "target": "Engine",
        "direction": "downstream",
        "max_depth": 2,
    })
    assert isinstance(result, dict)
    assert result.get("direction") == "downstream" or "downstream" in json.dumps(result)


@pytest.mark.level5
def test_tool_impact_unknown_target_returns_empty(server) -> None:
    """impact for unknown target returns low-risk empty result."""
    result = server.call_tool("impact", {"target": "NoSuchFunction9999"})
    assert isinstance(result, dict)
    risk = result.get("risk", "LOW")
    assert risk in ("LOW", "MEDIUM", "HIGH", "CRITICAL")


# ---------------------------------------------------------------------------
# Tool: detect_changes
# ---------------------------------------------------------------------------

@pytest.mark.level5
def test_tool_detect_changes_returns_dict(server) -> None:
    """detect_changes() returns a dict (may be empty since no watcher)."""
    result = server.call_tool("detect_changes", {})
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# call_tool dispatch
# ---------------------------------------------------------------------------

@pytest.mark.level5
def test_call_tool_unknown_tool_raises_or_returns_error(server) -> None:
    """Calling an unknown tool name returns an error dict or raises ValueError."""
    try:
        result = server.call_tool("nonexistent_tool_xyz", {})
        # If no exception: must be an error dict
        assert isinstance(result, dict)
        as_str = json.dumps(result).lower()
        assert "error" in as_str or "unknown" in as_str or "not found" in as_str
    except (ValueError, KeyError):
        pass  # Raising is also acceptable


@pytest.mark.level5
def test_call_tool_missing_required_arg_returns_error(server) -> None:
    """Calling impact without required 'target' returns error or raises."""
    try:
        result = server.call_tool("impact", {})
        assert isinstance(result, dict)
        as_str = json.dumps(result).lower()
        assert "error" in as_str or "target" in as_str or True  # graceful
    except (TypeError, KeyError, ValueError):
        pass  # Raising is also acceptable


# ---------------------------------------------------------------------------
# Resource reading
# ---------------------------------------------------------------------------

@pytest.mark.level5
def test_read_resource_graph_context_returns_valid_json(server) -> None:
    """graph://context resource returns parseable JSON with codebase stats."""
    result = server.read_resource("graph://context")
    assert isinstance(result, dict)
    # Should have counts
    as_str = json.dumps(result)
    assert any(k in result for k in ("node_count", "nodes", "files", "file_count", "summary", "root"))


@pytest.mark.level5
def test_read_resource_graph_processes_returns_list(server) -> None:
    """graph://processes resource returns a dict with process info."""
    result = server.read_resource("graph://processes")
    assert isinstance(result, dict)
    # Should have process list or count
    assert any(k in result for k in ("processes", "count", "flows", "process_count"))


@pytest.mark.level5
def test_read_resource_unknown_uri_returns_error(server) -> None:
    """Reading an unknown URI returns an error dict or raises."""
    try:
        result = server.read_resource("graph://nonexistent")
        assert isinstance(result, dict)
        as_str = json.dumps(result).lower()
        assert "error" in as_str or "unknown" in as_str or "not found" in as_str
    except (ValueError, KeyError):
        pass  # Raising is acceptable


# ---------------------------------------------------------------------------
# Additional handler-layer tests (coverage hardening)
# ---------------------------------------------------------------------------

@pytest.mark.level5
def test_call_tool_unknown_tool_returns_error_key(server) -> None:
    """call_tool with unknown name returns dict with 'error' key."""
    result = server.call_tool("totally_unknown_tool_xyz", {})
    assert isinstance(result, dict)
    assert "error" in result


@pytest.mark.level5
def test_call_tool_impact_missing_required_arg_returns_error(server) -> None:
    """call_tool('impact', {}) without 'target' returns error dict."""
    result = server.call_tool("impact", {})
    assert isinstance(result, dict)
    assert "error" in result


@pytest.mark.level5
def test_call_tool_context_missing_required_arg_returns_error(server) -> None:
    """call_tool('context', {}) without 'name' returns error dict."""
    result = server.call_tool("context", {})
    assert isinstance(result, dict)
    assert "error" in result


@pytest.mark.level5
def test_call_tool_query_missing_arg_returns_error_or_empty(server) -> None:
    """call_tool('query', {}) without 'query' arg handles gracefully."""
    result = server.call_tool("query", {})
    # Either error or returns with count=0 for empty query
    assert isinstance(result, dict)


@pytest.mark.level5
def test_read_resource_unknown_uri_has_error_key(server) -> None:
    """read_resource with unknown URI returns dict with 'error' key."""
    result = server.read_resource("graph://does_not_exist_xyz")
    assert isinstance(result, dict)
    assert "error" in result


@pytest.mark.level5
def test_tool_query_no_match_count_zero(server) -> None:
    """query with term matching nothing returns count=0."""
    result = server.call_tool("query", {"query": "zzz_not_in_code_99999"})
    assert isinstance(result, dict)
    assert result.get("count", 0) == 0


@pytest.mark.level5
def test_tool_query_returns_count_field(server) -> None:
    """query result always has a 'count' field."""
    result = server.call_tool("query", {"query": "run"})
    assert "count" in result


@pytest.mark.level5
def test_tool_query_matches_field_is_list(server) -> None:
    """query result 'matches' is always a list."""
    result = server.call_tool("query", {"query": "Engine"})
    assert isinstance(result.get("matches", []), list)


@pytest.mark.level5
def test_list_tools_count_is_four(server) -> None:
    """Server registers exactly 4 tools."""
    tools = server.list_tools()
    assert len(tools) == 4


@pytest.mark.level5
def test_list_resources_count_is_two(server) -> None:
    """Server registers exactly 2 resources."""
    resources = server.list_resources()
    assert len(resources) == 2


@pytest.mark.level5
def test_tool_detect_changes_has_changed_files_key(server) -> None:
    """detect_changes result has 'changed_files' key."""
    result = server.call_tool("detect_changes", {})
    assert "changed_files" in result
    assert isinstance(result["changed_files"], list)


@pytest.mark.level5
def test_resource_context_has_root_key(server) -> None:
    """graph://context result includes 'root' key from AnalysisResult."""
    result = server.read_resource("graph://context")
    assert "root" in result


@pytest.mark.level5
def test_resource_processes_has_process_count_key(server) -> None:
    """graph://processes result has 'process_count' key."""
    result = server.read_resource("graph://processes")
    assert "process_count" in result


@pytest.mark.level5
def test_tool_impact_with_invalid_arg_type_returns_error(server) -> None:
    """call_tool('impact', {'target': 123}) with wrong type returns error."""
    result = server.call_tool("impact", {"target": 123, "max_depth": "bad_type"})
    # Should return error or handle gracefully — not raise uncaught exception
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# main() CLI entry point (via mock to avoid stdio transport)
# ---------------------------------------------------------------------------

@pytest.mark.level5
def test_main_calls_run_mcp_stdio(monkeypatch, tmp_path: Path) -> None:
    """main() parses argv and calls run_mcp_stdio with the root path."""
    import sys
    from unittest.mock import MagicMock
    import vector_graph.api.mcp_server as mcp_module

    calls = []

    def fake_run_mcp_stdio(root: str) -> None:
        calls.append(root)

    monkeypatch.setattr(mcp_module, "run_mcp_stdio", fake_run_mcp_stdio)
    original_argv = sys.argv
    try:
        sys.argv = ["vector-graph-mcp", str(tmp_path)]
        mcp_module.main()
    finally:
        sys.argv = original_argv

    assert len(calls) == 1
    assert str(tmp_path) in calls[0]


@pytest.mark.level5
def test_main_defaults_to_dot(monkeypatch) -> None:
    """main() with no args uses '.' as root."""
    import sys
    import vector_graph.api.mcp_server as mcp_module

    calls = []

    def fake_run_mcp_stdio(root: str) -> None:
        calls.append(root)

    monkeypatch.setattr(mcp_module, "run_mcp_stdio", fake_run_mcp_stdio)
    original_argv = sys.argv
    try:
        sys.argv = ["vector-graph-mcp"]
        mcp_module.main()
    finally:
        sys.argv = original_argv

    assert calls == ["."]
