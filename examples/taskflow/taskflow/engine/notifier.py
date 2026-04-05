"""Notification service — fan-out event broadcasting.

INTENTIONAL CIRCULAR DEPENDENCY:
  notifier.py imports from task_engine.py (TYPE_CHECKING only, but runtime
  method notify_overdue() calls back into self._engine).
  task_engine.py imports NotificationService at runtime.
  This creates a runtime circular reference that vector-graph should detect.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from taskflow.engine.task_engine import TaskEngine

from taskflow.models.task import Task, TaskStatus


class NotificationService:
    """Broadcasts task lifecycle events to registered subscribers.

    Circular dependency with TaskEngine is intentional — demonstrates
    the vector-graph cycle detection feature.
    """

    def __init__(self, engine: "TaskEngine") -> None:
        self._engine = engine
        self._subscribers: list[Callable] = []

    def subscribe(self, callback: Callable) -> None:
        """Register an event callback: callback(event: str, task: Task, **kwargs)."""
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable) -> bool:
        if callback in self._subscribers:
            self._subscribers.remove(callback)
            return True
        return False

    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def notify_created(self, task: Task) -> None:
        self._broadcast("task_created", task)

    def notify_status_change(self, task: Task, old_status: TaskStatus) -> None:
        self._broadcast("status_changed", task, old_status=old_status)

    def notify_assigned(self, task: Task, user_id: str) -> None:
        self._broadcast("task_assigned", task, user_id=user_id)

    def notify_overdue(self) -> None:
        """CIRCULAR: calls back into engine to fetch overdue tasks."""
        overdue = self._engine.get_overdue_tasks()
        for task in overdue:
            self._broadcast("task_overdue", task)

    def notify_subtask_completed(self, task: Task, subtask_id: str) -> None:
        self._broadcast("subtask_completed", task, subtask_id=subtask_id)

    def clear_subscribers(self) -> None:
        self._subscribers.clear()

    def _broadcast(self, event: str, task: Task, **kwargs) -> None:
        for sub in list(self._subscribers):
            try:
                sub(event, task, **kwargs)
            except Exception:
                pass
