"""Unit tests for ChangeTracker (TDD — written before implementation)."""

from __future__ import annotations

import json
import time

import pytest

from vector_graph._types import (
    Edge,
    EdgeType,
    GraphNode,
    NodeLabel,
    NodeProperties,
)
from vector_graph.graph.knowledge_graph import KnowledgeGraph
from vector_graph.watch.change_tracker import ChangeEvent, ChangeTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_graph() -> KnowledgeGraph:
    return KnowledgeGraph()


def _add_function(
    graph: KnowledgeGraph,
    name: str,
    file_path: str,
    node_id: str,
    start_line: int = 1,
    end_line: int = 10,
    parameters: tuple[str, ...] = (),
    return_type: str | None = None,
    decorators: tuple[str, ...] = (),
) -> GraphNode:
    props = NodeProperties(
        name=name,
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        parameters=parameters,
        parameter_count=len(parameters),
        return_type=return_type,
        decorators=decorators,
    )
    node = GraphNode(id=node_id, label=NodeLabel.FUNCTION, properties=props)
    graph.add_node(node)
    return node


def _add_class(graph: KnowledgeGraph, name: str, file_path: str, node_id: str) -> GraphNode:
    props = NodeProperties(name=name, file_path=file_path, start_line=1, end_line=20)
    node = GraphNode(id=node_id, label=NodeLabel.CLASS, properties=props)
    graph.add_node(node)
    return node


def _add_file_node(graph: KnowledgeGraph, file_path: str, node_id: str) -> GraphNode:
    props = NodeProperties(name=file_path.split("/")[-1], file_path=file_path)
    node = GraphNode(id=node_id, label=NodeLabel.FILE, properties=props)
    graph.add_node(node)
    return node


# ---------------------------------------------------------------------------
# T1: test_change_tracker_records_modification
# ---------------------------------------------------------------------------

class TestChangeTrackerRecordsModification:
    def test_unchanged_function_not_in_modified(self) -> None:
        """If function signature didn't change, it's NOT in nodes_modified."""
        graph = _make_graph()
        file_path = "/project/foo.py"
        _add_function(graph, "bar", file_path, "fn1")

        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)

        # Graph still has bar with same signature — no real modification
        event = tracker.record_change(file_path, "modified")

        assert event.change_type == "modified"
        assert event.file_path == file_path
        # bar did NOT actually change (same signature) — should not be in modified
        assert "bar" not in event.nodes_modified
        assert len(event.nodes_modified) == 0

    def test_modified_when_signature_changes(self) -> None:
        """Function appears in nodes_modified when its signature actually changes."""
        graph = _make_graph()
        file_path = "/project/foo.py"
        _add_function(graph, "bar", file_path, "fn1", parameters=("x",), end_line=10)

        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)

        # Simulate re-parse: remove old node, add new one with different signature
        graph.remove_nodes_by_file(file_path)
        _add_function(graph, "bar", file_path, "fn1_v2", parameters=("x", "y"), end_line=15)

        event = tracker.record_change(file_path, "modified")
        assert "bar" in event.nodes_modified
        assert "fn1_v2" in event.node_ids_modified

    def test_modification_event_has_timestamp(self) -> None:
        graph = _make_graph()
        file_path = "/project/foo.py"
        _add_function(graph, "func_x", file_path, "fn2")
        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)
        before = time.time()
        event = tracker.record_change(file_path, "modified")
        after = time.time()
        assert before <= event.timestamp <= after

    def test_modification_event_stored_in_buffer(self) -> None:
        graph = _make_graph()
        file_path = "/project/foo.py"
        _add_function(graph, "my_func", file_path, "fn3")
        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)
        tracker.record_change(file_path, "modified")
        events = tracker.get_events(limit=10)
        assert len(events) == 1
        assert events[0].change_type == "modified"


# ---------------------------------------------------------------------------
# T2: test_change_tracker_records_addition
# ---------------------------------------------------------------------------

class TestChangeTrackerRecordsAddition:
    def test_nodes_added_when_new_functions_appear(self) -> None:
        """Snapshot empty file, then graph gets new function — it appears in nodes_added."""
        graph = _make_graph()
        file_path = "/project/new_file.py"
        tracker = ChangeTracker(graph)
        # Snapshot when file has NO nodes
        tracker.snapshot_file(file_path)
        # Now add a function to the graph (simulating parse result applied)
        _add_function(graph, "new_func", file_path, "fn_new")
        event = tracker.record_change(file_path, "created")

        assert event.change_type == "created"
        assert "new_func" in event.nodes_added
        assert len(event.nodes_removed) == 0

    def test_node_ids_added_populated(self) -> None:
        """node_ids_added contains the actual graph node IDs."""
        graph = _make_graph()
        file_path = "/project/new_file.py"
        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)
        _add_function(graph, "new_func", file_path, "fn_new")
        event = tracker.record_change(file_path, "created")
        assert "fn_new" in event.node_ids_added

    def test_multiple_nodes_added(self) -> None:
        graph = _make_graph()
        file_path = "/project/module.py"
        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)
        _add_function(graph, "alpha", file_path, "f1")
        _add_function(graph, "beta", file_path, "f2")
        _add_class(graph, "Gamma", file_path, "c1")
        event = tracker.record_change(file_path, "created")
        assert set(event.nodes_added) == {"alpha", "beta", "Gamma"}
        assert set(event.node_ids_added) == {"f1", "f2", "c1"}

    def test_file_nodes_excluded_from_added(self) -> None:
        """FILE and FOLDER nodes should not appear in nodes_added."""
        graph = _make_graph()
        file_path = "/project/module.py"
        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)
        _add_file_node(graph, file_path, "file1")
        _add_function(graph, "visible_fn", file_path, "fn_vis")
        event = tracker.record_change(file_path, "created")
        # file node name should NOT be in nodes_added
        names = set(event.nodes_added)
        assert "visible_fn" in names
        # The file node (basename of path) must not show up
        assert "module.py" not in names


# ---------------------------------------------------------------------------
# T3: test_change_tracker_records_deletion
# ---------------------------------------------------------------------------

class TestChangeTrackerRecordsDeletion:
    def test_nodes_removed_on_delete(self) -> None:
        """Snapshot file with functions, then delete → nodes_removed contains them."""
        graph = _make_graph()
        file_path = "/project/old.py"
        _add_function(graph, "stale_fn", file_path, "fn_stale")
        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)
        # Simulate file deletion — remove nodes from graph
        graph.remove_nodes_by_file(file_path)
        event = tracker.record_change(file_path, "deleted")

        assert event.change_type == "deleted"
        assert "stale_fn" in event.nodes_removed
        assert len(event.nodes_added) == 0

    def test_node_ids_removed_populated(self) -> None:
        """node_ids_removed contains the old node IDs from before deletion."""
        graph = _make_graph()
        file_path = "/project/old.py"
        _add_function(graph, "stale_fn", file_path, "fn_stale")
        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)
        graph.remove_nodes_by_file(file_path)
        event = tracker.record_change(file_path, "deleted")
        assert "fn_stale" in event.node_ids_removed

    def test_nodes_added_empty_on_delete(self) -> None:
        graph = _make_graph()
        file_path = "/project/gone.py"
        _add_function(graph, "fn", file_path, "fn_d1")
        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)
        graph.remove_nodes_by_file(file_path)
        event = tracker.record_change(file_path, "deleted")
        assert len(event.nodes_added) == 0
        assert len(event.node_ids_added) == 0


# ---------------------------------------------------------------------------
# T4: test_change_tracker_computes_impact
# ---------------------------------------------------------------------------

class TestChangeTrackerComputesImpact:
    def test_event_has_risk_field(self) -> None:
        """ChangeEvent always has a 'risk' field that is one of the known levels."""
        graph = _make_graph()
        file_path = "/project/a.py"
        _add_function(graph, "fn_a", file_path, "fn_a1")
        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)
        event = tracker.record_change(file_path, "modified")
        assert event.risk in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

    def test_event_has_affected_count(self) -> None:
        graph = _make_graph()
        file_path = "/project/b.py"
        _add_function(graph, "fn_b", file_path, "fn_b1")
        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)
        event = tracker.record_change(file_path, "modified")
        assert isinstance(event.affected_count, int)
        assert event.affected_count >= 0

    def test_isolated_node_has_low_risk(self) -> None:
        """A node with no callers should produce LOW risk."""
        graph = _make_graph()
        file_path = "/project/isolated.py"
        _add_function(graph, "lonely", file_path, "fn_lonely")
        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)
        event = tracker.record_change(file_path, "modified")
        assert event.risk == "LOW"
        assert event.affected_count == 0


# ---------------------------------------------------------------------------
# T5: test_change_tracker_ring_buffer_cap
# ---------------------------------------------------------------------------

class TestChangeTrackerRingBufferCap:
    def test_max_500_events_retained(self) -> None:
        """Adding 600 events to the tracker should retain only the newest 500."""
        graph = _make_graph()
        tracker = ChangeTracker(graph)
        for i in range(600):
            file_path = f"/project/f{i}.py"
            _add_function(graph, f"fn_{i}", file_path, f"fn_id_{i}")
            tracker.snapshot_file(file_path)
            tracker.record_change(file_path, "modified")
        # Should be capped at 500
        events = tracker.get_events(limit=1000)
        assert len(events) == 500

    def test_oldest_events_dropped(self) -> None:
        """After cap, the first-added events should be gone."""
        graph = _make_graph()
        tracker = ChangeTracker(graph)
        # Add exactly MAX+1 events so first one is dropped
        for i in range(501):
            file_path = f"/project/file_{i}.py"
            _add_function(graph, f"func_{i}", file_path, f"fid_{i}")
            tracker.snapshot_file(file_path)
            tracker.record_change(file_path, "modified")
        events = tracker.get_events(limit=1000)
        assert len(events) == 500
        # The oldest file path should no longer appear
        file_paths_in_events = {e.file_path for e in events}
        assert "/project/file_0.py" not in file_paths_in_events


# ---------------------------------------------------------------------------
# T6: test_change_tracker_session_summary
# ---------------------------------------------------------------------------

class TestChangeTrackerSessionSummary:
    def test_summary_correct_totals(self) -> None:
        """Session summary counts added/removed/modified nodes correctly."""
        graph = _make_graph()
        tracker = ChangeTracker(graph)

        # Event 1: create file with 2 functions
        fp1 = "/project/a.py"
        tracker.snapshot_file(fp1)
        _add_function(graph, "fn1", fp1, "e1_fn1")
        _add_function(graph, "fn2", fp1, "e1_fn2")
        tracker.record_change(fp1, "created")

        # Event 2: delete file
        fp2 = "/project/b.py"
        _add_function(graph, "old_fn", fp2, "e2_fn1")
        tracker.snapshot_file(fp2)
        graph.remove_nodes_by_file(fp2)
        tracker.record_change(fp2, "deleted")

        summary = tracker.session_summary()
        assert summary["event_count"] == 2
        assert summary["files_changed"] == 2
        assert summary["nodes_added"] == 2
        assert summary["nodes_removed"] == 1

    def test_summary_high_risk_count(self) -> None:
        """high_risk_changes counts events with risk HIGH or CRITICAL."""
        graph = _make_graph()
        tracker = ChangeTracker(graph)
        # We can't easily force HIGH risk without complex graph setup,
        # but we can verify the field exists and is an integer.
        fp = "/project/x.py"
        tracker.snapshot_file(fp)
        tracker.record_change(fp, "modified")
        summary = tracker.session_summary()
        assert "high_risk_changes" in summary
        assert isinstance(summary["high_risk_changes"], int)


# ---------------------------------------------------------------------------
# T7: test_change_tracker_empty_session
# ---------------------------------------------------------------------------

class TestChangeTrackerEmptySession:
    def test_empty_summary(self) -> None:
        """No changes → session summary has all zeros."""
        graph = _make_graph()
        tracker = ChangeTracker(graph)
        summary = tracker.session_summary()
        assert summary["event_count"] == 0
        assert summary["files_changed"] == 0
        assert summary["nodes_added"] == 0
        assert summary["nodes_modified"] == 0
        assert summary["nodes_removed"] == 0
        assert summary["high_risk_changes"] == 0
        assert summary["groups_affected"] == []

    def test_empty_get_events(self) -> None:
        graph = _make_graph()
        tracker = ChangeTracker(graph)
        assert tracker.get_events() == []


# ---------------------------------------------------------------------------
# T8: test_change_event_json_serializable
# ---------------------------------------------------------------------------

class TestChangeEventJsonSerializable:
    def test_to_dict_returns_valid_json(self) -> None:
        """ChangeEvent.to_dict() must be JSON serializable."""
        graph = _make_graph()
        file_path = "/project/ser.py"
        _add_function(graph, "serialize_me", file_path, "fn_ser")
        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)
        event = tracker.record_change(file_path, "modified")

        d = event.to_dict()
        # Must not raise
        serialized = json.dumps(d)
        restored = json.loads(serialized)
        assert restored["file"] == file_path
        assert restored["type"] == "modified"
        assert "nodes_added" in restored
        assert "nodes_modified" in restored
        assert "nodes_removed" in restored
        assert "node_ids_added" in restored
        assert "node_ids_modified" in restored
        assert "node_ids_removed" in restored
        assert "impact" in restored

    def test_to_dict_impact_fields(self) -> None:
        graph = _make_graph()
        file_path = "/project/impact_test.py"
        _add_function(graph, "fn_impact", file_path, "fn_imp")
        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)
        event = tracker.record_change(file_path, "modified")
        d = event.to_dict()
        impact = d["impact"]
        assert "risk" in impact
        assert "affected_count" in impact
        assert "affected_groups" in impact
        assert isinstance(impact["affected_groups"], list)

    def test_to_dict_lists_not_tuples(self) -> None:
        """All sequence fields in to_dict() must be lists, not tuples (JSON compat)."""
        graph = _make_graph()
        file_path = "/project/list_test.py"
        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)
        _add_function(graph, "f", file_path, "fn_lt")
        event = tracker.record_change(file_path, "created")
        d = event.to_dict()
        assert isinstance(d["nodes_added"], list)
        assert isinstance(d["nodes_modified"], list)
        assert isinstance(d["nodes_removed"], list)
        assert isinstance(d["node_ids_added"], list)
        assert isinstance(d["node_ids_modified"], list)
        assert isinstance(d["node_ids_removed"], list)
        assert isinstance(d["impact"]["affected_groups"], list)

    def test_change_event_is_frozen(self) -> None:
        """ChangeEvent dataclass is frozen — mutation should raise."""
        event = ChangeEvent(
            timestamp=1.0,
            file_path="/x.py",
            change_type="modified",
        )
        with pytest.raises((AttributeError, TypeError)):
            event.file_path = "/y.py"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# T9: on_change callback
# ---------------------------------------------------------------------------

class TestChangeTrackerCallbacks:
    def test_listener_receives_event(self) -> None:
        """Registered on_change listener gets called with ChangeEvent."""
        graph = _make_graph()
        file_path = "/project/cb.py"
        _add_function(graph, "fn_cb", file_path, "fn_cb1")
        tracker = ChangeTracker(graph)
        received: list[ChangeEvent] = []
        tracker.on_change(received.append)
        tracker.snapshot_file(file_path)
        tracker.record_change(file_path, "modified")
        assert len(received) == 1
        assert received[0].file_path == file_path

    def test_multiple_listeners(self) -> None:
        graph = _make_graph()
        file_path = "/project/multi.py"
        _add_function(graph, "fn_m", file_path, "fn_m1")
        tracker = ChangeTracker(graph)
        calls_a: list[ChangeEvent] = []
        calls_b: list[ChangeEvent] = []
        tracker.on_change(calls_a.append)
        tracker.on_change(calls_b.append)
        tracker.snapshot_file(file_path)
        tracker.record_change(file_path, "modified")
        assert len(calls_a) == 1
        assert len(calls_b) == 1

    def test_failing_listener_does_not_crash_tracker(self) -> None:
        """A listener that raises must not propagate the exception."""
        graph = _make_graph()
        file_path = "/project/fail.py"
        _add_function(graph, "fn_fail", file_path, "fn_fail1")
        tracker = ChangeTracker(graph)
        tracker.on_change(lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
        tracker.snapshot_file(file_path)
        # Should not raise
        event = tracker.record_change(file_path, "modified")
        assert event is not None


# ---------------------------------------------------------------------------
# T10: AST signature comparison (P0-2)
# ---------------------------------------------------------------------------

class TestASTSignatureComparison:
    def test_same_signature_not_modified(self) -> None:
        """Function with identical params, return type, decorators, line span is NOT modified."""
        graph = _make_graph()
        fp = "/project/sig.py"
        _add_function(graph, "fn", fp, "fn1", parameters=("a", "b"), end_line=10)

        tracker = ChangeTracker(graph)
        tracker.snapshot_file(fp)

        # Re-add with exact same signature (simulating no-op save)
        graph.remove_nodes_by_file(fp)
        _add_function(graph, "fn", fp, "fn1_v2", parameters=("a", "b"), end_line=10)

        event = tracker.record_change(fp, "modified")
        assert "fn" not in event.nodes_modified
        assert len(event.node_ids_modified) == 0

    def test_param_change_detected(self) -> None:
        """Adding a parameter triggers modification detection."""
        graph = _make_graph()
        fp = "/project/sig.py"
        _add_function(graph, "fn", fp, "fn1", parameters=("a",))

        tracker = ChangeTracker(graph)
        tracker.snapshot_file(fp)

        graph.remove_nodes_by_file(fp)
        _add_function(graph, "fn", fp, "fn1_v2", parameters=("a", "b"))

        event = tracker.record_change(fp, "modified")
        assert "fn" in event.nodes_modified

    def test_return_type_change_detected(self) -> None:
        """Changing return type triggers modification."""
        graph = _make_graph()
        fp = "/project/sig.py"
        _add_function(graph, "fn", fp, "fn1", return_type="int")

        tracker = ChangeTracker(graph)
        tracker.snapshot_file(fp)

        graph.remove_nodes_by_file(fp)
        _add_function(graph, "fn", fp, "fn1_v2", return_type="str")

        event = tracker.record_change(fp, "modified")
        assert "fn" in event.nodes_modified

    def test_decorator_change_detected(self) -> None:
        """Adding a decorator triggers modification."""
        graph = _make_graph()
        fp = "/project/sig.py"
        _add_function(graph, "fn", fp, "fn1")

        tracker = ChangeTracker(graph)
        tracker.snapshot_file(fp)

        graph.remove_nodes_by_file(fp)
        _add_function(graph, "fn", fp, "fn1_v2", decorators=("staticmethod",))

        event = tracker.record_change(fp, "modified")
        assert "fn" in event.nodes_modified

    def test_line_count_change_detected(self) -> None:
        """Changing function body length triggers modification."""
        graph = _make_graph()
        fp = "/project/sig.py"
        _add_function(graph, "fn", fp, "fn1", start_line=1, end_line=10)

        tracker = ChangeTracker(graph)
        tracker.snapshot_file(fp)

        graph.remove_nodes_by_file(fp)
        _add_function(graph, "fn", fp, "fn1_v2", start_line=1, end_line=20)

        event = tracker.record_change(fp, "modified")
        assert "fn" in event.nodes_modified

    def test_mixed_add_modify_remove(self) -> None:
        """Complex scenario: one added, one modified, one removed, one unchanged."""
        graph = _make_graph()
        fp = "/project/mixed.py"
        _add_function(graph, "keep_same", fp, "fn1", parameters=("x",), end_line=10)
        _add_function(graph, "will_change", fp, "fn2", parameters=("a",), end_line=20)
        _add_function(graph, "will_die", fp, "fn3", end_line=30)

        tracker = ChangeTracker(graph)
        tracker.snapshot_file(fp)

        graph.remove_nodes_by_file(fp)
        # keep_same: identical signature
        _add_function(graph, "keep_same", fp, "fn1_v2", parameters=("x",), end_line=10)
        # will_change: different params
        _add_function(graph, "will_change", fp, "fn2_v2", parameters=("a", "b"), end_line=25)
        # will_die: not re-added
        # new_func: brand new
        _add_function(graph, "new_func", fp, "fn4", end_line=40)

        event = tracker.record_change(fp, "modified")
        assert "new_func" in event.nodes_added
        assert "fn4" in event.node_ids_added
        assert "will_change" in event.nodes_modified
        assert "fn2_v2" in event.node_ids_modified
        assert "will_die" in event.nodes_removed
        assert "fn3" in event.node_ids_removed
        # keep_same should NOT be in any list
        assert "keep_same" not in event.nodes_added
        assert "keep_same" not in event.nodes_modified
        assert "keep_same" not in event.nodes_removed


# ---------------------------------------------------------------------------
# T11: Node ID fields (P0-1)
# ---------------------------------------------------------------------------

class TestNodeIdFields:
    def test_created_event_has_node_ids(self) -> None:
        """Created event includes node_ids_added matching the graph node IDs."""
        graph = _make_graph()
        fp = "/project/ids.py"
        tracker = ChangeTracker(graph)
        tracker.snapshot_file(fp)
        _add_function(graph, "alpha", fp, "id_alpha")
        _add_function(graph, "beta", fp, "id_beta")
        event = tracker.record_change(fp, "created")
        assert set(event.node_ids_added) == {"id_alpha", "id_beta"}
        assert set(event.nodes_added) == {"alpha", "beta"}

    def test_deleted_event_has_old_node_ids(self) -> None:
        """Deleted event includes node_ids_removed from the pre-deletion snapshot."""
        graph = _make_graph()
        fp = "/project/del.py"
        _add_function(graph, "doomed", fp, "id_doomed")
        tracker = ChangeTracker(graph)
        tracker.snapshot_file(fp)
        graph.remove_nodes_by_file(fp)
        event = tracker.record_change(fp, "deleted")
        assert "id_doomed" in event.node_ids_removed

    def test_to_dict_includes_node_ids(self) -> None:
        """to_dict() includes node_ids_* fields."""
        graph = _make_graph()
        fp = "/project/dict.py"
        tracker = ChangeTracker(graph)
        tracker.snapshot_file(fp)
        _add_function(graph, "f", fp, "nid_f")
        event = tracker.record_change(fp, "created")
        d = event.to_dict()
        assert "node_ids_added" in d
        assert "node_ids_modified" in d
        assert "node_ids_removed" in d
        assert "nid_f" in d["node_ids_added"]

    def test_node_ids_empty_when_no_changes(self) -> None:
        """All node_ids_* tuples are empty when nothing changed."""
        graph = _make_graph()
        fp = "/project/empty.py"
        tracker = ChangeTracker(graph)
        tracker.snapshot_file(fp)
        event = tracker.record_change(fp, "modified")
        assert event.node_ids_added == ()
        assert event.node_ids_modified == ()
        assert event.node_ids_removed == ()


# ---------------------------------------------------------------------------
# T12: Source diffs in ChangeEvent
# ---------------------------------------------------------------------------

class TestChangeTrackerDiffs:
    """Tests for unified-diff generation and source snapshot in ChangeTracker."""

    def test_change_tracker_records_diff_on_modify(self, tmp_path) -> None:
        """Modified function produces a diff entry in event.diffs."""
        py_file = tmp_path / "module.py"
        # Write initial version
        py_file.write_text("def greet(name):\n    return 'hi'\n", encoding="utf-8")

        graph = _make_graph()
        file_path = str(py_file)
        _add_function(graph, "greet", file_path, "fn_greet",
                      start_line=1, end_line=2, parameters=("name",))

        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)

        # Simulate modification: function signature changes (extra param)
        graph.remove_nodes_by_file(file_path)
        py_file.write_text("def greet(name, loud=False):\n    return 'hi'\n", encoding="utf-8")
        _add_function(graph, "greet", file_path, "fn_greet_v2",
                      start_line=1, end_line=2, parameters=("name", "loud"))

        event = tracker.record_change(file_path, "modified")
        assert "greet" in event.nodes_modified
        diff_map = dict(event.diffs)
        assert "greet" in diff_map
        assert len(diff_map["greet"]) > 0

    def test_change_tracker_diff_shows_added_lines(self, tmp_path) -> None:
        """Diff for a modified function has lines starting with '+' for new content."""
        py_file = tmp_path / "calc.py"
        py_file.write_text("def add(a):\n    return a\n", encoding="utf-8")

        graph = _make_graph()
        file_path = str(py_file)
        _add_function(graph, "add", file_path, "fn_add",
                      start_line=1, end_line=2, parameters=("a",))

        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)

        graph.remove_nodes_by_file(file_path)
        py_file.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        _add_function(graph, "add", file_path, "fn_add_v2",
                      start_line=1, end_line=2, parameters=("a", "b"))

        event = tracker.record_change(file_path, "modified")
        diff_map = dict(event.diffs)
        assert "add" in diff_map
        diff_text = diff_map["add"]
        # Unified diff always starts with --- / +++ headers or has +/- lines
        assert "+" in diff_text

    def test_change_tracker_diff_shows_removed_lines(self, tmp_path) -> None:
        """Diff for a modified function has lines starting with '-' for old content."""
        py_file = tmp_path / "ops.py"
        py_file.write_text("def sub(a, b, c):\n    return a - b - c\n", encoding="utf-8")

        graph = _make_graph()
        file_path = str(py_file)
        _add_function(graph, "sub", file_path, "fn_sub",
                      start_line=1, end_line=2, parameters=("a", "b", "c"))

        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)

        graph.remove_nodes_by_file(file_path)
        py_file.write_text("def sub(a, b):\n    return a - b\n", encoding="utf-8")
        _add_function(graph, "sub", file_path, "fn_sub_v2",
                      start_line=1, end_line=2, parameters=("a", "b"))

        event = tracker.record_change(file_path, "modified")
        diff_map = dict(event.diffs)
        assert "sub" in diff_map
        diff_text = diff_map["sub"]
        assert "-" in diff_text

    def test_change_tracker_no_diff_for_unchanged(self, tmp_path) -> None:
        """Unchanged functions (identical signature) do not appear in diffs."""
        py_file = tmp_path / "stable.py"
        py_file.write_text("def stable(x):\n    return x\n", encoding="utf-8")

        graph = _make_graph()
        file_path = str(py_file)
        _add_function(graph, "stable", file_path, "fn_stable",
                      start_line=1, end_line=2, parameters=("x",))
        _add_function(graph, "volatile", file_path, "fn_volatile",
                      start_line=3, end_line=4, parameters=("y",))

        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)

        # Remove and re-add — stable keeps same sig, volatile changes
        graph.remove_nodes_by_file(file_path)
        py_file.write_text(
            "def stable(x):\n    return x\ndef volatile(y, z):\n    return y + z\n",
            encoding="utf-8",
        )
        _add_function(graph, "stable", file_path, "fn_stable_v2",
                      start_line=1, end_line=2, parameters=("x",))
        _add_function(graph, "volatile", file_path, "fn_volatile_v2",
                      start_line=3, end_line=4, parameters=("y", "z"))

        event = tracker.record_change(file_path, "modified")
        diff_map = dict(event.diffs)
        # stable must NOT appear in diffs (no sig change)
        assert "stable" not in diff_map
        # volatile should appear (sig changed)
        assert "volatile" in diff_map

    def test_change_tracker_diff_for_new_function(self, tmp_path) -> None:
        """A newly added function has its full source in diffs."""
        py_file = tmp_path / "new_mod.py"
        py_file.write_text("def brand_new(x):\n    return x * 2\n", encoding="utf-8")

        graph = _make_graph()
        file_path = str(py_file)
        # Snapshot an empty file (no nodes yet)
        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)

        # "Create" event — add the new function
        _add_function(graph, "brand_new", file_path, "fn_brand",
                      start_line=1, end_line=2, parameters=("x",))

        event = tracker.record_change(file_path, "created")
        assert "brand_new" in event.nodes_added
        diff_map = dict(event.diffs)
        assert "brand_new" in diff_map
        assert "brand_new" in diff_map["brand_new"]

    def test_change_tracker_diff_for_deleted_function(self, tmp_path) -> None:
        """A deleted function has its old source preserved in diffs."""
        py_file = tmp_path / "dying.py"
        py_file.write_text("def doomed(x):\n    return x\n", encoding="utf-8")

        graph = _make_graph()
        file_path = str(py_file)
        _add_function(graph, "doomed", file_path, "fn_doomed",
                      start_line=1, end_line=2, parameters=("x",))

        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)

        # Simulate deletion
        graph.remove_nodes_by_file(file_path)
        event = tracker.record_change(file_path, "deleted")

        assert "doomed" in event.nodes_removed
        diff_map = dict(event.diffs)
        assert "doomed" in diff_map
        assert "doomed" in diff_map["doomed"]

    def test_change_event_diffs_json_serializable(self, tmp_path) -> None:
        """event.to_dict() with diffs survives a json.dumps / json.loads round-trip."""
        py_file = tmp_path / "serial.py"
        py_file.write_text("def serialize(x):\n    return x\n", encoding="utf-8")

        graph = _make_graph()
        file_path = str(py_file)
        _add_function(graph, "serialize", file_path, "fn_ser",
                      start_line=1, end_line=2, parameters=("x",))

        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)

        graph.remove_nodes_by_file(file_path)
        py_file.write_text("def serialize(x, y):\n    return x + y\n", encoding="utf-8")
        _add_function(graph, "serialize", file_path, "fn_ser_v2",
                      start_line=1, end_line=2, parameters=("x", "y"))

        event = tracker.record_change(file_path, "modified")
        d = event.to_dict()

        # Must not raise
        serialized = json.dumps(d)
        restored = json.loads(serialized)

        assert "diffs" in restored
        assert isinstance(restored["diffs"], dict)

    def test_change_tracker_snapshot_saves_source(self, tmp_path) -> None:
        """snapshot_file() stores source code in the internal snapshot structure."""
        py_file = tmp_path / "snap.py"
        py_file.write_text("def snapped(a, b):\n    return a + b\n", encoding="utf-8")

        graph = _make_graph()
        file_path = str(py_file)
        _add_function(graph, "snapped", file_path, "fn_snap",
                      start_line=1, end_line=2, parameters=("a", "b"))

        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)

        # The internal snapshot should contain source for "snapped"
        snap = tracker._file_snapshot.get(file_path, {})
        assert len(snap) == 1
        key = ("snapped", "Function")
        assert key in snap
        node_id, sig, source = snap[key]
        assert "snapped" in source


# ---------------------------------------------------------------------------
# T13: /api/suggest-tests endpoint helpers
# ---------------------------------------------------------------------------

class TestSuggestTestsEndpoint:
    """Tests for the suggest_tests integration used by /api/suggest-tests."""

    def test_suggest_tests_returns_list_for_known_name(self) -> None:
        """suggest_tests returns a list (possibly empty) for a known symbol name."""
        from vector_graph.analysis.suggest_tests import suggest_tests, TestSuggestion
        from vector_graph._types import Edge, EdgeType

        graph = _make_graph()
        fp_src = "/project/utils.py"
        fp_test = "/project/tests/test_utils.py"

        _add_function(graph, "compute", fp_src, "fn_compute")
        _add_function(graph, "test_compute", fp_test, "fn_test_compute")

        # Add CALLS edge: test_compute -> compute
        edge = Edge(
            id="e1",
            source_id="fn_test_compute",
            target_id="fn_compute",
            edge_type=EdgeType.CALLS,
            confidence=1.0,
        )
        graph.add_edge(edge)

        suggestions = suggest_tests(graph, "compute")
        assert isinstance(suggestions, list)
        assert len(suggestions) == 1
        assert suggestions[0].test_name == "test_compute"
        assert suggestions[0].test_file == fp_test

    def test_suggest_tests_unknown_name_returns_empty(self) -> None:
        """Unknown function name returns an empty suggestions list."""
        from vector_graph.analysis.suggest_tests import suggest_tests

        graph = _make_graph()
        suggestions = suggest_tests(graph, "totally_unknown_function_xyz")
        assert suggestions == []
