"""Core task management engine — CRUD + status transitions."""
from __future__ import annotations

from typing import Optional

from taskflow.engine.notifier import NotificationService  # CIRCULAR DEP (intentional)
from taskflow.models.task import Priority, SubTask, Task, TaskStatus
from taskflow.storage.base import StorageBackend
from taskflow.storage.memory import InMemoryStore
from taskflow.utils.validators import validate_task_id, validate_task_title


class TaskEngine:
    """Core task management engine.

    Owns the lifecycle of Task objects: create, read, update, delete.
    Circular import with NotificationService is intentional for demo purposes.
    """

    def __init__(self, store: Optional[StorageBackend] = None) -> None:
        # TYPE INFERENCE DEMO: vector-graph infers self.store: StorageBackend
        # from the branch `store or InMemoryStore()`
        self.store: StorageBackend = store or InMemoryStore()
        # CIRCULAR: NotificationService holds a back-reference to this engine
        self.notifier: NotificationService = NotificationService(self)

    # --- Create ---

    def create_task(self, id: str, title: str, **kwargs) -> Task:
        validate_task_id(id)
        validate_task_title(title)
        task = Task(id=id, title=title, **kwargs)
        self._save_task(task)
        self.notifier.notify_created(task)
        return task

    # --- Read ---

    def get_task(self, id: str) -> Optional[Task]:
        data = self.store.load("tasks", id)
        if data is None:
            return None
        return self._deserialize_task(data)

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        assignee: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> list[Task]:
        all_data = self.store.list_all("tasks")
        tasks = [self._deserialize_task(d) for d in all_data]
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        if assignee is not None:
            tasks = [t for t in tasks if t.assignee == assignee]
        if project_id is not None:
            tasks = [t for t in tasks if t.project_id == project_id]
        return tasks

    def get_overdue_tasks(self) -> list[Task]:
        return [t for t in self.list_tasks() if t.is_overdue]

    def count_tasks(self) -> int:
        return self.store.count("tasks")

    # --- Update ---

    def update_status(self, id: str, status: TaskStatus) -> bool:
        task = self.get_task(id)
        if task is None:
            return False
        old_status = task.status
        task.status = status
        self._save_task(task)
        self.notifier.notify_status_change(task, old_status)
        return True

    def assign_task(self, task_id: str, user_id: str) -> bool:
        task = self.get_task(task_id)
        if task is None:
            return False
        task.assignee = user_id
        self._save_task(task)
        self.notifier.notify_assigned(task, user_id)
        return True

    def add_subtask(self, task_id: str, subtask: SubTask) -> bool:
        task = self.get_task(task_id)
        if task is None:
            return False
        task.add_subtask(subtask)
        self._save_task(task)
        return True

    def complete_subtask(self, task_id: str, subtask_id: str) -> bool:
        task = self.get_task(task_id)
        if task is None:
            return False
        ok = task.complete_subtask(subtask_id)
        if ok:
            self._save_task(task)
            self.notifier.notify_subtask_completed(task, subtask_id)
        return ok

    def update_priority(self, task_id: str, priority: Priority) -> bool:
        task = self.get_task(task_id)
        if task is None:
            return False
        task.priority = priority
        self._save_task(task)
        return True

    def tag_task(self, task_id: str, tag: str) -> bool:
        task = self.get_task(task_id)
        if task is None:
            return False
        if tag not in task.tags:
            task.tags.append(tag)
            self._save_task(task)
        return True

    # --- Delete ---

    def delete_task(self, task_id: str) -> bool:
        return self.store.delete("tasks", task_id)

    # --- Internal ---

    def _save_task(self, task: Task) -> None:
        self.store.save("tasks", task.id, self._serialize_task(task))

    def _serialize_task(self, task: Task) -> dict:
        return {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "status": task.status.value,
            "priority": task.priority.value,
            "assignee": task.assignee,
            "project_id": task.project_id,
            "tags": list(task.tags),
            "subtasks": [
                {"id": st.id, "title": st.title, "done": st.done}
                for st in task.subtasks
            ],
        }

    def _deserialize_task(self, data: dict) -> Task:
        subtasks = [
            SubTask(id=s["id"], title=s["title"], done=s.get("done", False))
            for s in data.get("subtasks", [])
        ]
        return Task(
            id=data["id"],
            title=data["title"],
            description=data.get("description", ""),
            status=TaskStatus(data.get("status", "pending")),
            priority=Priority(data.get("priority", 2)),
            assignee=data.get("assignee"),
            project_id=data.get("project_id"),
            tags=list(data.get("tags", [])),
            subtasks=subtasks,
        )
