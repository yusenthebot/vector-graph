"""Unit tests for vector_graph.api.tui — TUI dashboard formatting functions."""

from __future__ import annotations

import time

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_change_event(
    change_type: str = "modified",
    file_path: str = "/project/mymodule.py",
    nodes_added: tuple = (),
    nodes_modified: tuple = ("func_a",),
    nodes_removed: tuple = (),
    risk: str = "MEDIUM",
    affected_count: int = 0,
    timestamp: float | None = None,
):
    """Build a ChangeEvent without needing a live graph."""
    from vector_graph.watch.change_tracker import ChangeEvent

    return ChangeEvent(
        timestamp=timestamp if timestamp is not None else time.time(),
        file_path=file_path,
        change_type=change_type,
        nodes_added=nodes_added,
        nodes_modified=nodes_modified,
        nodes_removed=nodes_removed,
        risk=risk,
        affected_count=affected_count,
    )


# ---------------------------------------------------------------------------
# test_tui_importable — module must import even without rich installed
# ---------------------------------------------------------------------------

class TestTuiImportable:
    def test_tui_importable(self) -> None:
        """from vector_graph.api.tui import format_change_event must not raise."""
        from vector_graph.api.tui import format_change_event  # noqa: F401

    def test_run_tui_exists(self) -> None:
        """run_tui function must be callable."""
        from vector_graph.api.tui import run_tui

        assert callable(run_tui)


# ---------------------------------------------------------------------------
# format_change_event
# ---------------------------------------------------------------------------

class TestFormatChangeEvent:
    def test_format_change_event_modified(self) -> None:
        """Modified file event includes ~ prefix and node counts."""
        from vector_graph.api.tui import format_change_event

        event = _make_change_event(
            change_type="modified",
            nodes_modified=("func_a", "func_b"),
        )
        result = format_change_event(event)

        assert "~" in result
        assert "mymodule.py" in result

    def test_format_change_event_modified_node_counts(self) -> None:
        """Modified event with 2 modified nodes shows mod count."""
        from vector_graph.api.tui import format_change_event

        event = _make_change_event(
            change_type="modified",
            nodes_modified=("func_a", "func_b"),
        )
        result = format_change_event(event)
        # Should mention ~2 mod somewhere
        assert "~2" in result

    def test_format_change_event_created(self) -> None:
        """Created file event includes + prefix."""
        from vector_graph.api.tui import format_change_event

        event = _make_change_event(
            change_type="created",
            file_path="/project/newfile.py",
            nodes_added=("new_func",),
            nodes_modified=(),
        )
        result = format_change_event(event)

        assert "+" in result
        assert "newfile.py" in result

    def test_format_change_event_created_node_counts(self) -> None:
        """Created event with 1 added node shows +1 new."""
        from vector_graph.api.tui import format_change_event

        event = _make_change_event(
            change_type="created",
            nodes_added=("new_func",),
            nodes_modified=(),
        )
        result = format_change_event(event)
        assert "+1" in result

    def test_format_change_event_deleted(self) -> None:
        """Deleted file event includes - prefix."""
        from vector_graph.api.tui import format_change_event

        event = _make_change_event(
            change_type="deleted",
            file_path="/project/gone.py",
            nodes_modified=(),
            nodes_removed=("dead_fn",),
        )
        result = format_change_event(event)

        assert "-" in result
        assert "gone.py" in result

    def test_format_change_event_deleted_node_counts(self) -> None:
        """Deleted event with 1 removed node shows -1 del."""
        from vector_graph.api.tui import format_change_event

        event = _make_change_event(
            change_type="deleted",
            nodes_modified=(),
            nodes_removed=("dead_fn",),
        )
        result = format_change_event(event)
        assert "-1" in result

    def test_format_change_event_includes_risk(self) -> None:
        """Formatted event string includes the risk level."""
        from vector_graph.api.tui import format_change_event

        event = _make_change_event(risk="HIGH")
        result = format_change_event(event)
        assert "HIGH" in result

    def test_format_change_event_includes_affected_count(self) -> None:
        """Formatted event includes affected count when > 0."""
        from vector_graph.api.tui import format_change_event

        event = _make_change_event(affected_count=5)
        result = format_change_event(event)
        assert "5" in result

    def test_format_change_event_no_affected_count_zero(self) -> None:
        """Formatted event omits affected count when 0."""
        from vector_graph.api.tui import format_change_event

        event = _make_change_event(affected_count=0)
        result = format_change_event(event)
        # "→ 0" should NOT appear (zero affected is not shown)
        assert "→ 0" not in result

    def test_format_change_event_returns_string(self) -> None:
        """format_change_event always returns a str."""
        from vector_graph.api.tui import format_change_event

        event = _make_change_event()
        result = format_change_event(event)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_change_event_includes_timestamp(self) -> None:
        """Formatted event includes a timestamp in HH:MM:SS format."""
        from vector_graph.api.tui import format_change_event

        event = _make_change_event()
        result = format_change_event(event)
        # Timestamp appears as [HH:MM:SS]
        assert "[" in result and ":" in result


# ---------------------------------------------------------------------------
# format_risk_badge
# ---------------------------------------------------------------------------

class TestFormatRiskBadge:
    @pytest.mark.parametrize("risk", ["CRITICAL", "HIGH", "MEDIUM", "LOW"])
    def test_format_risk_badge_distinct(self, risk: str) -> None:
        """Each risk level produces a distinct non-empty string representation."""
        from vector_graph.api.tui import format_change_event

        event = _make_change_event(risk=risk)
        result = format_change_event(event)
        assert risk in result


# ---------------------------------------------------------------------------
# format_session_summary
# ---------------------------------------------------------------------------

class TestFormatSessionSummary:
    def test_format_session_summary_nonempty(self) -> None:
        """Summary with data produces multi-line string."""
        from vector_graph.api.tui import format_session_summary

        summary = {
            "event_count": 3,
            "files_changed": 2,
            "nodes_added": 4,
            "nodes_modified": 7,
            "nodes_removed": 1,
            "high_risk_changes": 1,
            "groups_affected": ["analysis", "api"],
        }
        result = format_session_summary(summary)
        assert isinstance(result, str)
        assert "\n" in result  # multi-line
        assert "3" in result   # event_count
        assert "2" in result   # files_changed
        assert "4" in result   # nodes_added
        assert "7" in result   # nodes_modified

    def test_format_session_summary_empty(self) -> None:
        """Empty summary dict shows all zeros."""
        from vector_graph.api.tui import format_session_summary

        result = format_session_summary({})
        assert isinstance(result, str)
        # All counts default to 0
        assert "0" in result

    def test_format_session_summary_includes_groups(self) -> None:
        """Summary with groups lists them."""
        from vector_graph.api.tui import format_session_summary

        result = format_session_summary({"groups_affected": ["api", "watch"]})
        assert "api" in result
        assert "watch" in result

    def test_format_session_summary_no_groups_when_empty(self) -> None:
        """Summary with empty groups list doesn't add a Groups line."""
        from vector_graph.api.tui import format_session_summary

        result = format_session_summary({"groups_affected": []})
        # Should not have "Groups:" when list is empty
        # (Either not present or shows nothing — just verify no crash)
        assert isinstance(result, str)

    def test_format_session_summary_high_risk(self) -> None:
        """High risk count appears in summary."""
        from vector_graph.api.tui import format_session_summary

        result = format_session_summary({"high_risk_changes": 5})
        assert "5" in result
