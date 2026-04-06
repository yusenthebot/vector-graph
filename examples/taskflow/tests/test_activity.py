"""Tests for comments and activity tracking."""
from __future__ import annotations

import pytest

from taskflow.engine.task_engine import TaskEngine
from taskflow.models.comment import ActivityType
from taskflow.storage.memory import InMemoryStore


def make_engine() -> TaskEngine:
    return TaskEngine(InMemoryStore())


class TestComments:
    def test_add_and_get_comments(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "Test task")
        engine.add_comment("t1", "alice", "First comment")
        engine.add_comment("t1", "bob", "Second comment")
        comments = engine.get_comments("t1")
        assert len(comments) == 2
        assert comments[0].author == "alice"
        assert comments[1].text == "Second comment"

    def test_add_comment_missing_task_raises(self) -> None:
        engine = make_engine()
        with pytest.raises(ValueError):
            engine.add_comment("missing", "alice", "Nope")

    def test_add_comment_empty_text_raises(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "Test")
        with pytest.raises(ValueError):
            engine.add_comment("t1", "alice", "   ")

    def test_add_comment_empty_author_raises(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "Test")
        with pytest.raises(ValueError):
            engine.add_comment("t1", "", "Some text")

    def test_comments_isolated_per_task(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "Task 1")
        engine.create_task("t2", "Task 2")
        engine.add_comment("t1", "alice", "On t1")
        engine.add_comment("t2", "bob", "On t2")
        assert len(engine.get_comments("t1")) == 1
        assert len(engine.get_comments("t2")) == 1


class TestActivityLog:
    def test_create_task_records_activity(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "Test")
        activity = engine.get_task_activity("t1")
        assert len(activity) == 1
        assert activity[0].activity_type == ActivityType.CREATED

    def test_status_change_records_activity(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "Test")
        from taskflow.models.task import TaskStatus
        engine.update_status("t1", TaskStatus.IN_PROGRESS)
        activity = engine.get_task_activity("t1")
        types = [e.activity_type for e in activity]
        assert ActivityType.CREATED in types
        assert ActivityType.STATUS_CHANGED in types

    def test_assign_records_activity(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "Test")
        engine.assign_task("t1", "alice")
        activity = engine.get_task_activity("t1")
        types = [e.activity_type for e in activity]
        assert ActivityType.ASSIGNED in types

    def test_comment_records_activity(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "Test")
        engine.add_comment("t1", "alice", "Hello")
        activity = engine.get_task_activity("t1")
        types = [e.activity_type for e in activity]
        assert ActivityType.COMMENTED in types

    def test_recent_activity_returns_latest_first(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "First")
        engine.create_task("t2", "Second")
        recent = engine.get_recent_activity(limit=5)
        assert len(recent) == 2
        assert recent[0].task_id == "t2"

    def test_recent_activity_respects_limit(self) -> None:
        engine = make_engine()
        for i in range(10):
            engine.create_task(f"t{i}", f"Task {i}")
        recent = engine.get_recent_activity(limit=3)
        assert len(recent) == 3
