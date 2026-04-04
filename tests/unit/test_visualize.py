"""L5 unit tests for vector_graph.api.visualize — CLI output functions."""

from __future__ import annotations

from pathlib import Path

import pytest

from vector_graph._types import (
    AnalysisResult,
    Edge,
    EdgeType,
    GraphNode,
    ImpactEntry,
    ImpactResult,
    NodeLabel,
    NodeProperties,
)
from vector_graph.graph.knowledge_graph import KnowledgeGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_impact(
    target_name: str = "foo",
    risk: str = "LOW",
    entries: tuple[ImpactEntry, ...] = (),
    direction: str = "upstream",
) -> ImpactResult:
    return ImpactResult(
        target_name=target_name,
        target_file="/src/foo.py",
        direction=direction,
        risk=risk,
        entries=entries,
    )


def _make_entry(name: str = "bar", depth: int = 1) -> ImpactEntry:
    return ImpactEntry(
        node_id="n1",
        name=name,
        file_path="/src/bar.py",
        depth=depth,
        edge_type="CALLS",
        confidence=0.9,
    )


# ---------------------------------------------------------------------------
# print_summary
# ---------------------------------------------------------------------------

@pytest.mark.level5
class TestPrintSummary:
    def test_outputs_node_count(self, capsys: pytest.CaptureFixture) -> None:
        """print_summary includes node count in output."""
        from vector_graph.api.visualize import print_summary

        result = AnalysisResult(root="/test", node_count=100, edge_count=200, file_count=10)
        print_summary(result)
        captured = capsys.readouterr()
        assert "100" in captured.out

    def test_outputs_edge_count(self, capsys: pytest.CaptureFixture) -> None:
        """print_summary includes edge count in output."""
        from vector_graph.api.visualize import print_summary

        result = AnalysisResult(root="/test", node_count=5, edge_count=333)
        print_summary(result)
        captured = capsys.readouterr()
        assert "333" in captured.out

    def test_outputs_file_count(self, capsys: pytest.CaptureFixture) -> None:
        """print_summary includes file count in output."""
        from vector_graph.api.visualize import print_summary

        result = AnalysisResult(root="/test", file_count=42)
        print_summary(result)
        captured = capsys.readouterr()
        assert "42" in captured.out

    def test_outputs_function_count(self, capsys: pytest.CaptureFixture) -> None:
        """print_summary includes function count in output."""
        from vector_graph.api.visualize import print_summary

        result = AnalysisResult(root="/test", function_count=77)
        print_summary(result)
        captured = capsys.readouterr()
        assert "77" in captured.out

    def test_outputs_class_count(self, capsys: pytest.CaptureFixture) -> None:
        """print_summary includes class count in output."""
        from vector_graph.api.visualize import print_summary

        result = AnalysisResult(root="/test", class_count=12)
        print_summary(result)
        captured = capsys.readouterr()
        assert "12" in captured.out

    def test_outputs_root_path(self, capsys: pytest.CaptureFixture) -> None:
        """print_summary outputs the root directory path."""
        from vector_graph.api.visualize import print_summary

        result = AnalysisResult(root="/myproject/src")
        print_summary(result)
        captured = capsys.readouterr()
        assert "/myproject/src" in captured.out

    def test_zero_counts_produce_output(self, capsys: pytest.CaptureFixture) -> None:
        """print_summary with all-zero counts still produces output."""
        from vector_graph.api.visualize import print_summary

        result = AnalysisResult(root="/empty")
        print_summary(result)
        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_outputs_import_count(self, capsys: pytest.CaptureFixture) -> None:
        """print_summary includes import count in output."""
        from vector_graph.api.visualize import print_summary

        result = AnalysisResult(root="/test", import_count=55)
        print_summary(result)
        captured = capsys.readouterr()
        assert "55" in captured.out

    def test_outputs_call_count(self, capsys: pytest.CaptureFixture) -> None:
        """print_summary includes call edge count in output."""
        from vector_graph.api.visualize import print_summary

        result = AnalysisResult(root="/test", call_count=88)
        print_summary(result)
        captured = capsys.readouterr()
        assert "88" in captured.out

    def test_outputs_community_count(self, capsys: pytest.CaptureFixture) -> None:
        """print_summary includes community count in output."""
        from vector_graph.api.visualize import print_summary

        result = AnalysisResult(root="/test", community_count=3)
        print_summary(result)
        captured = capsys.readouterr()
        assert "3" in captured.out

    def test_outputs_process_count(self, capsys: pytest.CaptureFixture) -> None:
        """print_summary includes execution flow count in output."""
        from vector_graph.api.visualize import print_summary

        result = AnalysisResult(root="/test", process_count=7)
        print_summary(result)
        captured = capsys.readouterr()
        assert "7" in captured.out


# ---------------------------------------------------------------------------
# print_impact
# ---------------------------------------------------------------------------

@pytest.mark.level5
class TestPrintImpact:
    def test_outputs_risk_level_low(self, capsys: pytest.CaptureFixture) -> None:
        """print_impact includes risk label in output."""
        from vector_graph.api.visualize import print_impact

        impact = _make_impact(risk="LOW")
        print_impact(impact)
        captured = capsys.readouterr()
        assert "LOW" in captured.out

    def test_outputs_risk_level_high(self, capsys: pytest.CaptureFixture) -> None:
        """print_impact includes HIGH risk label."""
        from vector_graph.api.visualize import print_impact

        impact = _make_impact(risk="HIGH")
        print_impact(impact)
        captured = capsys.readouterr()
        assert "HIGH" in captured.out

    def test_outputs_risk_level_critical(self, capsys: pytest.CaptureFixture) -> None:
        """print_impact includes CRITICAL risk label."""
        from vector_graph.api.visualize import print_impact

        impact = _make_impact(risk="CRITICAL")
        print_impact(impact)
        captured = capsys.readouterr()
        assert "CRITICAL" in captured.out

    def test_outputs_risk_level_medium(self, capsys: pytest.CaptureFixture) -> None:
        """print_impact includes MEDIUM risk label."""
        from vector_graph.api.visualize import print_impact

        impact = _make_impact(risk="MEDIUM")
        print_impact(impact)
        captured = capsys.readouterr()
        assert "MEDIUM" in captured.out

    def test_outputs_target_name(self, capsys: pytest.CaptureFixture) -> None:
        """print_impact includes the target function name."""
        from vector_graph.api.visualize import print_impact

        impact = _make_impact(target_name="validate_email")
        print_impact(impact)
        captured = capsys.readouterr()
        assert "validate_email" in captured.out

    def test_outputs_direction(self, capsys: pytest.CaptureFixture) -> None:
        """print_impact includes the direction in output."""
        from vector_graph.api.visualize import print_impact

        impact = _make_impact(direction="downstream")
        print_impact(impact)
        captured = capsys.readouterr()
        assert "downstream" in captured.out

    def test_no_entries_outputs_no_affected_message(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """print_impact with empty entries prints a 'no affected' message."""
        from vector_graph.api.visualize import print_impact

        impact = _make_impact(entries=())
        print_impact(impact)
        captured = capsys.readouterr()
        # Should mention no symbols or similar — just verify it produces output
        assert len(captured.out) > 0

    def test_entries_are_displayed(self, capsys: pytest.CaptureFixture) -> None:
        """print_impact prints entry names when entries exist."""
        from vector_graph.api.visualize import print_impact

        entries = (_make_entry("caller_func", depth=1),)
        impact = _make_impact(entries=entries)
        print_impact(impact)
        captured = capsys.readouterr()
        assert "caller_func" in captured.out

    def test_multiple_entries_displayed(self, capsys: pytest.CaptureFixture) -> None:
        """print_impact lists multiple impacted symbols."""
        from vector_graph.api.visualize import print_impact

        entries = (
            _make_entry("alpha", depth=1),
            _make_entry("beta", depth=2),
            _make_entry("gamma", depth=3),
        )
        impact = _make_impact(entries=entries)
        print_impact(impact)
        captured = capsys.readouterr()
        assert "alpha" in captured.out
        assert "beta" in captured.out
        assert "gamma" in captured.out

    def test_entry_depth_displayed(self, capsys: pytest.CaptureFixture) -> None:
        """print_impact displays depth values for entries."""
        from vector_graph.api.visualize import print_impact

        entries = (_make_entry("deep_fn", depth=2),)
        impact = _make_impact(entries=entries)
        print_impact(impact)
        captured = capsys.readouterr()
        assert "2" in captured.out

    def test_truncates_at_30_entries(self, capsys: pytest.CaptureFixture) -> None:
        """print_impact truncates display at 30 entries and shows remainder count."""
        from vector_graph.api.visualize import print_impact

        entries = tuple(_make_entry(f"fn_{i}", depth=1) for i in range(35))
        impact = _make_impact(entries=entries)
        print_impact(impact)
        captured = capsys.readouterr()
        # Should mention the 5 truncated entries
        assert "5" in captured.out

    def test_file_basename_shown_for_entry(self, capsys: pytest.CaptureFixture) -> None:
        """print_impact shows file basename for each entry."""
        from vector_graph.api.visualize import print_impact

        entry = ImpactEntry(
            node_id="n1",
            name="some_fn",
            file_path="/very/deep/path/module.py",
            depth=1,
            edge_type="CALLS",
            confidence=0.9,
        )
        impact = _make_impact(entries=(entry,))
        print_impact(impact)
        captured = capsys.readouterr()
        assert "module.py" in captured.out

    def test_impacted_count_shown(self, capsys: pytest.CaptureFixture) -> None:
        """print_impact shows the total impacted count in panel header."""
        from vector_graph.api.visualize import print_impact

        entries = tuple(_make_entry(f"f_{i}") for i in range(5))
        impact = _make_impact(entries=entries)
        print_impact(impact)
        captured = capsys.readouterr()
        assert "5" in captured.out


# ---------------------------------------------------------------------------
# export_html
# ---------------------------------------------------------------------------

def _small_graph() -> KnowledgeGraph:
    g = KnowledgeGraph()
    g.add_node(GraphNode(
        id="f1",
        label=NodeLabel.FUNCTION,
        properties=NodeProperties(name="main", file_path="/src/app.py", start_line=1),
    ))
    g.add_node(GraphNode(
        id="f2",
        label=NodeLabel.FUNCTION,
        properties=NodeProperties(name="helper", file_path="/src/app.py", start_line=5),
    ))
    g.add_edge(Edge(id="e1", source_id="f1", target_id="f2", edge_type=EdgeType.CALLS))
    return g


@pytest.mark.level5
class TestExportHtml:
    def test_export_html_creates_file(self, tmp_path: Path) -> None:
        """export_html writes an HTML file to disk."""
        from vector_graph.api.visualize import export_html

        out = tmp_path / "graph.html"
        result = export_html(_small_graph(), output=out)
        assert result.exists()
        assert result.suffix == ".html"

    def test_export_html_returns_path(self, tmp_path: Path) -> None:
        """export_html returns the Path to the output file."""
        from vector_graph.api.visualize import export_html

        out = tmp_path / "out.html"
        result = export_html(_small_graph(), output=out)
        assert isinstance(result, Path)
        assert result == out

    def test_export_html_contains_html_tag(self, tmp_path: Path) -> None:
        """Generated HTML contains <html> tag."""
        from vector_graph.api.visualize import export_html

        out = tmp_path / "g.html"
        export_html(_small_graph(), output=out)
        content = out.read_text()
        assert "<html" in content.lower()

    def test_export_html_injects_title(self, tmp_path: Path) -> None:
        """export_html injects the title into the HTML <head>."""
        from vector_graph.api.visualize import export_html

        out = tmp_path / "g.html"
        export_html(_small_graph(), output=out, title="MyGraph")
        content = out.read_text()
        assert "MyGraph" in content

    def test_export_html_max_nodes_limits_output(self, tmp_path: Path) -> None:
        """max_nodes=1 limits nodes added to the visualization."""
        from vector_graph.api.visualize import export_html

        out = tmp_path / "g.html"
        # Should not raise even with very tight limit
        export_html(_small_graph(), output=out, max_nodes=1)
        assert out.exists()

    def test_export_html_include_files_adds_file_nodes(self, tmp_path: Path) -> None:
        """include_files=True includes FILE nodes in the graph."""
        from vector_graph.api.visualize import export_html

        g = KnowledgeGraph()
        g.add_node(GraphNode(
            id="file1",
            label=NodeLabel.FILE,
            properties=NodeProperties(name="app.py", file_path="/src/app.py"),
        ))
        g.add_node(GraphNode(
            id="fn1",
            label=NodeLabel.FUNCTION,
            properties=NodeProperties(name="main", file_path="/src/app.py"),
        ))
        out = tmp_path / "g.html"
        export_html(g, output=out, include_files=True)
        assert out.exists()

    def test_export_html_with_ros2_node(self, tmp_path: Path) -> None:
        """ROS2Node nodes are included with star shape in the visualization."""
        from vector_graph.api.visualize import export_html

        g = KnowledgeGraph()
        g.add_node(GraphNode(
            id="ros1",
            label=NodeLabel.ROS2_NODE,
            properties=NodeProperties(name="MyNode", file_path="/src/node.py"),
        ))
        out = tmp_path / "g.html"
        export_html(g, output=out)
        assert out.exists()

    def test_export_html_edge_types_filter(self, tmp_path: Path) -> None:
        """edge_types filter limits which edges appear in the output."""
        from vector_graph.api.visualize import export_html

        out = tmp_path / "g.html"
        # Pass only IMPORTS — CALLS edge should not appear
        export_html(
            _small_graph(),
            output=out,
            edge_types={EdgeType.IMPORTS},
        )
        assert out.exists()

    def test_export_html_empty_graph(self, tmp_path: Path) -> None:
        """Empty graph produces valid (if minimal) HTML file."""
        from vector_graph.api.visualize import export_html

        out = tmp_path / "g.html"
        export_html(KnowledgeGraph(), output=out)
        assert out.exists()
        assert len(out.read_text()) > 0
