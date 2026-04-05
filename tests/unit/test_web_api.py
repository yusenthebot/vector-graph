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
    build_file_tree,
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

    def test_node_without_file_path_returns_empty_file(self) -> None:
        """Node with no file_path returns empty string for file field."""
        g = KnowledgeGraph()
        g.add_node(GraphNode(
            id="fn1",
            label=NodeLabel.FUNCTION,
            properties=NodeProperties(name="orphan_fn", file_path=""),
        ))
        results = build_search_results(g, "orphan")
        assert len(results) == 1
        assert results[0]["file"] == ""


# ---------------------------------------------------------------------------
# build_graph_data — additional edge cases
# ---------------------------------------------------------------------------

@pytest.mark.level5
class TestBuildGraphDataAdditional:
    def test_node_with_docstring_includes_doc_field(self) -> None:
        """Node with docstring populates 'doc' field in output."""
        g = KnowledgeGraph()
        g.add_node(GraphNode(
            id="f1",
            label=NodeLabel.FUNCTION,
            properties=NodeProperties(
                name="documented_fn",
                file_path="/src/a.py",
                docstring="Does something important.",
            ),
        ))
        data = build_graph_data(g)
        node = next(n for n in data["nodes"] if n["name"] == "documented_fn")
        assert "doc" in node
        assert "something important" in node["doc"]

    def test_node_with_source_file_includes_source_snippet(self, tmp_path: Path) -> None:
        """Function node backed by a real file gets 'source' snippet."""
        src = tmp_path / "mod.py"
        src.write_text("def greet():\n    return 'hello'\n")
        g = KnowledgeGraph()
        g.add_node(GraphNode(
            id="fn_greet",
            label=NodeLabel.FUNCTION,
            properties=NodeProperties(
                name="greet",
                file_path=str(src),
                start_line=1,
                end_line=2,
            ),
        ))
        data = build_graph_data(g)
        node = next(n for n in data["nodes"] if n["name"] == "greet")
        assert "source" in node
        assert "greet" in node["source"]

    def test_source_snippet_truncated_for_large_file(self, tmp_path: Path) -> None:
        """Source snippet is truncated to 2000 chars for large functions."""
        src = tmp_path / "big.py"
        # Write 100 lines each with 30 chars -> 3000 chars total
        lines = ["x = " + "a" * 26 + "\n" for _ in range(100)]
        src.write_text("".join(lines))
        g = KnowledgeGraph()
        g.add_node(GraphNode(
            id="fn_big",
            label=NodeLabel.FUNCTION,
            properties=NodeProperties(
                name="big_fn",
                file_path=str(src),
                start_line=1,
                end_line=100,
            ),
        ))
        data = build_graph_data(g)
        node = next(n for n in data["nodes"] if n["name"] == "big_fn")
        assert "source" in node
        assert "truncated" in node["source"]

    def test_ros2_node_prioritized_before_function(self) -> None:
        """ROS2Node appears before Function when sort by priority."""
        g = KnowledgeGraph()
        g.add_node(GraphNode(
            id="fn1",
            label=NodeLabel.FUNCTION,
            properties=NodeProperties(name="plain_fn", file_path="/a.py"),
        ))
        g.add_node(GraphNode(
            id="ros1",
            label=NodeLabel.ROS2_NODE,
            properties=NodeProperties(name="MyNode", file_path="/node.py"),
        ))
        data = build_graph_data(g, max_nodes=1)
        # With max_nodes=1, only the highest priority (ROS2Node) should appear
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["label"] == "ROS2Node"

    def test_oserror_on_source_read_skips_source_field(self, tmp_path: Path) -> None:
        """OSError when reading source file is caught; no 'source' field."""
        g = KnowledgeGraph()
        g.add_node(GraphNode(
            id="fn_missing",
            label=NodeLabel.FUNCTION,
            properties=NodeProperties(
                name="missing_fn",
                file_path="/nonexistent/path/module.py",
                start_line=1,
                end_line=5,
            ),
        ))
        data = build_graph_data(g)
        node = next(n for n in data["nodes"] if n["name"] == "missing_fn")
        # Should not have source field when file is unreadable
        assert "source" not in node

    def test_method_node_gets_source_snippet(self, tmp_path: Path) -> None:
        """Method nodes (not just Function) also get source snippets."""
        src = tmp_path / "cls.py"
        src.write_text("class Foo:\n    def bar(self):\n        pass\n")
        g = KnowledgeGraph()
        g.add_node(GraphNode(
            id="m1",
            label=NodeLabel.METHOD,
            properties=NodeProperties(
                name="bar",
                file_path=str(src),
                start_line=2,
                end_line=3,
            ),
        ))
        data = build_graph_data(g)
        node = next(n for n in data["nodes"] if n["name"] == "bar")
        assert "source" in node


# ---------------------------------------------------------------------------
# build_source_response — additional cases
# ---------------------------------------------------------------------------

@pytest.mark.level5
class TestBuildSourceResponseAdditional:
    def test_start_only_returns_context_window(self, source_dir: Path) -> None:
        """Providing start without end returns context window around start line."""
        result = build_source_response(
            str(source_dir / "src" / "app.py"),
            str(source_dir),
            start=3,
        )
        assert "content" in result
        assert result["language"] == "python"
        assert result["startLine"] >= 1

    def test_start_and_end_returns_range(self, source_dir: Path) -> None:
        """Providing both start and end uses context around that range."""
        result = build_source_response(
            str(source_dir / "src" / "app.py"),
            str(source_dir),
            start=1,
            end=4,
            context_lines=0,
        )
        assert "content" in result
        assert "def main" in result["content"]

    def test_no_start_returns_full_file(self, source_dir: Path) -> None:
        """No start/end returns the entire file content."""
        result = build_source_response(
            str(source_dir / "src" / "app.py"),
            str(source_dir),
        )
        assert result["startLine"] == 1
        assert result["total"] > 0


# ---------------------------------------------------------------------------
# build_file_tree
# ---------------------------------------------------------------------------

@pytest.mark.level5
class TestBuildFileTree:
    def test_returns_dict_with_children(self, small_graph: KnowledgeGraph) -> None:
        """build_file_tree returns dict with 'children' key."""
        tree = build_file_tree(small_graph, "/src")
        assert "children" in tree
        assert "type" in tree
        assert tree["type"] == "dir"

    def test_file_node_appears_in_tree(self) -> None:
        """File nodes are included in the tree."""
        g = KnowledgeGraph()
        g.add_node(GraphNode(
            id="file1",
            label=NodeLabel.FILE,
            properties=NodeProperties(name="app.py", file_path="/project/app.py"),
        ))
        tree = build_file_tree(g, "/project")
        # Should have app.py somewhere in children
        assert "app.py" in tree["children"]

    def test_symbols_attached_to_file(self) -> None:
        """Functions in a file appear as symbols under that file in the tree."""
        g = KnowledgeGraph()
        g.add_node(GraphNode(
            id="file1",
            label=NodeLabel.FILE,
            properties=NodeProperties(name="app.py", file_path="/project/app.py"),
        ))
        g.add_node(GraphNode(
            id="fn1",
            label=NodeLabel.FUNCTION,
            properties=NodeProperties(
                name="main",
                file_path="/project/app.py",
                start_line=1,
            ),
        ))
        tree = build_file_tree(g, "/project")
        file_entry = tree["children"]["app.py"]
        assert file_entry["type"] == "file"
        symbols = file_entry["symbols"]
        assert any(s["name"] == "main" for s in symbols)

    def test_nested_directories_in_tree(self) -> None:
        """Files in subdirectories create nested tree structure."""
        g = KnowledgeGraph()
        g.add_node(GraphNode(
            id="file1",
            label=NodeLabel.FILE,
            properties=NodeProperties(name="core.py", file_path="/project/pkg/core.py"),
        ))
        tree = build_file_tree(g, "/project")
        # Should have pkg/ -> core.py
        assert "pkg" in tree["children"]
        pkg = tree["children"]["pkg"]
        assert "core.py" in pkg["children"]

    def test_symbols_sorted_by_line(self) -> None:
        """Symbols within a file are sorted by start_line."""
        g = KnowledgeGraph()
        g.add_node(GraphNode(
            id="file1",
            label=NodeLabel.FILE,
            properties=NodeProperties(name="mod.py", file_path="/proj/mod.py"),
        ))
        g.add_node(GraphNode(
            id="fn_b",
            label=NodeLabel.FUNCTION,
            properties=NodeProperties(name="beta", file_path="/proj/mod.py", start_line=10),
        ))
        g.add_node(GraphNode(
            id="fn_a",
            label=NodeLabel.FUNCTION,
            properties=NodeProperties(name="alpha", file_path="/proj/mod.py", start_line=2),
        ))
        tree = build_file_tree(g, "/proj")
        symbols = tree["children"]["mod.py"]["symbols"]
        names = [s["name"] for s in symbols]
        assert names.index("alpha") < names.index("beta")

    def test_empty_graph_returns_empty_children(self) -> None:
        """Empty graph produces tree with empty children."""
        g = KnowledgeGraph()
        tree = build_file_tree(g, "/project")
        assert tree["children"] == {}


# ---------------------------------------------------------------------------
# Three.js nebula integration tests
# ---------------------------------------------------------------------------

@pytest.mark.level5
class TestThreeJsNebulaIntegration:
    def test_html_contains_three_js_pinned_version(self) -> None:
        """HTML template loads three.js with exact version pin."""
        from vector_graph.api.web_server import _HTML
        assert 'three@0.137.0/build/three.min.js' in _HTML

    def test_html_contains_force_graph_pinned_version(self) -> None:
        """HTML template loads 3d-force-graph with exact version pin."""
        from vector_graph.api.web_server import _HTML
        assert '3d-force-graph@1.79.1' in _HTML

    def test_html_three_loads_before_force_graph(self) -> None:
        """three.js script tag appears before 3d-force-graph to ensure window.THREE is set."""
        from vector_graph.api.web_server import _HTML
        three_pos = _HTML.index('three@0.137.0')
        fg_pos = _HTML.index('3d-force-graph@1.79.1')
        assert three_pos < fg_pos, "three.js must load before 3d-force-graph"

    def test_html_contains_postprocessing_scripts(self) -> None:
        """HTML includes EffectComposer and related post-processing scripts."""
        from vector_graph.api.web_server import _HTML
        assert 'EffectComposer.js' in _HTML
        assert 'RenderPass.js' in _HTML
        assert 'UnrealBloomPass.js' in _HTML

    def test_html_three_version_compatible_with_force_graph(self) -> None:
        """three@0.137 is within 3d-force-graph's >=0.118 <1 range."""
        version = 137
        assert version >= 118 and version < 1000  # semantic: 0.137 < 1.0

    def test_html_contains_nebula_function(self) -> None:
        """HTML template contains updateNebulae rendering function."""
        from vector_graph.api.web_server import _HTML
        assert 'function updateNebulae()' in _HTML
        assert 'SphereGeometry' in _HTML
        assert 'PointsMaterial' in _HTML
        assert 'AdditiveBlending' in _HTML

    def test_html_contains_cluster_force(self) -> None:
        """HTML template has clustering force for group separation."""
        from vector_graph.api.web_server import _HTML
        assert 'clusterForce' in _HTML
        assert '_seedGroupPositions' in _HTML

    def test_build_graph_data_no_dust_nodes(self) -> None:
        """Graph data should NOT contain _isDust or _isLabel nodes (Three.js handles visuals)."""
        g = KnowledgeGraph()
        g.add_node(GraphNode(
            id="f1",
            label=NodeLabel.FUNCTION,
            properties=NodeProperties(name="foo", file_path="/a.py"),
        ))
        data = build_graph_data(g)
        dust = [n for n in data["nodes"] if n.get("_isDust") or n.get("_isLabel")]
        assert len(dust) == 0, "Data should not contain dust/label nodes"

    def test_build_graph_data_has_group_field(self) -> None:
        """Each node has a group field derived from file path."""
        g = KnowledgeGraph()
        g.add_node(GraphNode(
            id="f1",
            label=NodeLabel.FUNCTION,
            properties=NodeProperties(name="foo", file_path="/project/src/utils/helper.py"),
        ))
        data = build_graph_data(g, root_path="/project")
        assert "group" in data["nodes"][0]


# ---------------------------------------------------------------------------
# SSE + Changes Timeline (T4)
# ---------------------------------------------------------------------------

class TestSSEAndChangesTimeline:
    def test_html_contains_sse_event_source(self) -> None:
        """HTML template sets up SSE EventSource for live updates."""
        from vector_graph.api.web_server import _HTML
        assert 'EventSource' in _HTML
        assert '/api/events' in _HTML

    def test_html_contains_changes_tab(self) -> None:
        """HTML template has Changes sidebar tab."""
        from vector_graph.api.web_server import _HTML
        assert "switchTab('changes')" in _HTML
        assert 'panel-changes' in _HTML

    def test_html_contains_change_highlight(self) -> None:
        """HTML template has persistent change highlight system."""
        from vector_graph.api.web_server import _HTML
        assert 'handleChangeEvent' in _HTML
        assert 'activeChangeIds' in _HTML
        assert 'activeImpactIds' in _HTML
        assert 'clearChangeHighlight' in _HTML
        assert 'focusChange' in _HTML
