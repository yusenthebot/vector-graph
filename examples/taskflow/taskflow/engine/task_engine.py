"""Core task management engine — CRUD + status transitions."""
from __future__ import annotations

from datetime import datetime
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

    def search_tasks(
        self,
        keyword: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        priority: Optional[Priority] = None,
        assignee: Optional[str] = None,
        tag: Optional[str] = None,
        overdue_only: bool = False,
        sort_by: str = "priority",
        ascending: bool = False,
    ) -> list[Task]:
        """Search tasks with multi-criteria filtering and sorting.

        Args:
            keyword: Case-insensitive match against title and description.
            status: Exact status filter.
            priority: Minimum priority threshold (inclusive).
            assignee: Exact assignee filter.
            tag: Tasks must contain this tag.
            overdue_only: Only return overdue tasks.
            sort_by: One of 'priority', 'created', 'due_date', 'status'.
            ascending: Sort direction (default: descending).
        """
        tasks = self.list_tasks(status=status, assignee=assignee)

        if keyword:
            kw = keyword.lower()
            tasks = [
                t for t in tasks
                if kw in t.title.lower() or kw in t.description.lower()
            ]
        if priority is not None:
            tasks = [t for t in tasks if t.priority.value >= priority.value]
        if tag is not None:
            tasks = [t for t in tasks if t.has_tag(tag)]
        if overdue_only:
            tasks = [t for t in tasks if t.is_overdue]

        sort_keys = {
            "priority": lambda t: t.priority.value,
            "created": lambda t: t.created_at,
            "due_date": lambda t: t.due_date or datetime(9999, 12, 31),
            "status": lambda t: t.status.value,
        }
        key_fn = sort_keys.get(sort_by, sort_keys["priority"])
        tasks.sort(key=key_fn, reverse=not ascending)
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

    # --- Dependencies ---

    def add_dependency(self, task_id: str, depends_on_id: str) -> bool:
        """Add a dependency: task_id depends on depends_on_id.

        Returns False if either task doesn't exist, dependency already exists,
        a task depends on itself, or adding would create a cycle.
        """
        if task_id == depends_on_id:
            return False
        task = self.get_task(task_id)
        dep = self.get_task(depends_on_id)
        if task is None or dep is None:
            return False
        if depends_on_id in task.dependencies:
            return False
        if self._would_create_cycle(task_id, depends_on_id):
            return False
        task.dependencies.append(depends_on_id)
        self._save_task(task)
        return True

    def remove_dependency(self, task_id: str, depends_on_id: str) -> bool:
        task = self.get_task(task_id)
        if task is None or depends_on_id not in task.dependencies:
            return False
        task.dependencies.remove(depends_on_id)
        self._save_task(task)
        return True

    def get_dependency_chain(self, task_id: str) -> list[str]:
        """Return all transitive dependencies (topological order)."""
        visited: list[str] = []
        self._collect_deps(task_id, visited, set())
        return visited

    def get_blocked_reason(self, task_id: str) -> list[str]:
        """Return IDs of incomplete dependencies blocking this task."""
        task = self.get_task(task_id)
        if task is None:
            return []
        blocked_by: list[str] = []
        for dep_id in task.dependencies:
            dep = self.get_task(dep_id)
            if dep is not None and dep.status != TaskStatus.DONE:
                blocked_by.append(dep_id)
        return blocked_by

    def _would_create_cycle(self, task_id: str, new_dep_id: str) -> bool:
        """Check if adding new_dep_id as dependency of task_id creates a cycle."""
        visited: set[str] = set()
        return self._reaches(new_dep_id, task_id, visited)

    def _reaches(self, from_id: str, target_id: str, visited: set[str]) -> bool:
        """DFS: can we reach target_id starting from from_id via dependencies?"""
        if from_id == target_id:
            return True
        if from_id in visited:
            return False
        visited.add(from_id)
        task = self.get_task(from_id)
        if task is None:
            return False
        for dep_id in task.dependencies:
            if self._reaches(dep_id, target_id, visited):
                return True
        return False

    def _collect_deps(self, task_id: str, result: list[str], visited: set[str]) -> None:
        task = self.get_task(task_id)
        if task is None:
            return
        for dep_id in task.dependencies:
            if dep_id not in visited:
                visited.add(dep_id)
                self._collect_deps(dep_id, result, visited)
                result.append(dep_id)

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
            "dependencies": list(task.dependencies),
            "subtasks": [
                {"id": st.id, "title": st.title, "done": st.done}
                for st in task.subtasks
            ],
            "created_at": task.created_at.isoformat(),
            "due_date": task.due_date.isoformat() if task.due_date else None,
        }

    def _deserialize_task(self, data: dict) -> Task:
        subtasks = [
            SubTask(id=s["id"], title=s["title"], done=s.get("done", False))
            for s in data.get("subtasks", [])
        ]
        created_at = (
            datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now()
        )
        due_raw = data.get("due_date")
        due_date = datetime.fromisoformat(due_raw) if due_raw else None
        return Task(
            id=data["id"],
            title=data["title"],
            description=data.get("description", ""),
            status=TaskStatus(data.get("status", "pending")),
            priority=Priority(data.get("priority", 2)),
            assignee=data.get("assignee"),
            project_id=data.get("project_id"),
            tags=list(data.get("tags", [])),
            dependencies=list(data.get("dependencies", [])),
            subtasks=subtasks,
            created_at=created_at,
            due_date=due_date,
        )
