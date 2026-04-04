"""Tests for web server API data functions."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from vector_graph._types import (
    Edge,
    EdgeType,
    GraphNode,
    NodeLabel,
    NodeProperties,
)
from vector_graph.graph.knowledge_graph import KnowledgeGraph
from vector_graph.api.web_server import (
    build_context_response,
    build_graph_data,
    build_search_results,
    build_source_response,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def small_graph() -> KnowledgeGraph:
    g = KnowledgeGraph()
    g.add_node(GraphNode(id="f1", label=NodeLabel.FUNCTION, properties=NodeProperties(
        name="main", file_path="/src/app.py", start_line=1, end_line=10, return_type="None",
        parameters=("args",), decorators=("entry_point",),
    )))
    g.add_node(GraphNode(id="f2", label=NodeLabel.FUNCTION, properties=NodeProperties(
        name="helper", file_path="/src/utils.py", start_line=5, end_line=15,
    )))
    g.add_node(GraphNode(id="c1", label=NodeLabel.CLASS, properties=NodeProperties(
        name="Engine", file_path="/src/engine.py", start_line=1, end_line=50, bases=("Base",),
    )))
    g.add_edge(Edge(id="e1", source_id="f1", target_id="f2", edge_type=EdgeType.CALLS, confidence=0.9))
    g.add_edge(Edge(id="e2", source_id="f1", target_id="c1", edge_type=EdgeType.CALLS, confidence=0.8))
    return g


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(textwrap.dedent("""\
        def main():
            x = 1
            y = 2
            return x + y

        def other():
            pass
    """))
    return tmp_path


# ---------------------------------------------------------------------------
# build_graph_data
# ---------------------------------------------------------------------------

@pytest.mark.level5
class TestBuildGraphData:
    def test_returns_nodes_and_links(self, small_graph: KnowledgeGraph) -> None:
        data = build_graph_data(small_graph)
        assert "nodes" in data
        assert "links" in data

    def test_node_has_required_fields(self, small_graph: KnowledgeGraph) -> None:
        data = build_graph_data(small_graph)
        node = next(n for n in data["nodes"] if n["name"] == "main")
        assert node["id"] == "f1"
        assert node["label"] == "Function"
        assert node["file"] == "/src/app.py"
        assert node["line"] == 1

    def test_node_includes_optional_fields(self, small_graph: KnowledgeGraph) -> None:
        data = build_graph_data(small_graph)
        node = next(n for n in data["nodes"] if n["name"] == "main")
        assert node["returnType"] == "None"
        assert node["params"] == ["args"]
        assert node["decorators"] == ["entry_point"]

    def test_class_includes_bases(self, small_graph: KnowledgeGraph) -> None:
        data = build_graph_data(small_graph)
        node = next(n for n in data["nodes"] if n["name"] == "Engine")
        assert node["bases"] == ["Base"]

    def test_link_format(self, small_graph: KnowledgeGraph) -> None:
        data = build_graph_data(small_graph)
        link = data["links"][0]
        assert "source" in link
        assert "target" in link
        assert "type" in link
        assert "confidence" in link

    def test_max_nodes_limit(self, small_graph: KnowledgeGraph) -> None:
        data = build_graph_data(small_graph, max_nodes=1)
        assert len(data["nodes"]) == 1

    def test_skips_folder_nodes(self) -> None:
        g = KnowledgeGraph()
        g.add_node(GraphNode(id="d1", label=NodeLabel.FOLDER, properties=NodeProperties(name="src", file_path="/src")))
        g.add_node(GraphNode(id="f1", label=NodeLabel.FUNCTION, properties=NodeProperties(name="foo", file_path="/src/a.py")))
        data = build_graph_data(g)
        labels = [n["label"] for n in data["nodes"]]
        assert "Folder" not in labels


# ---------------------------------------------------------------------------
# build_source_response
# ---------------------------------------------------------------------------

@pytest.mark.level5
class TestBuildSourceResponse:
    def test_reads_full_file(self, source_dir: Path) -> None:
        result = build_source_response(str(source_dir / "src" / "app.py"), str(source_dir))
        assert "def main" in result["content"]
        assert result["startLine"] == 1
        assert result["language"] == "python"

    def test_reads_line_range_with_context(self, source_dir: Path) -> None:
        result = build_source_response(str(source_dir / "src" / "app.py"), str(source_dir), start=1, end=4, context_lines=1)
        assert "def main" in result["content"]

    def test_rejects_path_traversal(self, source_dir: Path) -> None:
        result = build_source_response("/etc/passwd", str(source_dir))
        assert result.get("error") == "path outside project root"

    def test_handles_missing_file(self, source_dir: Path) -> None:
        result = build_source_response(str(source_dir / "nope.py"), str(source_dir))
        assert "error" in result


# ---------------------------------------------------------------------------
# build_context_response
# ---------------------------------------------------------------------------

@pytest.mark.level5
class TestBuildContextResponse:
    def test_returns_node_info(self, small_graph: KnowledgeGraph) -> None:
        ctx = build_context_response(small_graph, "f1")
        assert ctx["node"]["name"] == "main"
        assert ctx["node"]["label"] == "Function"

    def test_returns_outbound_edges(self, small_graph: KnowledgeGraph) -> None:
        ctx = build_context_response(small_graph, "f1")
        assert len(ctx["outbound"]) == 2
        names = {r["name"] for r in ctx["outbound"]}
        assert "helper" in names
        assert "Engine" in names

    def test_returns_inbound_edges(self, small_graph: KnowledgeGraph) -> None:
        ctx = build_context_response(small_graph, "f2")
        assert len(ctx["inbound"]) == 1
        assert ctx["inbound"][0]["name"] == "main"

    def test_unknown_node_returns_error(self, small_graph: KnowledgeGraph) -> None:
        ctx = build_context_response(small_graph, "nonexistent")
        assert "error" in ctx


# ---------------------------------------------------------------------------
# build_search_results
# ---------------------------------------------------------------------------

@pytest.mark.level5
class TestBuildSearchResults:
    def test_finds_by_substring(self, small_graph: KnowledgeGraph) -> None:
        results = build_search_results(small_graph, "hel")
        assert len(results) == 1
        assert results[0]["name"] == "helper"

    def test_case_insensitive(self, small_graph: KnowledgeGraph) -> None:
        results = build_search_results(small_graph, "ENGINE")
        assert len(results) == 1

    def test_empty_query_returns_empty(self, small_graph: KnowledgeGraph) -> None:
        results = build_search_results(small_graph, "")
        assert results == []

    def test_no_match_returns_empty(self, small_graph: KnowledgeGraph) -> None:
        results = build_search_results(small_graph, "zzzzz")
        assert results == []

    def test_respects_limit(self, small_graph: KnowledgeGraph) -> None:
        results = build_search_results(small_graph, "e", limit=1)
        assert len(results) == 1
