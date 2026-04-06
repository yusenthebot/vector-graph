"""Tests for task statistics reporter."""
from __future__ import annotations

from datetime import datetime, timedelta

from taskflow.engine.reporter import TaskReporter
from taskflow.engine.task_engine import TaskEngine
from taskflow.models.task import Priority, SubTask, TaskStatus
from taskflow.storage.memory import InMemoryStore


def make_reporter() -> tuple[TaskEngine, TaskReporter]:
    engine = TaskEngine(InMemoryStore())
    return engine, TaskReporter(engine)


class TestEmptyReport:
    def test_empty_report_zeroes(self) -> None:
        _, reporter = make_reporter()
        report = reporter.generate_report()
        assert report.total == 0
        assert report.completion_rate == 0.0
        assert report.overdue_ratio == 0.0
        assert report.workload == []


class TestReportCounts:
    def _populated(self) -> tuple[TaskEngine, TaskReporter]:
        engine, reporter = make_reporter()
        engine.create_task("t1", "Task 1", priority=Priority.HIGH)
        engine.create_task("t2", "Task 2", priority=Priority.MEDIUM)
        engine.create_task("t3", "Task 3", priority=Priority.LOW,
                           due_date=datetime.now() - timedelta(days=1))
        engine.update_status("t1", TaskStatus.IN_PROGRESS)
        engine.update_status("t1", TaskStatus.DONE)
        engine.assign_task("t2", "alice")
        return engine, reporter

    def test_total_count(self) -> None:
        _, reporter = self._populated()
        report = reporter.generate_report()
        assert report.total == 3

    def test_completion_rate(self) -> None:
        _, reporter = self._populated()
        report = reporter.generate_report()
        assert abs(report.completion_rate - 1 / 3) < 0.01

    def test_overdue_count(self) -> None:
        _, reporter = self._populated()
        report = reporter.generate_report()
        assert report.overdue_count == 1

    def test_overdue_ratio(self) -> None:
        _, reporter = self._populated()
        report = reporter.generate_report()
        assert abs(report.overdue_ratio - 1 / 3) < 0.01

    def test_unassigned_count(self) -> None:
        _, reporter = self._populated()
        report = reporter.generate_report()
        # t1 (done, unassigned) + t3 (pending, unassigned) = 2
        assert report.unassigned_count == 2

    def test_by_status(self) -> None:
        _, reporter = self._populated()
        report = reporter.generate_report()
        assert report.by_status.get("done") == 1
        assert report.by_status.get("pending") == 2

    def test_by_priority(self) -> None:
        _, reporter = self._populated()
        report = reporter.generate_report()
        assert report.by_priority.get("HIGH") == 1
        assert report.by_priority.get("MEDIUM") == 1
        assert report.by_priority.get("LOW") == 1


class TestWorkload:
    def test_workload_entries(self) -> None:
        engine, reporter = make_reporter()
        engine.create_task("t1", "Task 1")
        engine.create_task("t2", "Task 2")
        engine.assign_task("t1", "alice")
        engine.assign_task("t2", "alice")
        engine.update_status("t1", TaskStatus.IN_PROGRESS)

        workload = reporter.workload_summary()
        assert len(workload) == 1
        assert workload[0].user == "alice"
        assert workload[0].total == 2
        assert workload[0].in_progress == 1

    def test_workload_sorted_by_total_desc(self) -> None:
        engine, reporter = make_reporter()
        engine.create_task("t1", "A")
        engine.create_task("t2", "B")
        engine.create_task("t3", "C")
        engine.assign_task("t1", "bob")
        engine.assign_task("t2", "alice")
        engine.assign_task("t3", "alice")

        workload = reporter.workload_summary()
        assert workload[0].user == "alice"
        assert workload[1].user == "bob"


class TestSubtaskAverage:
    def test_avg_subtask_completion(self) -> None:
        engine, reporter = make_reporter()
        engine.create_task("t1", "With subtasks")
        engine.add_subtask("t1", SubTask("s1", "A"))
        engine.add_subtask("t1", SubTask("s2", "B"))
        engine.complete_subtask("t1", "s1")
        # t1: 1/2 = 50%
        report = reporter.generate_report()
        assert abs(report.avg_subtask_completion - 0.5) < 0.01


class TestTopTags:
    def test_top_tags(self) -> None:
        engine, reporter = make_reporter()
        engine.create_task("t1", "A", tags=["bug", "urgent"])
        engine.create_task("t2", "B", tags=["bug"])
        engine.create_task("t3", "C", tags=["feature"])
        report = reporter.generate_report()
        tag_names = [t for t, _ in report.top_tags]
        assert tag_names[0] == "bug"
        assert "urgent" in tag_names
        assert "feature" in tag_names
