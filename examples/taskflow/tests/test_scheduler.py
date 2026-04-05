"""Unit tests for taskflow.engine.scheduler.PriorityScheduler."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from taskflow.engine.scheduler import PriorityScheduler
from taskflow.engine.task_engine import TaskEngine
from taskflow.models.task import Priority, SubTask, Task, TaskStatus
from taskflow.storage.memory import InMemoryStore


def make_scheduler() -> tuple[TaskEngine, PriorityScheduler]:
    engine = TaskEngine(InMemoryStore())
    scheduler = PriorityScheduler(engine)
    return engine, scheduler


class TestScheduleBasics:
    def test_empty_task_list_returns_empty(self) -> None:
        _, scheduler = make_scheduler()
        assert scheduler.schedule_tasks(["alice"]) == []

    def test_no_users_returns_empty(self) -> None:
        engine, scheduler = make_scheduler()
        engine.create_task("t1", "Task")
        assert scheduler.schedule_tasks([]) == []

    def test_assigns_pending_task_to_user(self) -> None:
        engine, scheduler = make_scheduler()
        engine.create_task("t1", "Task")
        assignments = scheduler.schedule_tasks(["alice"])
        assert len(assignments) == 1
        assert assignments[0] == ("t1", "alice")

    def test_task_status_updated_to_in_progress(self) -> None:
        engine, scheduler = make_scheduler()
        engine.create_task("t1", "Task")
        scheduler.schedule_tasks(["alice"])
        task = engine.get_task("t1")
        assert task is not None
        assert task.status == TaskStatus.IN_PROGRESS

    def test_assigns_to_least_loaded_user(self) -> None:
        engine, scheduler = make_scheduler()
        for i in range(3):
            engine.create_task(f"t{i}", f"Task {i}")
        assignments = scheduler.schedule_tasks(["alice", "bob"])
        users_assigned = [u for _, u in assignments]
        # Both users should get some tasks (not all to one)
        assert "alice" in users_assigned
        assert "bob" in users_assigned


class TestPriorityOrdering:
    def test_critical_task_scheduled_before_low(self) -> None:
        engine, scheduler = make_scheduler()
        engine.create_task("low", "Low priority", priority=Priority.LOW)
        engine.create_task("crit", "Critical", priority=Priority.CRITICAL)
        scheduler.max_concurrent = 1
        assignments = scheduler.schedule_tasks(["alice"])
        assert len(assignments) == 1
        assert assignments[0][0] == "crit"


class TestDependencies:
    def test_task_with_unresolved_dependency_skipped(self) -> None:
        engine, scheduler = make_scheduler()
        engine.create_task("dep", "Dependency")
        engine.create_task("child", "Child", tags=["depends_on:dep"])
        assignments = scheduler.schedule_tasks(["alice"])
        assigned_ids = [tid for tid, _ in assignments]
        assert "child" not in assigned_ids

    def test_task_with_resolved_dependency_scheduled(self) -> None:
        engine, scheduler = make_scheduler()
        engine.create_task("dep", "Dependency")
        engine.update_status("dep", TaskStatus.DONE)
        engine.create_task("child", "Child", tags=["depends_on:dep"])
        assignments = scheduler.schedule_tasks(["alice"])
        assigned_ids = [tid for tid, _ in assignments]
        assert "child" in assigned_ids


class TestBlockedUnblocking:
    def test_blocked_task_unblocked_when_dependency_done(self) -> None:
        engine, scheduler = make_scheduler()
        engine.create_task("dep", "Done dep")
        engine.update_status("dep", TaskStatus.DONE)
        engine.create_task("blocked", "Was blocked", tags=["depends_on:dep"])
        engine.update_status("blocked", TaskStatus.BLOCKED)
        # scheduler should unblock and schedule
        assignments = scheduler.schedule_tasks(["alice"])
        assigned_ids = [tid for tid, _ in assignments]
        assert "blocked" in assigned_ids


class TestScheduleSummary:
    def test_summary_keys(self) -> None:
        engine, scheduler = make_scheduler()
        engine.create_task("t1", "Task")
        summary = scheduler.get_schedule_summary()
        for key in ("total", "pending", "in_progress", "done", "blocked", "overdue", "critical"):
            assert key in summary

    def test_summary_counts(self) -> None:
        engine, scheduler = make_scheduler()
        engine.create_task("t1", "Task 1")
        engine.create_task("t2", "Task 2")
        engine.update_status("t2", TaskStatus.DONE)
        summary = scheduler.get_schedule_summary()
        assert summary["total"] == 2
        assert summary["done"] == 1
