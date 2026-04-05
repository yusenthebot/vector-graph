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


def _add_function(graph: KnowledgeGraph, name: str, file_path: str, node_id: str) -> GraphNode:
    props = NodeProperties(name=name, file_path=file_path, start_line=1, end_line=10)
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
    def test_nodes_modified_list_populated(self) -> None:
        """After snapshot + modify, nodes_modified contains the surviving function name."""
        graph = _make_graph()
        file_path = "/project/foo.py"
        _add_function(graph, "bar", file_path, "fn1")

        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)

        # Graph already has bar — no change to nodes, just same nodes remain
        event = tracker.record_change(file_path, "modified")

        assert event.change_type == "modified"
        assert event.file_path == file_path
        # On a plain modify with the same nodes, modified set = intersection
        assert "bar" in event.nodes_modified

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

    def test_nodes_added_empty_on_delete(self) -> None:
        graph = _make_graph()
        file_path = "/project/gone.py"
        _add_function(graph, "fn", file_path, "fn_d1")
        tracker = ChangeTracker(graph)
        tracker.snapshot_file(file_path)
        graph.remove_nodes_by_file(file_path)
        event = tracker.record_change(file_path, "deleted")
        assert len(event.nodes_added) == 0


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
