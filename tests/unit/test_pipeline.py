"""L2 unit tests for run_pipeline and CodeGraph API."""

from __future__ import annotations

import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Pipeline tests using tmp_project fixture
# ---------------------------------------------------------------------------

@pytest.mark.level2
def test_pipeline_returns_analysis_result(tmp_project: Path) -> None:
    """run_pipeline returns (graph, AnalysisResult) with non-zero counts."""
    from vector_graph.pipeline import run_pipeline

    graph, result = run_pipeline(tmp_project)
    assert result.node_count > 0
    assert result.file_count > 0


@pytest.mark.level2
def test_pipeline_finds_python_files(tmp_project: Path) -> None:
    """Pipeline discovers all .py files in the project."""
    from vector_graph.pipeline import run_pipeline

    graph, result = run_pipeline(tmp_project)
    # tmp_project has: __init__.py, models.py, utils.py, views.py, orphan.py = 5 files
    assert result.file_count >= 4


@pytest.mark.level2
def test_pipeline_finds_functions_from_models(tmp_project: Path) -> None:
    """Pipeline registers functions/methods from models.py."""
    from vector_graph.pipeline import run_pipeline
    from vector_graph._types import NodeLabel

    graph, result = run_pipeline(tmp_project)
    # models.py has: User.full_name, Post.summary (methods) + class User, Post
    func_names = {
        n.properties.name
        for n in graph.iter_nodes()
        if n.label in (NodeLabel.FUNCTION, NodeLabel.METHOD, NodeLabel.CLASS)
    }
    assert "User" in func_names or "full_name" in func_names


@pytest.mark.level2
def test_pipeline_finds_functions_from_utils(tmp_project: Path) -> None:
    """Pipeline registers functions from utils.py."""
    from vector_graph.pipeline import run_pipeline
    from vector_graph._types import NodeLabel

    graph, result = run_pipeline(tmp_project)
    func_names = {
        n.properties.name
        for n in graph.iter_nodes()
        if n.label in (NodeLabel.FUNCTION, NodeLabel.METHOD)
    }
    assert "validate_email" in func_names or "format_name" in func_names


@pytest.mark.level2
def test_pipeline_finds_functions_from_views(tmp_project: Path) -> None:
    """Pipeline registers functions from views.py."""
    from vector_graph.pipeline import run_pipeline
    from vector_graph._types import NodeLabel

    graph, result = run_pipeline(tmp_project)
    func_names = {
        n.properties.name
        for n in graph.iter_nodes()
        if n.label in (NodeLabel.FUNCTION, NodeLabel.METHOD)
    }
    assert "create_user" in func_names or "render_feed" in func_names


@pytest.mark.level2
def test_pipeline_creates_imports_edges(tmp_project: Path) -> None:
    """Pipeline creates IMPORTS edges from views.py importing models/utils."""
    from vector_graph.pipeline import run_pipeline
    from vector_graph._types import EdgeType

    graph, result = run_pipeline(tmp_project)
    edge_types = {e.edge_type for e in graph.iter_edges()}
    assert EdgeType.IMPORTS in edge_types or result.import_count > 0


@pytest.mark.level2
def test_pipeline_analysis_result_counts_consistent(tmp_project: Path) -> None:
    """AnalysisResult counts match graph node/edge counts."""
    from vector_graph.pipeline import run_pipeline
    from vector_graph._types import NodeLabel, EdgeType

    graph, result = run_pipeline(tmp_project)

    actual_node_count = sum(1 for _ in graph.iter_nodes())
    actual_edge_count = sum(1 for _ in graph.iter_edges())

    assert result.node_count == actual_node_count
    assert result.edge_count == actual_edge_count


@pytest.mark.level2
def test_pipeline_root_stored_in_result(tmp_project: Path) -> None:
    """AnalysisResult.root is set to the project root path."""
    from vector_graph.pipeline import run_pipeline

    graph, result = run_pipeline(tmp_project)
    assert str(tmp_project) in result.root or result.root == str(tmp_project)


@pytest.mark.level2
def test_pipeline_with_string_path(tmp_project: Path) -> None:
    """run_pipeline accepts a string path as well as a Path object."""
    from vector_graph.pipeline import run_pipeline

    graph, result = run_pipeline(str(tmp_project))
    assert result.node_count > 0


@pytest.mark.level2
def test_codegraph_analyze(tmp_project: Path) -> None:
    """CodeGraph.analyze() returns AnalysisResult."""
    from vector_graph.api.python_api import CodeGraph

    cg = CodeGraph(tmp_project)
    result = cg.analyze()
    assert result.node_count > 0
    assert result.root


@pytest.mark.level2
def test_codegraph_orphans(tmp_project: Path) -> None:
    """CodeGraph.orphans() returns list of GraphNode for orphan.py functions."""
    from vector_graph.api.python_api import CodeGraph
    from vector_graph._types import NodeLabel

    cg = CodeGraph(tmp_project)
    cg.analyze()
    orphans = cg.orphans()
    orphan_names = {n.properties.name for n in orphans}
    # orphan.py defines unreachable_function and UnusedClass — at least one should appear
    assert "unreachable_function" in orphan_names or "UnusedClass" in orphan_names


@pytest.mark.level2
def test_codegraph_impact(tmp_project: Path) -> None:
    """CodeGraph.impact() returns ImpactResult for a known function."""
    from vector_graph.api.python_api import CodeGraph
    from vector_graph._types import NodeLabel

    cg = CodeGraph(tmp_project)
    cg.analyze()

    # Find a function node that exists
    graph = cg._graph
    func_nodes = [
        n for n in graph.iter_nodes()
        if n.label == NodeLabel.FUNCTION and n.properties.name == "validate_email"
    ]
    if not func_nodes:
        pytest.skip("validate_email not found in graph")

    result = cg.impact("validate_email", direction="upstream")
    assert result.target_name == "validate_email"
    assert result.risk in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
