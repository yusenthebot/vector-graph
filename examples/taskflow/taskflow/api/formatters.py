"""Output formatters for CLI and other text-based interfaces."""
from __future__ import annotations

from taskflow.models.task import Task


def format_task_table(tasks: list[Task]) -> str:
    """Render tasks as a plain-text table."""
    if not tasks:
        return "No tasks."
    header = f"{'ID':<20} {'Title':<30} {'Status':<15} {'Priority':<10}"
    separator = "-" * len(header)
    lines = [header, separator]
    for t in tasks:
        lines.append(
            f"{t.id:<20} {t.title[:30]:<30} {t.status.value:<15} {t.priority.name:<10}"
        )
    return "\n".join(lines)


def format_project_summary(data: dict) -> str:
    """Format project progress dict as a single summary line."""
    name = data.get("project", "?")
    done = data.get("completed", 0)
    total = data.get("total_tasks", 0)
    progress = data.get("progress", 0.0)
    return f"{name}: {done}/{total} tasks complete ({progress:.0%})"


def format_task_detail(task: Task) -> str:
    """Multi-line detailed view of a single task."""
    lines = [
        f"ID:          {task.id}",
        f"Title:       {task.title}",
        f"Status:      {task.status.value}",
        f"Priority:    {task.priority.name}",
        f"Assignee:    {task.assignee or '(unassigned)'}",
        f"Project:     {task.project_id or '(none)'}",
        f"Tags:        {', '.join(task.tags) or '(none)'}",
        f"Overdue:     {task.is_overdue}",
        f"Completion:  {task.completion_ratio:.0%}",
    ]
    if task.subtasks:
        lines.append("Subtasks:")
        for st in task.subtasks:
            mark = "x" if st.done else " "
            lines.append(f"  [{mark}] {st.id}: {st.title}")
    return "\n".join(lines)


def format_schedule_summary(summary: dict) -> str:
    """Format scheduler summary dict as a human-readable string."""
    return (
        f"Tasks — total: {summary.get('total', 0)}, "
        f"pending: {summary.get('pending', 0)}, "
        f"in-progress: {summary.get('in_progress', 0)}, "
        f"done: {summary.get('done', 0)}, "
        f"blocked: {summary.get('blocked', 0)}, "
        f"overdue: {summary.get('overdue', 0)}"
    )
