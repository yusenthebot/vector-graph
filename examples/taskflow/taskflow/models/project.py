"""Project model — groups tasks under a shared context."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class ProjectConfig:
    max_tasks: int = 100
    allow_subtasks: bool = True
    require_assignee: bool = False
    auto_close_completed: bool = True


@dataclass
class Project:
    id: str
    name: str
    description: str = ""
    owner: Optional[str] = None
    config: ProjectConfig = field(default_factory=ProjectConfig)
    task_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def task_count(self) -> int:
        return len(self.task_ids)

    def add_task(self, task_id: str) -> bool:
        if self.task_count >= self.config.max_tasks:
            return False
        if task_id not in self.task_ids:
            self.task_ids.append(task_id)
        return True

    def remove_task(self, task_id: str) -> bool:
        if task_id in self.task_ids:
            self.task_ids.remove(task_id)
            return True
        return False

    def is_at_capacity(self) -> bool:
        return self.task_count >= self.config.max_tasks

    def has_task(self, task_id: str) -> bool:
        return task_id in self.task_ids
