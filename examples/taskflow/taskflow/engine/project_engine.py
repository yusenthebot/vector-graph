"""Project lifecycle management engine."""
from __future__ import annotations

from typing import Optional

from taskflow.engine.task_engine import TaskEngine
from taskflow.models.project import Project, ProjectConfig
from taskflow.models.task import TaskStatus
from taskflow.storage.base import StorageBackend


class ProjectEngine:
    """Manages project creation, membership, and progress tracking."""

    def __init__(self, store: StorageBackend, task_engine: TaskEngine) -> None:
        self.store: StorageBackend = store
        self.task_engine: TaskEngine = task_engine

    # --- Create ---

    def create_project(self, id: str, name: str, **kwargs) -> Project:
        project = Project(id=id, name=name, **kwargs)
        self._save_project(project)
        return project

    # --- Read ---

    def get_project(self, id: str) -> Optional[Project]:
        data = self.store.load("projects", id)
        if data is None:
            return None
        config_data = data.get("config", {})
        config = ProjectConfig(
            max_tasks=config_data.get("max_tasks", 100),
            allow_subtasks=config_data.get("allow_subtasks", True),
            require_assignee=config_data.get("require_assignee", False),
            auto_close_completed=config_data.get("auto_close_completed", True),
        )
        return Project(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            owner=data.get("owner"),
            config=config,
            task_ids=list(data.get("task_ids", [])),
        )

    def list_projects(self) -> list[Project]:
        all_data = self.store.list_all("projects")
        projects = []
        for data in all_data:
            p = self.get_project(data["id"])
            if p is not None:
                projects.append(p)
        return projects

    # --- Task membership ---

    def add_task_to_project(self, project_id: str, task_id: str) -> bool:
        project = self.get_project(project_id)
        if project is None:
            return False
        task = self.task_engine.get_task(task_id)
        if task is None:
            return False
        if not project.add_task(task_id):
            return False
        task.project_id = project_id
        self.task_engine._save_task(task)
        self._save_project(project)
        return True

    def remove_task_from_project(self, project_id: str, task_id: str) -> bool:
        project = self.get_project(project_id)
        if project is None:
            return False
        removed = project.remove_task(task_id)
        if removed:
            self._save_project(project)
        return removed

    # --- Progress ---

    def get_project_progress(self, project_id: str) -> dict:
        project = self.get_project(project_id)
        if project is None:
            return {"error": "not found"}
        tasks = [self.task_engine.get_task(tid) for tid in project.task_ids]
        tasks = [t for t in tasks if t is not None]
        total = len(tasks)
        done = sum(1 for t in tasks if t.status == TaskStatus.DONE)
        in_progress = sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS)
        blocked = sum(1 for t in tasks if t.status == TaskStatus.BLOCKED)
        return {
            "project": project.name,
            "total_tasks": total,
            "completed": done,
            "in_progress": in_progress,
            "blocked": blocked,
            "progress": done / total if total > 0 else 0.0,
        }

    def is_complete(self, project_id: str) -> bool:
        progress = self.get_project_progress(project_id)
        if "error" in progress:
            return False
        total = progress["total_tasks"]
        return total > 0 and progress["completed"] == total

    # --- Internal ---

    def _save_project(self, project: Project) -> None:
        self.store.save(
            "projects",
            project.id,
            {
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "owner": project.owner,
                "config": {
                    "max_tasks": project.config.max_tasks,
                    "allow_subtasks": project.config.allow_subtasks,
                    "require_assignee": project.config.require_assignee,
                    "auto_close_completed": project.config.auto_close_completed,
                },
                "task_ids": list(project.task_ids),
            },
        )
