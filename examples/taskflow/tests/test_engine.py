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


class TestSearchTasks:
    def _populated(self) -> TaskEngine:
        engine = make_engine()
        from datetime import datetime, timedelta
        engine.create_task("t1", "Implement path planner", priority=Priority.HIGH,
                           description="A* algorithm for nav")
        engine.create_task("t2", "Write unit tests", priority=Priority.MEDIUM,
                           tags=["testing"])
        engine.create_task("t3", "Deploy to hardware", priority=Priority.CRITICAL,
                           due_date=datetime.now() - timedelta(days=1))
        engine.create_task("t4", "Update docs", priority=Priority.LOW,
                           tags=["testing", "docs"])
        return engine

    def test_keyword_matches_title(self) -> None:
        engine = self._populated()
        assert len(engine.search_tasks(keyword="planner")) == 1

    def test_keyword_matches_description(self) -> None:
        engine = self._populated()
        assert len(engine.search_tasks(keyword="algorithm")) == 1

    def test_keyword_case_insensitive(self) -> None:
        engine = self._populated()
        assert len(engine.search_tasks(keyword="PLANNER")) == 1

    def test_priority_filter(self) -> None:
        engine = self._populated()
        results = engine.search_tasks(priority=Priority.HIGH)
        ids = {t.id for t in results}
        assert "t1" in ids and "t3" in ids
        assert "t4" not in ids

    def test_tag_filter(self) -> None:
        engine = self._populated()
        ids = {t.id for t in engine.search_tasks(tag="testing")}
        assert ids == {"t2", "t4"}

    def test_overdue_filter(self) -> None:
        engine = self._populated()
        results = engine.search_tasks(overdue_only=True)
        assert len(results) == 1 and results[0].id == "t3"

    def test_combined_filters(self) -> None:
        engine = self._populated()
        results = engine.search_tasks(keyword="unit", tag="testing")
        assert len(results) == 1 and results[0].id == "t2"

    def test_no_match(self) -> None:
        engine = self._populated()
        assert engine.search_tasks(keyword="nonexistent") == []

    def test_sort_by_priority_desc(self) -> None:
        engine = self._populated()
        results = engine.search_tasks()
        assert results[0].priority.value >= results[-1].priority.value

    def test_sort_by_due_date_asc(self) -> None:
        engine = self._populated()
        results = engine.search_tasks(sort_by="due_date", ascending=True)
        assert results[0].id == "t3"


class TestDependencies:
    def test_add_dependency(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "First")
        engine.create_task("t2", "Second")
        assert engine.add_dependency("t2", "t1")
        task = engine.get_task("t2")
        assert "t1" in task.dependencies

    def test_add_dependency_missing_task(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "First")
        assert not engine.add_dependency("t2", "t1")
        assert not engine.add_dependency("t1", "t2")

    def test_self_dependency_rejected(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "First")
        assert not engine.add_dependency("t1", "t1")

    def test_duplicate_dependency_rejected(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "First")
        engine.create_task("t2", "Second")
        assert engine.add_dependency("t2", "t1")
        assert not engine.add_dependency("t2", "t1")

    def test_cycle_detection_direct(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "A")
        engine.create_task("t2", "B")
        engine.add_dependency("t2", "t1")
        # t1 -> t2 would create cycle: t1 depends on t2 depends on t1
        assert not engine.add_dependency("t1", "t2")

    def test_cycle_detection_transitive(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "A")
        engine.create_task("t2", "B")
        engine.create_task("t3", "C")
        engine.add_dependency("t2", "t1")
        engine.add_dependency("t3", "t2")
        # t1 -> t3 would create cycle: t1 -> t3 -> t2 -> t1
        assert not engine.add_dependency("t1", "t3")

    def test_remove_dependency(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "A")
        engine.create_task("t2", "B")
        engine.add_dependency("t2", "t1")
        assert engine.remove_dependency("t2", "t1")
        task = engine.get_task("t2")
        assert "t1" not in task.dependencies

    def test_remove_nonexistent_dependency(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "A")
        assert not engine.remove_dependency("t1", "t2")

    def test_dependency_chain(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "A")
        engine.create_task("t2", "B")
        engine.create_task("t3", "C")
        engine.add_dependency("t2", "t1")
        engine.add_dependency("t3", "t2")
        chain = engine.get_dependency_chain("t3")
        assert chain == ["t1", "t2"]

    def test_blocked_reason(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "Dep")
        engine.create_task("t2", "Blocked")
        engine.add_dependency("t2", "t1")
        assert engine.get_blocked_reason("t2") == ["t1"]

    def test_blocked_reason_resolved(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "Dep")
        engine.create_task("t2", "Blocked")
        engine.add_dependency("t2", "t1")
        engine.update_status("t1", TaskStatus.DONE)
        assert engine.get_blocked_reason("t2") == []

    def test_dependency_persisted(self) -> None:
        engine = make_engine()
        engine.create_task("t1", "A")
        engine.create_task("t2", "B")
        engine.add_dependency("t2", "t1")
        # Re-fetch from store
        task = engine.get_task("t2")
        assert task.depends_on("t1")


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
