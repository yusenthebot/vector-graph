"""CLI entry point for the TaskFlow demo application."""
from __future__ import annotations

import sys

from taskflow.api.formatters import (
    format_project_summary,
    format_schedule_summary,
    format_task_detail,
    format_task_table,
)
from taskflow.engine.project_engine import ProjectEngine
from taskflow.engine.scheduler import PriorityScheduler
from taskflow.engine.task_engine import TaskEngine
from taskflow.models.task import SubTask, TaskStatus
from taskflow.storage.memory import InMemoryStore
from taskflow.utils.validators import validate_task_id, validate_task_title


def build_demo_data(engine: TaskEngine, project_engine: ProjectEngine) -> None:
    """Populate store with representative demo tasks and one project."""
    from datetime import datetime, timedelta

    from taskflow.models.task import Priority

    project_engine.create_project("p1", "Vector Robotics Nav Stack")

    engine.create_task("task-001", "Implement path planner", priority=Priority.HIGH)
    engine.create_task("task-002", "Write SLAM integration tests", priority=Priority.MEDIUM)
    engine.create_task(
        "task-003",
        "Tune PID controller",
        tags=["depends_on:task-001"],
    )
    engine.create_task(
        "task-004",
        "Deploy to robot hardware",
        due_date=datetime.now() - timedelta(days=1),
    )
    engine.create_task("task-005", "Update README", priority=Priority.LOW)

    project_engine.add_task_to_project("p1", "task-001")
    project_engine.add_task_to_project("p1", "task-002")

    engine.update_status("task-002", TaskStatus.IN_PROGRESS)
    engine.assign_task("task-002", "alice")

    engine.add_subtask("task-001", SubTask("st-1", "Design interface"))
    engine.add_subtask("task-001", SubTask("st-2", "Implement A*"))
    engine.complete_subtask("task-001", "st-1")


def _build_engines() -> tuple[TaskEngine, ProjectEngine, PriorityScheduler]:
    store = InMemoryStore()
    task_engine = TaskEngine(store)
    project_engine = ProjectEngine(store, task_engine)
    scheduler = PriorityScheduler(task_engine)
    return task_engine, project_engine, scheduler


def cmd_list(task_engine: TaskEngine) -> None:
    tasks = task_engine.list_tasks()
    print(format_task_table(tasks))


def cmd_show(task_engine: TaskEngine, task_id: str) -> None:
    task = task_engine.get_task(task_id)
    if task is None:
        print(f"Task not found: {task_id}", file=sys.stderr)
        return
    print(format_task_detail(task))


def cmd_schedule(
    scheduler: PriorityScheduler,
    users: list[str],
) -> None:
    assignments = scheduler.schedule_tasks(users)
    if not assignments:
        print("No assignments made.")
        return
    for task_id, user_id in assignments:
        print(f"  {task_id} -> {user_id}")
    print()
    print(format_schedule_summary(scheduler.get_schedule_summary()))


def cmd_project(project_engine: ProjectEngine, project_id: str) -> None:
    progress = project_engine.get_project_progress(project_id)
    print(format_project_summary(progress))


def main() -> None:
    task_engine, project_engine, scheduler = _build_engines()
    build_demo_data(task_engine, project_engine)

    print("=== TaskFlow Demo ===\n")

    print("-- All Tasks --")
    cmd_list(task_engine)
    print()

    print("-- Task Detail: task-001 --")
    cmd_show(task_engine, "task-001")
    print()

    print("-- Schedule (users: alice, bob) --")
    cmd_schedule(scheduler, ["alice", "bob"])
    print()

    print("-- Project p1 --")
    cmd_project(project_engine, "p1")


if __name__ == "__main__":
    main()
