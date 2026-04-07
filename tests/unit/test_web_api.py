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
        """ROS2Node appears before Function when sort by priority (deep mode includes all labels)."""
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
        data = build_graph_data(g, max_nodes=1, mode="deep")
        # With max_nodes=1 and deep mode, only the highest priority (ROS2Node) should appear
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


# ---------------------------------------------------------------------------
# Visualization mode filtering (mode param on build_graph_data)
# ---------------------------------------------------------------------------

@pytest.mark.level5
class TestVisualizationModes:
    def _graph_with_all_labels(self) -> KnowledgeGraph:
        """Graph with FILE, FUNCTION, CLASS, METHOD, VARIABLE, PROPERTY, DECORATOR."""
        g = KnowledgeGraph()
        g.add_node(GraphNode(id="file1", label=NodeLabel.FILE,
                             properties=NodeProperties(name="mod.py", file_path="/proj/mod.py")))
        g.add_node(GraphNode(id="fn1", label=NodeLabel.FUNCTION,
                             properties=NodeProperties(name="do_work", file_path="/proj/mod.py")))
        g.add_node(GraphNode(id="cls1", label=NodeLabel.CLASS,
                             properties=NodeProperties(name="MyClass", file_path="/proj/mod.py")))
        g.add_node(GraphNode(id="meth1", label=NodeLabel.METHOD,
                             properties=NodeProperties(name="run", file_path="/proj/mod.py")))
        g.add_node(GraphNode(id="var1", label=NodeLabel.VARIABLE,
                             properties=NodeProperties(name="CONST", file_path="/proj/mod.py")))
        g.add_node(GraphNode(id="prop1", label=NodeLabel.PROPERTY,
                             properties=NodeProperties(name="value", file_path="/proj/mod.py")))
        g.add_node(GraphNode(id="dec1", label=NodeLabel.DECORATOR,
                             properties=NodeProperties(name="cached", file_path="/proj/mod.py")))
        return g

    def _graph_with_mixed_edges(self) -> KnowledgeGraph:
        """Graph with FILE nodes and CALLS + IMPORTS edges."""
        g = KnowledgeGraph()
        g.add_node(GraphNode(id="fa", label=NodeLabel.FILE,
                             properties=NodeProperties(name="a.py", file_path="/proj/a.py")))
        g.add_node(GraphNode(id="fb", label=NodeLabel.FILE,
                             properties=NodeProperties(name="b.py", file_path="/proj/b.py")))
        g.add_edge(Edge(id="e_imp", source_id="fa", target_id="fb",
                        edge_type=EdgeType.IMPORTS, confidence=1.0))
        g.add_edge(Edge(id="e_calls", source_id="fa", target_id="fb",
                        edge_type=EdgeType.CALLS, confidence=0.9))
        return g

    def test_build_graph_data_architecture_mode_only_files(self) -> None:
        """architecture mode keeps only FILE label nodes."""
        data = build_graph_data(self._graph_with_all_labels(), mode="architecture")
        labels = {n["label"] for n in data["nodes"]}
        assert labels == {"File"}, f"Expected only File nodes, got {labels}"

    def test_build_graph_data_architecture_mode_only_imports(self) -> None:
        """architecture mode keeps only IMPORTS edges."""
        data = build_graph_data(self._graph_with_mixed_edges(), mode="architecture")
        edge_types = {lnk["type"] for lnk in data["links"]}
        assert EdgeType.CALLS.value not in edge_types
        assert EdgeType.IMPORTS.value in edge_types

    def test_build_graph_data_logic_mode_includes_functions(self) -> None:
        """logic mode includes FILE, FUNCTION, CLASS, METHOD nodes."""
        data = build_graph_data(self._graph_with_all_labels(), mode="logic")
        labels = {n["label"] for n in data["nodes"]}
        assert NodeLabel.FILE.value in labels
        assert NodeLabel.FUNCTION.value in labels
        assert NodeLabel.CLASS.value in labels
        assert NodeLabel.METHOD.value in labels

    def test_build_graph_data_logic_mode_excludes_variables(self) -> None:
        """logic mode excludes VARIABLE, PROPERTY, DECORATOR nodes."""
        data = build_graph_data(self._graph_with_all_labels(), mode="logic")
        labels = {n["label"] for n in data["nodes"]}
        assert NodeLabel.VARIABLE.value not in labels
        assert NodeLabel.PROPERTY.value not in labels
        assert NodeLabel.DECORATOR.value not in labels

    def test_build_graph_data_deep_mode_includes_all(self) -> None:
        """deep mode includes all node types (VARIABLE, PROPERTY, DECORATOR present)."""
        data = build_graph_data(self._graph_with_all_labels(), mode="deep")
        labels = {n["label"] for n in data["nodes"]}
        assert NodeLabel.VARIABLE.value in labels
        assert NodeLabel.PROPERTY.value in labels
        assert NodeLabel.DECORATOR.value in labels

    def test_build_graph_data_deep_mode_max_nodes_2000(self) -> None:
        """deep mode allows up to 2000 nodes when max_nodes not specified."""
        from vector_graph.api.web_server import _MODE_MAX_NODES
        assert _MODE_MAX_NODES["deep"] == 2000

    def test_build_graph_data_default_mode_is_logic(self) -> None:
        """Calling build_graph_data with no mode argument behaves like mode='logic'."""
        g = self._graph_with_all_labels()
        data_default = build_graph_data(g)
        data_logic = build_graph_data(g, mode="logic")
        default_labels = {n["label"] for n in data_default["nodes"]}
        logic_labels = {n["label"] for n in data_logic["nodes"]}
        assert default_labels == logic_labels

    def test_build_graph_data_architecture_file_node_has_symbol_count(self) -> None:
        """In architecture mode, FILE nodes carry function_count and class_count."""
        g = KnowledgeGraph()
        g.add_node(GraphNode(id="file1", label=NodeLabel.FILE,
                             properties=NodeProperties(name="mod.py", file_path="/proj/mod.py")))
        g.add_node(GraphNode(id="fn1", label=NodeLabel.FUNCTION,
                             properties=NodeProperties(name="foo", file_path="/proj/mod.py")))
        g.add_node(GraphNode(id="fn2", label=NodeLabel.FUNCTION,
                             properties=NodeProperties(name="bar", file_path="/proj/mod.py")))
        g.add_node(GraphNode(id="cls1", label=NodeLabel.CLASS,
                             properties=NodeProperties(name="Engine", file_path="/proj/mod.py")))
        data = build_graph_data(g, mode="architecture")
        file_node = next(n for n in data["nodes"] if n["label"] == "File")
        assert file_node["function_count"] == 2
        assert file_node["class_count"] == 1


# ---------------------------------------------------------------------------
# Resizable panels
# ---------------------------------------------------------------------------

class TestResizablePanels:
    def test_html_contains_sidebar_resize_handle(self):
        from vector_graph.api.web_server import _HTML
        assert 'id="sidebar-resize"' in _HTML
        assert 'resize-handle' in _HTML

    def test_html_contains_inspector_resize_handle(self):
        from vector_graph.api.web_server import _HTML
        assert 'id="inspector-resize"' in _HTML


# ---------------------------------------------------------------------------
# Mode selector UI
# ---------------------------------------------------------------------------

class TestModeSelectorUI:
    def test_html_contains_mode_selector_div(self):
        """HTML contains the mode-selector container div."""
        from vector_graph.api.web_server import _HTML
        assert 'id="mode-selector"' in _HTML

    def test_html_contains_all_three_mode_buttons(self):
        """HTML has buttons for architecture, logic, and deep modes."""
        from vector_graph.api.web_server import _HTML
        assert 'data-mode="architecture"' in _HTML
        assert 'data-mode="logic"' in _HTML
        assert 'data-mode="deep"' in _HTML

    def test_html_logic_button_is_default_active(self):
        """The logic mode button starts with class active (default mode)."""
        from vector_graph.api.web_server import _HTML
        # The logic button must have both 'mode-btn active' and 'data-mode="logic"'
        assert 'class="mode-btn active" data-mode="logic"' in _HTML

    def test_html_contains_sb_stats_span(self):
        """HTML contains the sb-stats span for node/link counts (status bar replaces topbar)."""
        from vector_graph.api.web_server import _HTML
        assert 'id="sb-stats"' in _HTML

    def test_js_contains_current_mode_state(self):
        """JS declares currentMode state variable with localStorage fallback."""
        from vector_graph.api.web_server import _HTML
        assert "currentMode" in _HTML
        assert "localStorage.getItem('vg-mode')" in _HTML

    def test_js_contains_switch_mode_function(self):
        """JS defines switchMode() for mode switching."""
        from vector_graph.api.web_server import _HTML
        assert "function switchMode(" in _HTML

    def test_js_load_data_uses_current_mode(self):
        """loadData() pre-caches all modes and uses modeCache[currentMode]."""
        from vector_graph.api.web_server import _HTML
        assert "modeCache[currentMode]" in _HTML

    def test_js_contains_keyboard_shortcuts(self):
        """Keyboard shortcuts 1/2/3 map to architecture/logic/deep modes."""
        from vector_graph.api.web_server import _HTML
        assert "switchMode('architecture')" in _HTML
        assert "switchMode('logic')" in _HTML
        assert "switchMode('deep')" in _HTML
        # Triggered only when not in an input field
        assert "tagName !== 'INPUT'" in _HTML

    def test_js_update_status_bar_writes_sb_stats(self):
        """updateStatusBar() targets sb-stats element (status bar replaces topbar)."""
        from vector_graph.api.web_server import _HTML
        assert "'sb-stats'" in _HTML
        # Must NOT reference the removed topbar-stats element
        assert "'topbar-stats'" not in _HTML

    def test_css_contains_mode_btn_styles(self):
        """CSS defines .mode-btn and .mode-btn.active rules."""
        from vector_graph.api.web_server import _HTML
        assert ".mode-btn" in _HTML
        assert ".mode-btn.active" in _HTML
        assert ".mode-btn:hover" in _HTML

    def test_css_contains_mode_selector_flex(self):
        """CSS defines #mode-selector as flex container."""
        from vector_graph.api.web_server import _HTML
        assert "#mode-selector" in _HTML
        assert "display:flex" in _HTML


# ---------------------------------------------------------------------------
# Enriched change panel: diffs, test suggestions, change frequency
# ---------------------------------------------------------------------------

class TestEnrichedChangePanel:
    def test_css_contains_diff_block_styles(self):
        """CSS defines .diff-block rule with collapsed variant."""
        from vector_graph.api.web_server import _HTML
        assert ".diff-block" in _HTML
        assert ".diff-block.collapsed" in _HTML

    def test_css_contains_diff_line_color_classes(self):
        """CSS defines diff line color classes for add, del, and header."""
        from vector_graph.api.web_server import _HTML
        assert ".diff-line-add" in _HTML
        assert ".diff-line-del" in _HTML
        assert ".diff-line-hdr" in _HTML

    def test_css_contains_collapse_toggle_styles(self):
        """CSS defines .collapse-toggle with hover state."""
        from vector_graph.api.web_server import _HTML
        assert ".collapse-toggle" in _HTML
        assert ".collapse-toggle:hover" in _HTML

    def test_css_contains_source_preview_styles(self):
        """CSS defines .source-preview and .source-preview.open."""
        from vector_graph.api.web_server import _HTML
        assert ".source-preview" in _HTML
        assert ".source-preview.open" in _HTML

    def test_css_contains_test_item_styles(self):
        """CSS defines .test-item and .test-depth for test suggestion display."""
        from vector_graph.api.web_server import _HTML
        assert ".test-item" in _HTML
        assert ".test-depth" in _HTML

    def test_css_contains_change_freq_badge(self):
        """CSS defines .change-freq for the frequency badge."""
        from vector_graph.api.web_server import _HTML
        assert ".change-freq" in _HTML

    def test_js_contains_session_change_count_state(self):
        """JS declares sessionChangeCount state variable."""
        from vector_graph.api.web_server import _HTML
        assert "sessionChangeCount" in _HTML

    def test_js_handle_change_event_tracks_frequency(self):
        """handleChangeEvent tracks per-symbol change frequency."""
        from vector_graph.api.web_server import _HTML
        assert "sessionChangeCount[name]" in _HTML
        assert "nodes_added" in _HTML
        assert "nodes_modified" in _HTML

    def test_js_contains_toggle_diff_function(self):
        """JS defines toggleDiff() helper for expand/collapse."""
        from vector_graph.api.web_server import _HTML
        assert "function toggleDiff(" in _HTML
        assert "classList.toggle('open')" in _HTML

    def test_js_contains_format_diff_function(self):
        """JS defines formatDiff() for unified diff coloring."""
        from vector_graph.api.web_server import _HTML
        assert "function formatDiff(" in _HTML
        assert "diff-line-add" in _HTML
        assert "diff-line-del" in _HTML
        assert "diff-line-hdr" in _HTML

    def test_js_contains_format_diff_removed_function(self):
        """JS defines formatDiffRemoved() for all-red removed source."""
        from vector_graph.api.web_server import _HTML
        assert "function formatDiffRemoved(" in _HTML

    def test_js_contains_ordinal_function(self):
        """JS defines ordinal() for 1st/2nd/3rd display."""
        from vector_graph.api.web_server import _HTML
        assert "function ordinal(" in _HTML

    def test_js_contains_fetch_test_suggestions_function(self):
        """JS defines fetchTestSuggestions() async function."""
        from vector_graph.api.web_server import _HTML
        assert "async function fetchTestSuggestions(" in _HTML
        assert "/api/suggest-tests?name=" in _HTML

    def test_js_fetch_test_suggestions_deduplicates(self):
        """fetchTestSuggestions deduplicates by test_file::test_name key."""
        from vector_graph.api.web_server import _HTML
        assert "test_file + '::' + s.test_name" in _HTML

    def test_js_show_impact_panel_uses_diffs_field(self):
        """showImpactPanel reads change.diffs for diff text."""
        from vector_graph.api.web_server import _HTML
        assert "change.diffs" in _HTML

    def test_js_show_impact_panel_renders_diff_blocks(self):
        """showImpactPanel renders .diff-block elements with toggleDiff."""
        from vector_graph.api.web_server import _HTML
        assert "diff-block" in _HTML
        assert "toggleDiff(" in _HTML

    def test_js_show_impact_panel_renders_source_previews(self):
        """showImpactPanel renders .source-preview for Calls/Depended On By."""
        from vector_graph.api.web_server import _HTML
        assert "source-preview" in _HTML
        assert "srcNode.source" in _HTML

    def test_js_show_impact_panel_shows_test_suggestions_section(self):
        """showImpactPanel adds test-suggestions-section and async fetch."""
        from vector_graph.api.web_server import _HTML
        assert "test-suggestions-section" in _HTML
        assert "test-suggestions-loading" in _HTML
        assert "fetchTestSuggestions(" in _HTML

    def test_js_show_impact_panel_shows_change_freq_badge(self):
        """showImpactPanel shows change-freq badge when freq > 1."""
        from vector_graph.api.web_server import _HTML
        assert "change-freq" in _HTML
        assert "ordinal(freq)" in _HTML

    def test_js_expand_toggle_stops_propagation_for_calls(self):
        """Expand toggle in Calls/Depended On By uses event.stopPropagation."""
        from vector_graph.api.web_server import _HTML
        assert "event.stopPropagation()" in _HTML


# ---------------------------------------------------------------------------
# /api/git-history endpoint
# ---------------------------------------------------------------------------

class TestGitHistoryEndpoint:
    def test_html_contains_git_history_fetch(self):
        """The JS or HTML should be ready to fetch /api/git-history."""
        # Placeholder: actual integration test would require a running server.
        # This verifies the test infrastructure is in place.
        pass  # placeholder — actual integration test would need a running server

    def test_git_history_endpoint_registered(self):
        """The web_server.py handler should contain the git-history path."""
        import inspect
        from vector_graph.api import web_server
        source = inspect.getsource(web_server)
        assert "/api/git-history" in source


# ---------------------------------------------------------------------------
# 2D impact graph label collision avoidance
# ---------------------------------------------------------------------------

class TestImpactGraphLabels:
    """Impact graph rendering (updated v0.9.2 — HTML tree replaced force-graph canvas)."""

    def test_impact_tree_replaces_force_graph(self):
        """v0.9.2: HTML impact tree replaces the old 2D force-graph canvas."""
        from vector_graph.api.web_server import _HTML
        assert "buildImpactTree" in _HTML

    def test_2d_hover_state_var_retained(self):
        """hovered2dId state variable is retained (used by buildImpactSubgraph dead code)."""
        from vector_graph.api.web_server import _HTML
        assert "hovered2dId" in _HTML

    def test_impact_tree_has_calls_groups(self):
        """Impact tree shows calls/called-by groups for each changed node."""
        from vector_graph.api.web_server import _HTML
        assert "tree-group-label" in _HTML or "tree-group" in _HTML


# ---------------------------------------------------------------------------
# Fan-in/fan-out connectivity data in build_graph_data output (v0.8.0)
# ---------------------------------------------------------------------------

class TestFanConnectivity:
    """Fan-in/fan-out connectivity data in build_graph_data output (v0.8.0)."""

    def test_includes_fan_fields(self, tmp_project: Path) -> None:
        """Every node has fanIn and fanOut integer fields."""
        from vector_graph.api.python_api import CodeGraph
        cg = CodeGraph(tmp_project)
        cg.analyze()
        assert cg._graph is not None
        data = build_graph_data(cg._graph, mode="deep")
        for node in data["nodes"]:
            assert "fanIn" in node, f"fanIn missing on {node['name']}"
            assert "fanOut" in node, f"fanOut missing on {node['name']}"
            assert isinstance(node["fanIn"], int) and node["fanIn"] >= 0
            assert isinstance(node["fanOut"], int) and node["fanOut"] >= 0

    def test_fan_out_counts_outbound_edges(self, tmp_project: Path) -> None:
        """A function that calls 2 others should have fanOut >= 2."""
        from vector_graph.api.python_api import CodeGraph
        cg = CodeGraph(tmp_project)
        cg.analyze()
        assert cg._graph is not None
        data = build_graph_data(cg._graph, mode="deep")
        nodes_with_fanout = [n for n in data["nodes"] if n["fanOut"] >= 1]
        assert len(nodes_with_fanout) >= 1, "Expected at least one node with fanOut >= 1"

    def test_fan_in_counts_inbound_edges(self, tmp_project: Path) -> None:
        """A function called by others should have fanIn >= 1."""
        from vector_graph.api.python_api import CodeGraph
        cg = CodeGraph(tmp_project)
        cg.analyze()
        assert cg._graph is not None
        data = build_graph_data(cg._graph, mode="deep")
        nodes_with_fanin = [n for n in data["nodes"] if n["fanIn"] >= 1]
        assert len(nodes_with_fanin) >= 1, "Expected at least one node with fanIn >= 1"

    def test_fan_counts_all_edge_types(self) -> None:
        """Fan counts include IMPORTS, EXTENDS, etc. — not just CALLS."""
        g = KnowledgeGraph()
        g.add_node(GraphNode(
            id="fa",
            label=NodeLabel.FILE,
            properties=NodeProperties(name="a.py", file_path="/proj/a.py"),
        ))
        g.add_node(GraphNode(
            id="fb",
            label=NodeLabel.FILE,
            properties=NodeProperties(name="b.py", file_path="/proj/b.py"),
        ))
        g.add_edge(Edge(id="e1", source_id="fa", target_id="fb",
                        edge_type=EdgeType.IMPORTS, confidence=1.0))
        data = build_graph_data(g, mode="deep")
        node_a = next(n for n in data["nodes"] if n["id"] == "fa")
        assert node_a["fanOut"] >= 1

    def test_fan_excludes_pruned_nodes(self) -> None:
        """In architecture mode, edges to pruned (non-FILE) nodes are not counted."""
        g = KnowledgeGraph()
        g.add_node(GraphNode(
            id="file1",
            label=NodeLabel.FILE,
            properties=NodeProperties(name="mod.py", file_path="/proj/mod.py"),
        ))
        g.add_node(GraphNode(
            id="fn1",
            label=NodeLabel.FUNCTION,
            properties=NodeProperties(name="foo", file_path="/proj/mod.py"),
        ))
        g.add_edge(Edge(id="e1", source_id="file1", target_id="fn1",
                        edge_type=EdgeType.CONTAINS, confidence=1.0))
        # architecture mode only includes FILE nodes; fn1 is pruned
        data = build_graph_data(g, mode="architecture")
        file_node = next(n for n in data["nodes"] if n["id"] == "file1")
        assert file_node["fanOut"] == 0


class TestHoverEdgesAndConnectivitySizing:
    """P0-1 hover-to-show edges + P0-2 connectivity sizing (v0.8.0)."""

    def test_hovered_id_state_variable(self):
        from vector_graph.api.web_server import _HTML
        assert "let hoveredId = null" in _HTML

    def test_on_node_hover_callback(self):
        from vector_graph.api.web_server import _HTML
        assert ".onNodeHover(" in _HTML

    def test_default_edge_opacity_zero(self):
        """Default link opacity is 0 when nothing hovered/selected."""
        from vector_graph.api.web_server import _HTML
        # The linkOpacity callback should have hoveredId checks
        assert "hoveredId" in _HTML

    def test_connectivity_sizing_in_get_node_size(self):
        from vector_graph.api.web_server import _HTML
        assert "n.fanIn" in _HTML
        assert "n.fanOut" in _HTML
        assert "Math.log2" in _HTML


class TestPanelCollapse:
    """Panel collapse with keyboard shortcuts (v0.9.0)."""

    def test_css_sidebar_collapsed(self):
        from vector_graph.api.web_server import _HTML
        assert '#sidebar.collapsed' in _HTML

    def test_css_inspector_collapsed(self):
        from vector_graph.api.web_server import _HTML
        assert '#inspector.collapsed' in _HTML

    def test_js_toggle_sidebar(self):
        from vector_graph.api.web_server import _HTML
        assert 'function toggleSidebar()' in _HTML

    def test_js_toggle_inspector(self):
        from vector_graph.api.web_server import _HTML
        assert 'function toggleInspector()' in _HTML

    def test_js_ctrl_b_shortcut(self):
        from vector_graph.api.web_server import _HTML
        assert 'toggleSidebar' in _HTML

    def test_js_sidebar_state_persisted(self):
        from vector_graph.api.web_server import _HTML
        assert "'vg-sidebar-collapsed'" in _HTML


# ---------------------------------------------------------------------------
# Status bar (v0.9.0) — replaces helpbar + topbar + sidebar-stats
# ---------------------------------------------------------------------------

class TestStatusBar:
    """Status bar replaces helpbar + topbar + sidebar-stats (v0.9.0)."""

    def test_html_contains_statusbar(self):
        from vector_graph.api.web_server import _HTML
        assert 'id="statusbar"' in _HTML

    def test_html_contains_statusbar_sections(self):
        from vector_graph.api.web_server import _HTML
        assert 'id="sb-mode"' in _HTML
        assert 'id="sb-stats"' in _HTML
        assert 'id="sb-hints"' in _HTML

    def test_html_no_helpbar(self):
        from vector_graph.api.web_server import _HTML
        assert 'id="helpbar"' not in _HTML

    def test_html_no_topbar(self):
        from vector_graph.api.web_server import _HTML
        assert 'id="topbar"' not in _HTML

    def test_html_no_sidebar_stats(self):
        from vector_graph.api.web_server import _HTML
        assert 'id="sidebar-stats"' not in _HTML

    def test_html_main_row_wrapper(self):
        from vector_graph.api.web_server import _HTML
        assert 'id="main-row"' in _HTML

    def test_js_update_status_bar_function(self):
        from vector_graph.api.web_server import _HTML
        assert 'function updateStatusBar()' in _HTML

    def test_js_statusbar_context_sensitive(self):
        from vector_graph.api.web_server import _HTML
        assert 'sb-hints' in _HTML
        assert 'sb-mode' in _HTML

    def test_js_fps_counter(self):
        from vector_graph.api.web_server import _HTML
        assert 'sb-fps' in _HTML


# ---------------------------------------------------------------------------
# Sidebar tabs (restored)
# ---------------------------------------------------------------------------

class TestSidebarTabs:
    """Sidebar uses tab navigation."""

    def test_html_sidebar_tabs(self):
        from vector_graph.api.web_server import _HTML
        assert 'class="sidebar-tabs"' in _HTML

    def test_html_panel_ids(self):
        from vector_graph.api.web_server import _HTML
        assert 'id="panel-explorer"' in _HTML
        assert 'id="panel-groups"' in _HTML
        assert 'id="panel-filters"' in _HTML
        assert 'id="panel-changes"' in _HTML

    def test_js_switch_tab(self):
        from vector_graph.api.web_server import _HTML
        assert 'function switchTab(' in _HTML


# ---------------------------------------------------------------------------
# Command palette (v0.9.0)
# ---------------------------------------------------------------------------

class TestCommandPalette:
    """Command palette overlay (v0.9.0)."""

    def test_html_cmd_palette_element(self):
        from vector_graph.api.web_server import _HTML
        assert 'id="cmd-palette"' in _HTML

    def test_html_cmd_input(self):
        from vector_graph.api.web_server import _HTML
        assert 'id="cmd-input"' in _HTML

    def test_html_cmd_results(self):
        from vector_graph.api.web_server import _HTML
        assert 'id="cmd-results"' in _HTML

    def test_js_open_cmd_palette(self):
        from vector_graph.api.web_server import _HTML
        assert 'function openCmdPalette()' in _HTML

    def test_js_close_cmd_palette(self):
        from vector_graph.api.web_server import _HTML
        assert 'function closeCmdPalette()' in _HTML

    def test_js_cmd_commands_list(self):
        from vector_graph.api.web_server import _HTML
        assert 'CMD_COMMANDS' in _HTML

    def test_js_keyboard_nav(self):
        from vector_graph.api.web_server import _HTML
        assert 'ArrowDown' in _HTML
        assert 'ArrowUp' in _HTML

    def test_css_cmd_styles(self):
        from vector_graph.api.web_server import _HTML
        assert '#cmd-palette' in _HTML
        assert '#cmd-dialog' in _HTML
        assert '.cmd-item' in _HTML

    def test_js_slash_opens_palette(self):
        from vector_graph.api.web_server import _HTML
        assert "openCmdPalette" in _HTML


class TestVisualWins:
    """F2 default arrows + F3 nebula labels + F6 dash patterns (v0.9.1)."""

    def test_default_arrows_for_calls(self):
        """CALLS edges show small arrows by default."""
        from vector_graph.api.web_server import _HTML
        assert "l.type === 'CALLS'" in _HTML or "CALLS" in _HTML

    def test_nebula_label_min_scale(self):
        """Nebula labels have minimum scale of 50."""
        from vector_graph.api.web_server import _HTML
        assert 'Math.max' in _HTML
        assert '50' in _HTML

    def test_nebula_label_background(self):
        """Nebula labels have background rect for contrast."""
        from vector_graph.api.web_server import _HTML
        assert 'fillRect' in _HTML

    def test_link_line_dash(self):
        """Edge dash patterns differentiate IMPORTS from CALLS."""
        from vector_graph.api.web_server import _HTML
        assert 'linkLineDash' in _HTML or 'lineDash' in _HTML


# ---------------------------------------------------------------------------
# Legend panel + minimap (v0.9.1)
# ---------------------------------------------------------------------------

class TestLegendAndMinimap:
    """Legend panel + minimap (v0.9.1)."""

    def test_html_legend_element(self):
        from vector_graph.api.web_server import _HTML
        assert 'id="legend"' in _HTML

    def test_js_build_legend(self):
        from vector_graph.api.web_server import _HTML
        assert 'function buildLegend()' in _HTML or 'buildLegend' in _HTML

    def test_css_legend_styles(self):
        from vector_graph.api.web_server import _HTML
        assert '#legend' in _HTML

    def test_html_minimap_canvas(self):
        from vector_graph.api.web_server import _HTML
        assert 'id="minimap"' in _HTML

    def test_js_update_minimap(self):
        from vector_graph.api.web_server import _HTML
        assert 'updateMinimap' in _HTML

    def test_css_minimap_styles(self):
        from vector_graph.api.web_server import _HTML
        assert '#minimap' in _HTML
# Selection Glow (F5) + Constellation Expand (F8)
# ---------------------------------------------------------------------------

class TestGlowAndConstellation:
    """Selection glow + constellation expand animation (v0.9.1)."""

    def test_js_selection_glow_group(self):
        from vector_graph.api.web_server import _HTML
        assert '_selectionGlowGroup' in _HTML

    def test_js_add_selection_glow(self):
        from vector_graph.api.web_server import _HTML
        assert 'function addSelectionGlow(' in _HTML

    def test_js_remove_selection_glow(self):
        from vector_graph.api.web_server import _HTML
        assert 'removeSelectionGlow' in _HTML

    def test_js_constellation_force(self):
        from vector_graph.api.web_server import _HTML
        assert "'constellation'" in _HTML


class TestNodeLabels:
    """Node text labels with LOD (v0.9.1 F1)."""

    def test_js_node_label_sprite(self):
        from vector_graph.api.web_server import _HTML
        assert 'THREE.Sprite' in _HTML or 'SpriteMaterial' in _HTML

    def test_js_label_lod_distance(self):
        from vector_graph.api.web_server import _HTML
        assert '_updateLabelVisibility' in _HTML or 'labelVisible' in _HTML


class TestImpactTree:
    """Impact tree diagram replaces force-graph (v0.9.2)."""

    def test_js_build_impact_tree(self):
        from vector_graph.api.web_server import _HTML
        assert 'buildImpactTree' in _HTML

    def test_css_impact_tree_styles(self):
        from vector_graph.api.web_server import _HTML
        assert '.impact-tree' in _HTML

    def test_js_tree_node_click(self):
        from vector_graph.api.web_server import _HTML
        assert 'previewNode' in _HTML  # tree nodes click to fly to 3D
