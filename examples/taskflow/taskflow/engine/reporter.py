"""Task statistics and reporting — aggregate analytics across all tasks."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from taskflow.engine.task_engine import TaskEngine
from taskflow.models.task import Priority, Task, TaskStatus


@dataclass(frozen=True)
class WorkloadEntry:
    user: str
    total: int
    in_progress: int
    pending: int
    done: int
    overdue: int


@dataclass(frozen=True)
class TaskReport:
    total: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
    overdue_count: int
    overdue_ratio: float
    completion_rate: float
    unassigned_count: int
    avg_subtask_completion: float
    workload: list[WorkloadEntry]
    top_tags: list[tuple[str, int]]


class TaskReporter:
    """Generates aggregate statistics from the task engine."""

    def __init__(self, engine: TaskEngine) -> None:
        self._engine = engine

    def generate_report(self) -> TaskReport:
        tasks = self._engine.list_tasks()
        if not tasks:
            return TaskReport(
                total=0,
                by_status={},
                by_priority={},
                overdue_count=0,
                overdue_ratio=0.0,
                completion_rate=0.0,
                unassigned_count=0,
                avg_subtask_completion=0.0,
                workload=[],
                top_tags=[],
            )

        by_status = Counter(t.status.value for t in tasks)
        by_priority = Counter(t.priority.name for t in tasks)

        done_count = sum(1 for t in tasks if t.status == TaskStatus.DONE)
        overdue_count = sum(1 for t in tasks if t.is_overdue)
        unassigned = sum(1 for t in tasks if not t.is_assigned())

        tasks_with_subtasks = [t for t in tasks if t.subtasks]
        avg_subtask = (
            sum(t.completion_ratio for t in tasks_with_subtasks) / len(tasks_with_subtasks)
            if tasks_with_subtasks
            else 0.0
        )

        tag_counter: Counter[str] = Counter()
        for t in tasks:
            for tag in t.tags:
                tag_counter[tag] += 1

        return TaskReport(
            total=len(tasks),
            by_status=dict(by_status),
            by_priority=dict(by_priority),
            overdue_count=overdue_count,
            overdue_ratio=overdue_count / len(tasks),
            completion_rate=done_count / len(tasks),
            unassigned_count=unassigned,
            avg_subtask_completion=avg_subtask,
            workload=self._compute_workload(tasks),
            top_tags=tag_counter.most_common(10),
        )

    def workload_summary(self) -> list[WorkloadEntry]:
        return self._compute_workload(self._engine.list_tasks())

    def _compute_workload(self, tasks: list[Task]) -> list[WorkloadEntry]:
        users: dict[str, dict[str, int]] = {}
        for t in tasks:
            if not t.assignee:
                continue
            if t.assignee not in users:
                users[t.assignee] = {
                    "total": 0, "in_progress": 0, "pending": 0,
                    "done": 0, "overdue": 0,
                }
            u = users[t.assignee]
            u["total"] += 1
            if t.status == TaskStatus.IN_PROGRESS:
                u["in_progress"] += 1
            elif t.status == TaskStatus.PENDING:
                u["pending"] += 1
            elif t.status == TaskStatus.DONE:
                u["done"] += 1
            if t.is_overdue:
                u["overdue"] += 1

        entries = [
            WorkloadEntry(user=uid, **counts)
            for uid, counts in users.items()
        ]
        entries.sort(key=lambda e: e.total, reverse=True)
        return entries
