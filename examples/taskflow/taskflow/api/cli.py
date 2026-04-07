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
from taskflow.models.task import Priority, SubTask, TaskStatus
from taskflow.storage.memory import InMemoryStore
from taskflow.utils.validators import validate_task_id, validate_task_title


def build_demo_data(engine: TaskEngine, project_engine: ProjectEngine) -> None:
    """Populate store with representative demo tasks and one project."""
    from datetime import datetime, timedelta

    from taskflow.models.task import Priority

    project_engine.create_project("p1", "Vector Robotics Nav Stack")

    engine.create_task("task-001", "Implement path planner", priority=Priority.HIGH)
    engine.create_task("task-002", "Write SLAM integration tests", priority=Priority.MEDIUM)
    engine.create_task("task-003", "Tune PID controller")
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

    # Dependencies: task-003 depends on task-001, task-004 depends on task-003
    engine.add_dependency("task-003", "task-001")
    engine.add_dependency("task-004", "task-003")


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


def cmd_search(task_engine: TaskEngine, label: str, **kwargs) -> None:
    print(f"-- Search: {label} --")
    tasks = task_engine.search_tasks(**kwargs)
    if not tasks:
        print("  No matching tasks.")
    else:
        print(format_task_table(tasks))
    print()


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

    cmd_search(task_engine, "keyword='planner'", keyword="planner")
    cmd_search(task_engine, "priority >= HIGH", priority=Priority.HIGH)
    cmd_search(task_engine, "overdue only", overdue_only=True)

    print("-- Dependencies: task-003 --")
    cmd_show(task_engine, "task-003")
    print()

    print("-- Dependency chain: task-004 --")
    chain = task_engine.get_dependency_chain("task-004")
    print(f"  task-004 transitively depends on: {' -> '.join(chain)}")
    print()

    print("-- Blocked reason: task-003 --")
    blocked_by = task_engine.get_blocked_reason("task-003")
    if blocked_by:
        print(f"  Blocked by: {', '.join(blocked_by)}")
    else:
        print("  Not blocked")
    print()

    print("-- Cycle detection: task-001 -> task-003 (would create cycle) --")
    ok = task_engine.add_dependency("task-001", "task-003")
    print(f"  add_dependency('task-001', 'task-003') = {ok}")
    print()

    print("-- Project p1 --")
    cmd_project(project_engine, "p1")


if __name__ == "__main__":
    main()
