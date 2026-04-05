"""Unit tests for taskflow.models.task."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from taskflow.models.task import Priority, SubTask, Task, TaskStatus


def make_task(**kwargs) -> Task:
    defaults = {"id": "t1", "title": "Test task"}
    defaults.update(kwargs)
    return Task(**defaults)


class TestTaskStatus:
    def test_default_status_is_pending(self) -> None:
        task = make_task()
        assert task.status == TaskStatus.PENDING

    def test_is_terminal_done(self) -> None:
        task = make_task(status=TaskStatus.DONE)
        assert task.is_terminal()

    def test_is_terminal_cancelled(self) -> None:
        task = make_task(status=TaskStatus.CANCELLED)
        assert task.is_terminal()

    def test_pending_is_not_terminal(self) -> None:
        task = make_task()
        assert not task.is_terminal()


class TestOverdue:
    def test_not_overdue_without_due_date(self) -> None:
        task = make_task()
        assert not task.is_overdue

    def test_overdue_when_due_date_in_past(self) -> None:
        task = make_task(due_date=datetime.now() - timedelta(days=1))
        assert task.is_overdue

    def test_not_overdue_when_done(self) -> None:
        task = make_task(
            status=TaskStatus.DONE,
            due_date=datetime.now() - timedelta(days=1),
        )
        assert not task.is_overdue

    def test_not_overdue_future_due_date(self) -> None:
        task = make_task(due_date=datetime.now() + timedelta(days=7))
        assert not task.is_overdue


class TestSubtasks:
    def test_completion_ratio_no_subtasks_pending(self) -> None:
        task = make_task()
        assert task.completion_ratio == 0.0

    def test_completion_ratio_no_subtasks_done(self) -> None:
        task = make_task(status=TaskStatus.DONE)
        assert task.completion_ratio == 1.0

    def test_completion_ratio_partial(self) -> None:
        task = make_task()
        task.add_subtask(SubTask("s1", "First"))
        task.add_subtask(SubTask("s2", "Second"))
        task.complete_subtask("s1")
        assert task.completion_ratio == pytest.approx(0.5)

    def test_complete_subtask_returns_false_for_missing(self) -> None:
        task = make_task()
        assert not task.complete_subtask("missing")

    def test_complete_subtask_marks_done(self) -> None:
        task = make_task()
        task.add_subtask(SubTask("s1", "Step 1"))
        assert task.complete_subtask("s1")
        assert task.subtasks[0].done


class TestTaskHelpers:
    def test_has_tag(self) -> None:
        task = make_task(tags=["urgent", "backend"])
        assert task.has_tag("urgent")
        assert not task.has_tag("frontend")

    def test_is_assigned(self) -> None:
        task = make_task(assignee="alice")
        assert task.is_assigned()

    def test_not_assigned_by_default(self) -> None:
        task = make_task()
        assert not task.is_assigned()

    def test_is_blocking(self) -> None:
        task = make_task(status=TaskStatus.BLOCKED)
        assert task.is_blocking()
