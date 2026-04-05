"""Unit tests for taskflow.engine.task_engine and engine.notifier."""
from __future__ import annotations

from taskflow.engine.task_engine import TaskEngine
from taskflow.models.task import Priority, SubTask, Task, TaskStatus
from taskflow.storage.memory import InMemoryStore
from taskflow.utils.validators import validate_task_id, validate_task_title


def make_engine() -> TaskEngine:
    return TaskEngine(InMemoryStore())


class TestTaskEngineCRUD:
    def test_create_and_get_task(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "Hello World")
        task = engine.get_task("t1")
        assert task is not None
        assert task.title == "Hello World"

    def test_get_missing_task_returns_none(self) -> None:
        engine = make_engine()
        assert engine.get_task("missing") is None

    def test_create_task_invalid_id_raises(self) -> None:
        engine = make_engine()
        import pytest
        with pytest.raises(ValueError):
            engine.create_task("bad id!", "Title")

    def test_create_task_empty_title_raises(self) -> None:
        engine = make_engine()
        import pytest
        with pytest.raises(ValueError):
            engine.create_task("t1", "")

    def test_delete_task(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "Delete me")
        assert engine.delete_task("t1")
        assert engine.get_task("t1") is None

    def test_delete_missing_task_returns_false(self) -> None:
        engine = make_engine()
        assert not engine.delete_task("missing")


class TestStatusTransitions:
    def test_update_status(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "Test")
        assert engine.update_status("t1", TaskStatus.IN_PROGRESS)
        task = engine.get_task("t1")
        assert task is not None
        assert task.status == TaskStatus.IN_PROGRESS

    def test_update_status_missing_task_returns_false(self) -> None:
        engine = make_engine()
        assert not engine.update_status("missing", TaskStatus.DONE)


class TestAssignment:
    def test_assign_task(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "Test")
        assert engine.assign_task("t1", "alice")
        task = engine.get_task("t1")
        assert task is not None
        assert task.assignee == "alice"

    def test_list_tasks_by_assignee(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "Alice task")
        engine.create_task("t2", "Bob task")
        engine.assign_task("t1", "alice")
        engine.assign_task("t2", "bob")
        alice_tasks = engine.list_tasks(assignee="alice")
        assert len(alice_tasks) == 1
        assert alice_tasks[0].id == "t1"


class TestSubtaskOps:
    def test_add_and_complete_subtask(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "Parent")
        engine.add_subtask("t1", SubTask("s1", "Step 1"))
        assert engine.complete_subtask("t1", "s1")
        task = engine.get_task("t1")
        assert task is not None
        assert task.subtasks[0].done

    def test_add_subtask_missing_task_returns_false(self) -> None:
        engine = make_engine()
        assert not engine.add_subtask("missing", SubTask("s1", "Step"))


class TestNotifications:
    def test_subscriber_receives_created_event(self) -> None:
        engine = make_engine()
        received = []
        engine.notifier.subscribe(lambda event, task, **kw: received.append((event, task.id)))
        engine.create_task("t1", "Notification test")
        assert ("task_created", "t1") in received

    def test_subscriber_receives_status_change(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "Test")
        events = []
        engine.notifier.subscribe(lambda ev, task, **kw: events.append(ev))
        engine.update_status("t1", TaskStatus.DONE)
        assert "status_changed" in events

    def test_tagging_task(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "Tagged")
        assert engine.tag_task("t1", "urgent")
        task = engine.get_task("t1")
        assert task is not None
        assert "urgent" in task.tags
