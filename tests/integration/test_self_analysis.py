"""L2 integration tests — vector-graph analyzes itself.

The project root ~/Desktop/vector-graph/ is a real Python project with
many files, so it provides a realistic integration target.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # ~/Desktop/vector-graph/


@pytest.mark.level2
def test_self_analysis_node_count_above_threshold() -> None:
    """Analyzing vector-graph itself yields node_count > 100."""
    from vector_graph.api.python_api import CodeGraph

    cg = CodeGraph(PROJECT_ROOT)
    result = cg.analyze()
    assert result.node_count > 100, (
        f"Expected node_count > 100, got {result.node_count}"
    )


@pytest.mark.level2
def test_self_analysis_function_count_above_threshold() -> None:
    """Analyzing vector-graph itself yields function_count > 50."""
    from vector_graph.api.python_api import CodeGraph

    cg = CodeGraph(PROJECT_ROOT)
    result = cg.analyze()
    assert result.function_count > 50, (
        f"Expected function_count > 50, got {result.function_count}"
    )


@pytest.mark.level2
def test_self_analysis_edge_count_above_threshold() -> None:
    """Analyzing vector-graph itself yields edge_count > 100."""
    from vector_graph.api.python_api import CodeGraph

    cg = CodeGraph(PROJECT_ROOT)
    result = cg.analyze()
    assert result.edge_count > 100, (
        f"Expected edge_count > 100, got {result.edge_count}"
    )


@pytest.mark.level2
def test_self_analysis_impact_knowledge_graph_non_empty() -> None:
    """impact('KnowledgeGraph') returns a non-empty result on the real codebase."""
    from vector_graph.api.python_api import CodeGraph

    cg = CodeGraph(PROJECT_ROOT)
    cg.analyze()
    result = cg.impact("KnowledgeGraph")
    # KnowledgeGraph is a central class — should have callers/callees
    assert result is not None
    assert result.target_name == "KnowledgeGraph"
    assert result.impacted_count > 0, (
        f"Expected non-empty impact for KnowledgeGraph, got {result.impacted_count} entries"
    )


@pytest.mark.level2
def test_self_analysis_orphans_returns_list() -> None:
    """orphans() returns a list (possibly empty) without error."""
    from vector_graph.api.python_api import CodeGraph

    cg = CodeGraph(PROJECT_ROOT)
    cg.analyze()
    result = cg.orphans()
    assert isinstance(result, list)
