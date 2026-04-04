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


@pytest.mark.level2
def test_self_analysis_typed_calls_reduce_global_tier() -> None:
    """AC10: GLOBAL-tier call edges are < 80% of all CALL edges on self-analysis.

    Before v0.3.0 most attribute calls fell to GLOBAL tier.
    After type-inferred resolution dominates, GLOBAL share drops significantly.
    """
    from vector_graph.api.python_api import CodeGraph
    from vector_graph._types import EdgeType

    cg = CodeGraph(PROJECT_ROOT)
    cg.analyze()
    graph = cg._graph
    assert graph is not None

    global_edges = 0
    total_call_edges = 0
    for e in graph.iter_edges():
        if e.edge_type != EdgeType.CALLS:
            continue
        total_call_edges += 1
        if "global" in (e.reason or "").lower():
            global_edges += 1

    # Must have call edges at all
    assert total_call_edges > 0, "Expected at least some CALLS edges"
    global_ratio = global_edges / total_call_edges
    assert global_ratio < 0.80, (
        f"GLOBAL-tier is {global_ratio:.0%} of calls, expected < 80%"
    )


@pytest.mark.level2
def test_self_analysis_query_callers_of_add_node() -> None:
    """AC4: query('callers_of', name='add_node') returns callers from the pipeline."""
    from vector_graph.api.python_api import CodeGraph

    cg = CodeGraph(PROJECT_ROOT)
    cg.analyze()
    result = cg.query("callers_of", name="add_node")
    assert result.count > 0, "add_node should have callers in the pipeline"


@pytest.mark.level2
def test_self_analysis_query_subclasses() -> None:
    """AC4: query('subclasses_of') runs without error and returns a QueryResult."""
    from vector_graph.api.python_api import CodeGraph

    cg = CodeGraph(PROJECT_ROOT)
    cg.analyze()
    # KnowledgeGraph may have subclasses; result may be empty, but must not error
    result = cg.query("subclasses_of", name="FileSystemEventHandler")
    assert result is not None
    assert result.query_type == "subclasses_of"


@pytest.mark.level2
def test_self_analysis_query_by_file() -> None:
    """AC4: query('by_file') returns nodes for pipeline.py."""
    import os

    from vector_graph.api.python_api import CodeGraph

    cg = CodeGraph(PROJECT_ROOT)
    cg.analyze()
    pipeline_path = os.path.join(str(PROJECT_ROOT), "vector_graph", "pipeline.py")
    result = cg.query("by_file", file_path=pipeline_path)
    assert result.count > 0, "pipeline.py should have nodes in the graph"


@pytest.mark.level2
def test_self_analysis_query_by_pattern() -> None:
    """AC4: query('by_pattern', pattern='build_*') finds several functions."""
    from vector_graph.api.python_api import CodeGraph

    cg = CodeGraph(PROJECT_ROOT)
    cg.analyze()
    result = cg.query("by_pattern", pattern="build_*")
    assert result.count > 0, "'build_*' should match at least one function"


@pytest.mark.level2
def test_self_analysis_export_json() -> None:
    """AC5: export('json') produces valid JSON with node/edge counts matching analyze()."""
    import json

    from vector_graph.api.python_api import CodeGraph

    cg = CodeGraph(PROJECT_ROOT)
    analysis = cg.analyze()

    json_str = cg.export("json")
    data = json.loads(json_str)  # must parse without error

    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == analysis.node_count
    assert len(data["edges"]) == analysis.edge_count


@pytest.mark.level2
def test_self_analysis_export_dot() -> None:
    """AC5: export('dot') produces a non-empty DOT string."""
    from vector_graph.api.python_api import CodeGraph

    cg = CodeGraph(PROJECT_ROOT)
    cg.analyze()

    dot_str = cg.export("dot")
    assert dot_str.startswith("digraph")
    assert "}" in dot_str


@pytest.mark.level2
def test_self_analysis_performance() -> None:
    """AC3: Pipeline completes in under 5 seconds for self-analysis."""
    import time

    from vector_graph.pipeline import run_pipeline

    start = time.monotonic()
    run_pipeline(str(PROJECT_ROOT))
    elapsed = time.monotonic() - start

    assert elapsed < 5.0, f"Pipeline took {elapsed:.1f}s, expected < 5s"
