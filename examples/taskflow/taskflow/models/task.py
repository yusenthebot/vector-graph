"""Task model — core domain object."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class Priority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass(frozen=True)
class SubTask:
    id: str
    title: str
    done: bool = False


@dataclass
class Task:
    id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    priority: Priority = Priority.MEDIUM
    assignee: Optional[str] = None
    project_id: Optional[str] = None
    subtasks: list[SubTask] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    due_date: Optional[datetime] = None

    @property
    def is_overdue(self) -> bool:
        if self.due_date and self.status != TaskStatus.DONE:
            return datetime.now() > self.due_date
        return False

    @property
    def completion_ratio(self) -> float:
        if not self.subtasks:
            return 1.0 if self.status == TaskStatus.DONE else 0.0
        done = sum(1 for s in self.subtasks if s.done)
        return done / len(self.subtasks)

    def add_subtask(self, subtask: SubTask) -> None:
        self.subtasks.append(subtask)

    def complete_subtask(self, subtask_id: str) -> bool:
        for i, st in enumerate(self.subtasks):
            if st.id == subtask_id:
                self.subtasks[i] = SubTask(id=st.id, title=st.title, done=True)
                return True
        return False

    def depends_on(self, task_id: str) -> bool:
        return task_id in self.dependencies

    def has_tag(self, tag: str) -> bool:
        return tag in self.tags

    def is_assigned(self) -> bool:
        return self.assignee is not None

    def is_blocking(self) -> bool:
        return self.status == TaskStatus.BLOCKED

    def is_terminal(self) -> bool:
        return self.status in (TaskStatus.DONE, TaskStatus.CANCELLED)
