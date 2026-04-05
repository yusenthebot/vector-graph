"""Unit tests for taskflow.models.project and engine.project_engine."""
from __future__ import annotations

import pytest

from taskflow.engine.project_engine import ProjectEngine
from taskflow.engine.task_engine import TaskEngine
from taskflow.models.project import Project, ProjectConfig
from taskflow.models.task import TaskStatus
from taskflow.storage.memory import InMemoryStore


def make_engines() -> tuple[TaskEngine, ProjectEngine]:
    store = InMemoryStore()
    te = TaskEngine(store)
    pe = ProjectEngine(store, te)
    return te, pe


class TestProjectModel:
    def test_add_task_increments_count(self) -> None:
        p = Project(id="p1", name="Alpha")
        assert p.add_task("t1")
        assert p.task_count == 1

    def test_add_task_at_capacity_returns_false(self) -> None:
        config = ProjectConfig(max_tasks=1)
        p = Project(id="p1", name="Alpha", config=config)
        p.add_task("t1")
        assert not p.add_task("t2")

    def test_remove_task_returns_true_when_present(self) -> None:
        p = Project(id="p1", name="Alpha")
        p.add_task("t1")
        assert p.remove_task("t1")
        assert p.task_count == 0

    def test_remove_missing_task_returns_false(self) -> None:
        p = Project(id="p1", name="Alpha")
        assert not p.remove_task("missing")

    def test_has_task(self) -> None:
        p = Project(id="p1", name="Alpha")
        p.add_task("t1")
        assert p.has_task("t1")
        assert not p.has_task("t2")


class TestProjectEngine:
    def test_create_and_retrieve_project(self) -> None:
        _, pe = make_engines()
        pe.create_project("p1", "Demo Project")
        project = pe.get_project("p1")
        assert project is not None
        assert project.name == "Demo Project"

    def test_get_missing_project_returns_none(self) -> None:
        _, pe = make_engines()
        assert pe.get_project("missing") is None

    def test_add_task_to_project(self) -> None:
        te, pe = make_engines()
        pe.create_project("p1", "Demo")
        te.create_task("t1", "Task One")
        assert pe.add_task_to_project("p1", "t1")
        project = pe.get_project("p1")
        assert project is not None
        assert project.has_task("t1")

    def test_project_progress_all_done(self) -> None:
        te, pe = make_engines()
        pe.create_project("p1", "Demo")
        te.create_task("t1", "Task One")
        pe.add_task_to_project("p1", "t1")
        te.update_status("t1", TaskStatus.DONE)
        progress = pe.get_project_progress("p1")
        assert progress["completed"] == 1
        assert progress["total_tasks"] == 1
        assert progress["progress"] == pytest.approx(1.0)

    def test_is_complete_empty_project(self) -> None:
        _, pe = make_engines()
        pe.create_project("p1", "Empty")
        assert not pe.is_complete("p1")

    def test_list_projects(self) -> None:
        _, pe = make_engines()
        pe.create_project("p1", "A")
        pe.create_project("p2", "B")
        projects = pe.list_projects()
        assert len(projects) == 2
