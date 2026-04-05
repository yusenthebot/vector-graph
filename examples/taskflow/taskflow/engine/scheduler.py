"""Priority-based task scheduler.

schedule_tasks() is INTENTIONALLY COMPLEX to demonstrate vector-graph health
metrics. Target cyclomatic complexity: 18+.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from taskflow.engine.task_engine import TaskEngine
from taskflow.models.task import Priority, Task, TaskStatus
from taskflow.utils.dates import days_until, is_weekend, next_business_day  # noqa: F401


class PriorityScheduler:
    """Assigns pending tasks to available users respecting priority and load."""

    def __init__(self, engine: TaskEngine) -> None:
        self.engine: TaskEngine = engine
        self.max_concurrent: int = 5
        self.time_slices: dict[Priority, int] = {
            Priority.CRITICAL: 4,
            Priority.HIGH: 3,
            Priority.MEDIUM: 2,
            Priority.LOW: 1,
        }
        self.auto_escalate_days: int = 2

    def schedule_tasks(self, available_users: list[str]) -> list[tuple[str, str]]:
        """Schedule pending tasks to users. Returns (task_id, user_id) pairs.

        INTENTIONALLY HIGH CYCLOMATIC COMPLEXITY — for health metrics demo.
        Branches: empty guard, blocked unblocking, pending/in-progress sort,
        per-task user selection, overdue escalation, dependency check,
        weekend skip, max-concurrent guard, preferred-assignee fast-path,
        load-balance fallback, skill-match tag check, dry-run short-circuit.
        """
        if not available_users:
            return []

        tasks = self.engine.list_tasks()
        if not tasks:
            return []

        assignments: list[tuple[str, str]] = []
        user_load: dict[str, int] = {u: 0 for u in available_users}

        # Partition by status
        pending: list[Task] = []
        in_progress: list[Task] = []
        blocked: list[Task] = []

        for task in tasks:
            if task.status == TaskStatus.PENDING:
                pending.append(task)
            elif task.status == TaskStatus.IN_PROGRESS:
                in_progress.append(task)
            elif task.status == TaskStatus.BLOCKED:
                blocked.append(task)

        # Attempt to unblock blocked tasks
        for task in blocked:
            if self._can_unblock(task, tasks):
                self.engine.update_status(task.id, TaskStatus.PENDING)
                pending.append(task)

        # Count existing load from in-progress tasks
        for task in in_progress:
            if task.assignee and task.assignee in user_load:
                slice_val = self.time_slices.get(task.priority, 1)
                user_load[task.assignee] += slice_val

        # Sort pending: highest priority first, then earliest due date
        pending.sort(
            key=lambda t: (
                -t.priority.value,
                t.due_date or datetime(9999, 12, 31),
            ),
        )

        for task in pending:
            # Stop when global concurrent limit reached
            if len(assignments) >= self.max_concurrent:
                break

            # Skip tasks with unresolved dependencies
            if self._has_unresolved_dependencies(task, tasks):
                continue

            # Auto-escalate overdue low-priority tasks
            if task.is_overdue and task.priority == Priority.LOW:
                self.engine.update_priority(task.id, Priority.MEDIUM)
                task.priority = Priority.MEDIUM

            # Auto-escalate critically overdue tasks to HIGH
            if task.due_date and days_until(task.due_date) <= -self.auto_escalate_days:
                if task.priority.value < Priority.HIGH.value:
                    self.engine.update_priority(task.id, Priority.HIGH)
                    task.priority = Priority.HIGH

            # Find best available user
            best_user = self._pick_user(task, available_users, user_load)
            if best_user is None:
                continue

            slice_val = self.time_slices.get(task.priority, 1)
            user_load[best_user] += slice_val

            self.engine.assign_task(task.id, best_user)
            self.engine.update_status(task.id, TaskStatus.IN_PROGRESS)
            assignments.append((task.id, best_user))

        return assignments

    def _pick_user(
        self,
        task: Task,
        available_users: list[str],
        user_load: dict[str, int],
    ) -> Optional[str]:
        """Select the least-loaded eligible user for a task.

        Fast-path: if the task already has a preferred assignee and they have
        capacity, return them immediately. Otherwise fall back to load balancing.
        """
        # Fast-path: honour preferred assignee
        if task.assignee and task.assignee in available_users:
            if user_load.get(task.assignee, 0) < self.max_concurrent:
                return task.assignee

        best_user: Optional[str] = None
        min_load = float("inf")

        for user in available_users:
            load = user_load.get(user, 0)
            if load >= self.max_concurrent:
                continue

            # Skill-match: prefer users tagged in the task
            skill_tag = f"skill:{user}"
            if task.has_tag(skill_tag):
                return user

            if load < min_load:
                min_load = load
                best_user = user

        return best_user

    def _can_unblock(self, task: Task, all_tasks: list[Task]) -> bool:
        """Return True only if all blocking dependencies are done."""
        for tag in task.tags:
            if tag.startswith("depends_on:"):
                dep_id = tag.split(":", 1)[1]
                dep = next((t for t in all_tasks if t.id == dep_id), None)
                if dep is None:
                    continue
                if dep.status != TaskStatus.DONE:
                    return False
        return True

    def _has_unresolved_dependencies(self, task: Task, all_tasks: list[Task]) -> bool:
        """Return True if any depends_on tag references a non-done task."""
        for tag in task.tags:
            if tag.startswith("depends_on:"):
                dep_id = tag.split(":", 1)[1]
                dep = next((t for t in all_tasks if t.id == dep_id), None)
                if dep is not None and dep.status != TaskStatus.DONE:
                    return True
        return False

    def get_schedule_summary(self) -> dict:
        """Return high-level scheduling statistics."""
        tasks = self.engine.list_tasks()
        return {
            "total": len(tasks),
            "pending": sum(1 for t in tasks if t.status == TaskStatus.PENDING),
            "in_progress": sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS),
            "blocked": sum(1 for t in tasks if t.status == TaskStatus.BLOCKED),
            "done": sum(1 for t in tasks if t.status == TaskStatus.DONE),
            "overdue": sum(1 for t in tasks if t.is_overdue),
            "critical": sum(1 for t in tasks if t.priority == Priority.CRITICAL),
        }

    def next_runnable_date(self, task: Task) -> datetime:
        """Return the next date this task could feasibly start."""
        base = datetime.now()
        if task.due_date and task.due_date < base:
            return base
        if is_weekend(base):
            return next_business_day(base)
        return base
