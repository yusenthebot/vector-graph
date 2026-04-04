"""L4 unit tests for GraphWatcher (file watcher + incremental graph update).

TDD — RED phase: all tests written before implementation.

Uses tmp_path fixture with actual filesystem writes to trigger watchdog events.
Short sleeps (0.5s) give the watcher thread time to propagate changes.
"""

from __future__ import annotations

import time
import threading
from pathlib import Path

import pytest

from vector_graph.graph.knowledge_graph import KnowledgeGraph
from vector_graph.watch.file_watcher import GraphWatcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SETTLE = 0.6  # seconds — time to wait after a filesystem event


def _node_names(graph: KnowledgeGraph, file_path: str) -> set[str]:
    """Return the set of node names belonging to file_path."""
    return {n.properties.name for n in graph.get_nodes_by_file(file_path)}


def _wait(seconds: float = _SETTLE) -> None:
    time.sleep(seconds)


# ---------------------------------------------------------------------------
# L4 tests
# ---------------------------------------------------------------------------

@pytest.mark.level4
def test_watcher_starts_and_stops(tmp_path: Path) -> None:
    """GraphWatcher starts without error and stops cleanly."""
    graph = KnowledgeGraph()
    watcher = GraphWatcher(root=tmp_path, graph=graph)
    watcher.start()
    _wait(0.1)
    watcher.stop()  # must not raise


@pytest.mark.level4
def test_watcher_stop_is_idempotent(tmp_path: Path) -> None:
    """Calling stop() twice does not raise."""
    graph = KnowledgeGraph()
    watcher = GraphWatcher(root=tmp_path, graph=graph)
    watcher.start()
    watcher.stop()
    watcher.stop()  # second call — must not raise


@pytest.mark.level4
def test_file_create_adds_nodes(tmp_path: Path) -> None:
    """Creating a .py file causes its symbols to appear in the graph."""
    graph = KnowledgeGraph()
    watcher = GraphWatcher(root=tmp_path, graph=graph, debounce_sec=0.1)
    watcher.start()

    py_file = tmp_path / "new_module.py"
    py_file.write_text(
        "def hello() -> None:\n    pass\n\nclass World:\n    pass\n"
    )
    _wait()

    watcher.stop()

    node_names = _node_names(graph, str(py_file))
    assert "hello" in node_names
    assert "World" in node_names


@pytest.mark.level4
def test_file_modify_updates_nodes(tmp_path: Path) -> None:
    """Modifying a .py file removes stale nodes and adds new ones."""
    py_file = tmp_path / "mod_module.py"
    py_file.write_text("def old_func() -> None:\n    pass\n")

    graph = KnowledgeGraph()
    watcher = GraphWatcher(root=tmp_path, graph=graph, debounce_sec=0.1)
    watcher.start()
    _wait()  # let initial scan settle (watcher does not do initial scan; file existed before start)

    # Overwrite with new content
    py_file.write_text("def new_func() -> None:\n    pass\n")
    _wait()

    watcher.stop()

    node_names = _node_names(graph, str(py_file))
    assert "new_func" in node_names
    assert "old_func" not in node_names


@pytest.mark.level4
def test_file_delete_removes_nodes(tmp_path: Path) -> None:
    """Deleting a .py file removes all its nodes from the graph."""
    py_file = tmp_path / "del_module.py"
    py_file.write_text("def to_delete() -> None:\n    pass\n")

    graph = KnowledgeGraph()
    watcher = GraphWatcher(root=tmp_path, graph=graph, debounce_sec=0.1)
    watcher.start()

    # First create the file so nodes exist — trigger a modify event
    py_file.write_text("def to_delete() -> None:\n    pass\n")
    _wait()

    assert "to_delete" in _node_names(graph, str(py_file))

    py_file.unlink()
    _wait()

    watcher.stop()

    node_names = _node_names(graph, str(py_file))
    assert "to_delete" not in node_names
    assert len(node_names) == 0


@pytest.mark.level4
def test_non_python_files_ignored(tmp_path: Path) -> None:
    """Non-.py files (e.g. .txt, .md) do not trigger graph updates."""
    graph = KnowledgeGraph()
    watcher = GraphWatcher(root=tmp_path, graph=graph, debounce_sec=0.1)
    watcher.start()

    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("hello world")
    md_file = tmp_path / "README.md"
    md_file.write_text("# readme")
    _wait()

    watcher.stop()

    assert graph.node_count == 0


@pytest.mark.level4
def test_callback_called_on_change(tmp_path: Path) -> None:
    """Registered callback is invoked when a .py file changes."""
    graph = KnowledgeGraph()
    watcher = GraphWatcher(root=tmp_path, graph=graph, debounce_sec=0.1)

    events: list[tuple[str, str]] = []

    def _on_change(file_path: str, event_type: str) -> None:
        events.append((file_path, event_type))

    watcher.on_change(_on_change)
    watcher.start()

    py_file = tmp_path / "callback_test.py"
    py_file.write_text("x = 1\n")
    _wait()

    watcher.stop()

    assert len(events) >= 1
    paths = [e[0] for e in events]
    assert str(py_file) in paths


@pytest.mark.level4
def test_callback_receives_event_type(tmp_path: Path) -> None:
    """Callback receives a non-empty event_type string."""
    graph = KnowledgeGraph()
    watcher = GraphWatcher(root=tmp_path, graph=graph, debounce_sec=0.1)

    event_types: list[str] = []

    def _on_change(file_path: str, event_type: str) -> None:
        event_types.append(event_type)

    watcher.on_change(_on_change)
    watcher.start()

    py_file = tmp_path / "ev_type_test.py"
    py_file.write_text("y = 2\n")
    _wait()

    watcher.stop()

    assert len(event_types) >= 1
    assert all(isinstance(et, str) and len(et) > 0 for et in event_types)


@pytest.mark.level4
def test_multiple_callbacks_all_called(tmp_path: Path) -> None:
    """Multiple registered callbacks are all invoked on change."""
    graph = KnowledgeGraph()
    watcher = GraphWatcher(root=tmp_path, graph=graph, debounce_sec=0.1)

    results_a: list[str] = []
    results_b: list[str] = []

    watcher.on_change(lambda fp, et: results_a.append(fp))
    watcher.on_change(lambda fp, et: results_b.append(fp))
    watcher.start()

    py_file = tmp_path / "multi_cb.py"
    py_file.write_text("z = 3\n")
    _wait()

    watcher.stop()

    assert len(results_a) >= 1
    assert len(results_b) >= 1


@pytest.mark.level4
def test_debounce_rapid_changes_single_update(tmp_path: Path) -> None:
    """Rapid successive writes to the same file trigger only one update."""
    graph = KnowledgeGraph()
    # Use a longer debounce so rapid writes collapse
    watcher = GraphWatcher(root=tmp_path, graph=graph, debounce_sec=0.3)

    call_count = 0
    lock = threading.Lock()

    def _on_change(file_path: str, event_type: str) -> None:
        nonlocal call_count
        with lock:
            call_count += 1

    watcher.on_change(_on_change)
    watcher.start()

    py_file = tmp_path / "debounce_test.py"
    # Write 5 times in rapid succession within debounce window
    for i in range(5):
        py_file.write_text(f"x = {i}\n")
        time.sleep(0.02)

    # Wait well past debounce period for flush
    time.sleep(0.6)
    watcher.stop()

    # Debounce should collapse rapid writes: expect far fewer calls than 5
    assert call_count <= 3


@pytest.mark.level4
def test_watches_subdirectories_recursively(tmp_path: Path) -> None:
    """Watcher detects changes in nested subdirectories."""
    sub = tmp_path / "subdir" / "nested"
    sub.mkdir(parents=True)

    graph = KnowledgeGraph()
    watcher = GraphWatcher(root=tmp_path, graph=graph, debounce_sec=0.1)
    watcher.start()

    py_file = sub / "deep_module.py"
    py_file.write_text("def deep_fn() -> None:\n    pass\n")
    _wait()

    watcher.stop()

    node_names = _node_names(graph, str(py_file))
    assert "deep_fn" in node_names


@pytest.mark.level4
def test_no_crash_on_parse_error(tmp_path: Path) -> None:
    """Watcher continues running when a malformed .py file is written."""
    graph = KnowledgeGraph()
    watcher = GraphWatcher(root=tmp_path, graph=graph, debounce_sec=0.1)
    watcher.start()

    bad_file = tmp_path / "bad_syntax.py"
    bad_file.write_text("def (: broken syntax!!!\n")
    _wait()

    # Write a valid file after the bad one — watcher must still work
    good_file = tmp_path / "good_module.py"
    good_file.write_text("def ok_func() -> None:\n    pass\n")
    _wait()

    watcher.stop()

    # Bad file: empty result, no crash
    assert len(_node_names(graph, str(bad_file))) == 0
    # Good file: parsed correctly
    assert "ok_func" in _node_names(graph, str(good_file))


@pytest.mark.level4
def test_graph_thread_safety(tmp_path: Path) -> None:
    """Concurrent file writes do not corrupt the graph (no exceptions)."""
    graph = KnowledgeGraph()
    watcher = GraphWatcher(root=tmp_path, graph=graph, debounce_sec=0.05)
    watcher.start()

    errors: list[Exception] = []

    def _write_files() -> None:
        try:
            for i in range(10):
                f = tmp_path / f"concurrent_{i}.py"
                f.write_text(f"def fn_{i}() -> None:\n    pass\n")
                time.sleep(0.01)
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=_write_files)
    thread.start()
    thread.join(timeout=5.0)

    _wait(0.5)
    watcher.stop()

    assert errors == [], f"Errors during concurrent writes: {errors}"


@pytest.mark.level4
def test_file_modify_replaces_not_accumulates(tmp_path: Path) -> None:
    """After modify, the graph has exactly the new file's nodes, not old+new."""
    py_file = tmp_path / "replace_test.py"

    graph = KnowledgeGraph()
    watcher = GraphWatcher(root=tmp_path, graph=graph, debounce_sec=0.1)
    watcher.start()

    py_file.write_text("def alpha() -> None:\n    pass\n")
    _wait()

    py_file.write_text("def beta() -> None:\n    pass\n")
    _wait()

    watcher.stop()

    node_names = _node_names(graph, str(py_file))
    assert "beta" in node_names
    # alpha must NOT be in the graph (replaced, not accumulated)
    assert "alpha" not in node_names


@pytest.mark.level4
def test_watcher_handles_empty_python_file(tmp_path: Path) -> None:
    """An empty .py file does not crash the watcher and results in no nodes."""
    graph = KnowledgeGraph()
    watcher = GraphWatcher(root=tmp_path, graph=graph, debounce_sec=0.1)
    watcher.start()

    empty_file = tmp_path / "empty.py"
    empty_file.write_text("")
    _wait()

    watcher.stop()

    node_names = _node_names(graph, str(empty_file))
    assert len(node_names) == 0


# ---------------------------------------------------------------------------
# Edge rebuild tests (T7) — use _process_event directly (no filesystem watcher)
# to test deterministically without sleeps.
# ---------------------------------------------------------------------------

def _build_two_file_graph(
    file_a_path: str,
    file_b_path: str,
    source_a: str,
    source_b: str,
    root: str,
) -> tuple:
    """Bootstrap a KnowledgeGraph + GraphWatcher state from two in-memory files.

    Returns (graph, watcher, parse_results, symbol_table, resolution, all_files).
    This helper does NOT use watchdog — it calls pipeline internals directly so
    tests run fast and deterministically.
    """
    from vector_graph.graph.symbol_table import SymbolTable
    from vector_graph.graph.resolution import ResolutionContext
    from vector_graph.pipeline import (
        _phase1_create_file_nodes,
        _phase2_parse_files,
        _phase3_register_symbols,
        _phase4_resolve_imports,
    )
    from vector_graph.parse.python_parser import parse_file

    graph = KnowledgeGraph()
    symbol_table = SymbolTable()
    resolution = ResolutionContext(symbol_table)

    # Simulate parse_file with in-memory source
    parse_results = {
        file_a_path: parse_file(file_a_path, source=source_a),
        file_b_path: parse_file(file_b_path, source=source_b),
    }
    all_files = set(parse_results.keys())

    _phase1_create_file_nodes(graph, list(all_files))
    _phase3_register_symbols(graph, symbol_table, parse_results)
    _phase4_resolve_imports(graph, resolution, parse_results, all_files, root)

    watcher = GraphWatcher.from_pipeline(
        root=root,
        graph=graph,
        symbol_table=symbol_table,
        resolution=resolution,
        parse_results=parse_results,
    )

    return graph, watcher, parse_results, symbol_table, resolution, all_files


def test_incremental_single_file_edges_rebuilt(tmp_path: Path) -> None:
    """After modifying a file, IMPORTS edge from that file is rebuilt."""
    root = str(tmp_path)
    file_a = str(tmp_path / "file_a.py")
    file_b = str(tmp_path / "file_b.py")

    # file_a imports file_b
    source_a = "from file_b import bar\n\ndef foo() -> None:\n    pass\n"
    source_b = "def bar() -> None:\n    pass\n"

    graph, watcher, parse_results, symbol_table, resolution, all_files = (
        _build_two_file_graph(file_a, file_b, source_a, source_b, root)
    )

    # Confirm initial IMPORTS edge exists
    from vector_graph._types import EdgeType
    imports_edges_before = [
        e for e in graph.iter_edges()
        if e.edge_type == EdgeType.IMPORTS
    ]
    assert len(imports_edges_before) >= 1, "Expected initial IMPORTS edge"

    # Simulate a file_a modify — same import still present
    source_a_v2 = "from file_b import bar\n\ndef foo_v2() -> None:\n    pass\n"
    watcher._process_event_with_source(file_a, "modified", source_a_v2)

    # IMPORTS edge from file_a to file_b must still exist after rebuild
    from vector_graph._types import EdgeType
    imports_edges_after = [
        e for e in graph.iter_edges()
        if e.edge_type == EdgeType.IMPORTS
    ]
    assert len(imports_edges_after) >= 1, "IMPORTS edge must be rebuilt after file modify"


def test_incremental_preserves_other_file_nodes(tmp_path: Path) -> None:
    """Nodes from untouched file_b remain unchanged when file_a is modified."""
    root = str(tmp_path)
    file_a = str(tmp_path / "file_a.py")
    file_b = str(tmp_path / "file_b.py")

    source_a = "def foo() -> None:\n    pass\n"
    source_b = "def bar() -> None:\n    pass\n\nclass Baz:\n    pass\n"

    graph, watcher, _, _, _, _ = _build_two_file_graph(
        file_a, file_b, source_a, source_b, root
    )

    nodes_b_before = {n.id for n in graph.get_nodes_by_file(file_b)}
    assert len(nodes_b_before) >= 2, "Expected bar and Baz nodes in file_b"

    # Modify file_a — file_b must be untouched
    source_a_v2 = "def foo_new() -> None:\n    pass\n"
    watcher._process_event_with_source(file_a, "modified", source_a_v2)

    nodes_b_after = {n.id for n in graph.get_nodes_by_file(file_b)}
    assert nodes_b_before == nodes_b_after, "file_b nodes must be unchanged"


def test_incremental_handles_delete_removes_edges(tmp_path: Path) -> None:
    """Deleted file's IMPORTS and CALLS edges are fully removed."""
    root = str(tmp_path)
    file_a = str(tmp_path / "file_a.py")
    file_b = str(tmp_path / "file_b.py")

    source_a = "from file_b import bar\n\ndef foo() -> None:\n    pass\n"
    source_b = "def bar() -> None:\n    pass\n"

    graph, watcher, _, _, _, _ = _build_two_file_graph(
        file_a, file_b, source_a, source_b, root
    )

    from vector_graph._types import EdgeType
    edges_before = list(graph.iter_edges())
    assert any(e.edge_type == EdgeType.IMPORTS for e in edges_before)

    # Process delete for file_a
    watcher._process_event(file_a, "deleted")

    # No edges should reference file_a's (now-gone) nodes
    remaining_node_ids = {n.id for n in graph.iter_nodes()}
    for edge in graph.iter_edges():
        assert edge.source_id in remaining_node_ids, (
            f"Edge {edge.id} references deleted source {edge.source_id}"
        )
        assert edge.target_id in remaining_node_ids, (
            f"Edge {edge.id} references deleted target {edge.target_id}"
        )


def test_incremental_handles_new_file_imports_edge(tmp_path: Path) -> None:
    """When a new file is added that imports an existing file, IMPORTS edge is created."""
    root = str(tmp_path)
    file_a = str(tmp_path / "file_a.py")
    file_b = str(tmp_path / "file_b.py")

    # Start: only file_b exists in the graph
    source_b = "def bar() -> None:\n    pass\n"
    from vector_graph.graph.symbol_table import SymbolTable
    from vector_graph.graph.resolution import ResolutionContext
    from vector_graph.pipeline import (
        _phase1_create_file_nodes,
        _phase3_register_symbols,
        _phase4_resolve_imports,
    )
    from vector_graph.parse.python_parser import parse_file

    graph = KnowledgeGraph()
    symbol_table = SymbolTable()
    resolution = ResolutionContext(symbol_table)

    parse_results = {file_b: parse_file(file_b, source=source_b)}
    all_files = {file_b}

    _phase1_create_file_nodes(graph, [file_b])
    _phase3_register_symbols(graph, symbol_table, parse_results)
    _phase4_resolve_imports(graph, resolution, parse_results, all_files, root)

    watcher = GraphWatcher.from_pipeline(
        root=root,
        graph=graph,
        symbol_table=symbol_table,
        resolution=resolution,
        parse_results=parse_results,
    )

    # Add file_a that imports from file_b
    source_a = "from file_b import bar\n\ndef foo() -> None:\n    pass\n"
    watcher._process_event_with_source(file_a, "created", source_a)

    from vector_graph._types import EdgeType
    imports_edges = [e for e in graph.iter_edges() if e.edge_type == EdgeType.IMPORTS]
    assert len(imports_edges) >= 1, "IMPORTS edge must be created for new file importing existing"


def test_incremental_remove_edge_method(tmp_path: Path) -> None:
    """KnowledgeGraph.remove_edge removes the edge and cleans up adjacency indexes."""
    from vector_graph._types import Edge, EdgeType

    graph = KnowledgeGraph()
    from vector_graph._types import GraphNode, NodeLabel, NodeProperties

    node_a = GraphNode(
        id="node_a",
        label=NodeLabel.FUNCTION,
        properties=NodeProperties(name="a", file_path="/fake/a.py"),
    )
    node_b = GraphNode(
        id="node_b",
        label=NodeLabel.FUNCTION,
        properties=NodeProperties(name="b", file_path="/fake/b.py"),
    )
    graph.add_node(node_a)
    graph.add_node(node_b)

    edge = Edge(id="edge_1", source_id="node_a", target_id="node_b",
                edge_type=EdgeType.CALLS, confidence=0.9)
    graph.add_edge(edge)
    assert graph.edge_count == 1

    graph.remove_edge("edge_1")
    assert graph.edge_count == 0

    # Adjacency indexes cleaned
    assert list(graph.get_edges_from("node_a")) == []
    assert list(graph.get_edges_to("node_b")) == []

    # Idempotent — second remove must not raise
    graph.remove_edge("edge_1")


@pytest.mark.level4
def test_delete_event_type_in_callback(tmp_path: Path) -> None:
    """Callback event_type for deletion contains 'deleted' or 'delete'."""
    py_file = tmp_path / "del_cb.py"
    py_file.write_text("def gone() -> None:\n    pass\n")

    graph = KnowledgeGraph()
    watcher = GraphWatcher(root=tmp_path, graph=graph, debounce_sec=0.1)

    # First get nodes into graph
    py_file.write_text("def gone() -> None:\n    pass\n")

    delete_events: list[tuple[str, str]] = []

    def _on_change(fp: str, et: str) -> None:
        if "delet" in et.lower():
            delete_events.append((fp, et))

    watcher.on_change(_on_change)
    watcher.start()

    # Trigger modify so nodes exist
    py_file.write_text("def gone() -> None:\n    pass\n")
    _wait()

    py_file.unlink()
    _wait()

    watcher.stop()

    assert len(delete_events) >= 1
    assert str(py_file) in [e[0] for e in delete_events]
