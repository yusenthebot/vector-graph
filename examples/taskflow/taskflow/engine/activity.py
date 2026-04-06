"""Activity tracker — records task lifecycle events as an audit log.

Subscribes to NotificationService events and persists ActivityEntry records
in the storage backend. Also manages comments on tasks.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from taskflow.models.comment import ActivityEntry, ActivityType, Comment
from taskflow.models.task import Task, TaskStatus
from taskflow.storage.base import StorageBackend
from taskflow.utils.validators import validate_task_id


class ActivityTracker:
    """Records task events and manages comments.

    Hooks into the NotificationService as a subscriber to automatically
    capture all task lifecycle events.
    """

    def __init__(self, store: StorageBackend) -> None:
        self._store = store
        self._comment_seq = 0
        self._activity_seq = 0

    # --- Comments ---

    def add_comment(self, task_id: str, author: str, text: str) -> Comment:
        validate_task_id(task_id)
        if not author or not text.strip():
            raise ValueError("Author and text must be non-empty")
        self._comment_seq += 1
        comment = Comment(
            id=f"cmt-{self._comment_seq:04d}",
            task_id=task_id,
            author=author,
            text=text.strip(),
        )
        self._store.save("comments", comment.id, self._serialize_comment(comment))
        self._record(task_id, ActivityType.COMMENTED, f"{author}: {text.strip()}")
        return comment

    def get_comments(self, task_id: str) -> list[Comment]:
        all_data = self._store.list_all("comments")
        comments = [self._deserialize_comment(d) for d in all_data if d["task_id"] == task_id]
        comments.sort(key=lambda c: c.created_at)
        return comments

    def comment_count(self, task_id: str) -> int:
        return len(self.get_comments(task_id))

    # --- Activity log ---

    def get_activity(self, task_id: str) -> list[ActivityEntry]:
        all_data = self._store.list_all("activity")
        entries = [self._deserialize_entry(d) for d in all_data if d["task_id"] == task_id]
        entries.sort(key=lambda e: e.timestamp)
        return entries

    def get_recent_activity(self, limit: int = 20) -> list[ActivityEntry]:
        all_data = self._store.list_all("activity")
        entries = [self._deserialize_entry(d) for d in all_data]
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries[:limit]

    # --- Notification subscriber callback ---

    def on_event(self, event: str, task: Task, **kwargs) -> None:
        """Subscriber callback for NotificationService."""
        type_map = {
            "task_created": ActivityType.CREATED,
            "status_changed": ActivityType.STATUS_CHANGED,
            "task_assigned": ActivityType.ASSIGNED,
            "subtask_completed": ActivityType.SUBTASK_COMPLETED,
            "task_overdue": ActivityType.STATUS_CHANGED,
        }
        activity_type = type_map.get(event)
        if activity_type is None:
            return

        detail = self._build_detail(event, task, **kwargs)
        self._record(task.id, activity_type, detail)

    # --- Internal ---

    def _record(self, task_id: str, activity_type: ActivityType, detail: str) -> None:
        self._activity_seq += 1
        entry = ActivityEntry(
            id=f"act-{self._activity_seq:04d}",
            task_id=task_id,
            activity_type=activity_type,
            detail=detail,
        )
        self._store.save("activity", entry.id, self._serialize_entry(entry))

    def _build_detail(self, event: str, task: Task, **kwargs) -> str:
        if event == "task_created":
            return f"Task '{task.title}' created"
        if event == "status_changed":
            old = kwargs.get("old_status")
            old_val = old.value if isinstance(old, TaskStatus) else str(old)
            return f"{old_val} -> {task.status.value}"
        if event == "task_assigned":
            return f"Assigned to {kwargs.get('user_id', '?')}"
        if event == "subtask_completed":
            return f"Subtask {kwargs.get('subtask_id', '?')} completed"
        if event == "task_overdue":
            return "Task is overdue"
        return event

    def _serialize_comment(self, comment: Comment) -> dict:
        return {
            "id": comment.id,
            "task_id": comment.task_id,
            "author": comment.author,
            "text": comment.text,
            "created_at": comment.created_at.isoformat(),
        }

    def _deserialize_comment(self, data: dict) -> Comment:
        return Comment(
            id=data["id"],
            task_id=data["task_id"],
            author=data["author"],
            text=data["text"],
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    def _serialize_entry(self, entry: ActivityEntry) -> dict:
        return {
            "id": entry.id,
            "task_id": entry.task_id,
            "activity_type": entry.activity_type.value,
            "detail": entry.detail,
            "timestamp": entry.timestamp.isoformat(),
        }

    def _deserialize_entry(self, data: dict) -> ActivityEntry:
        return ActivityEntry(
            id=data["id"],
            task_id=data["task_id"],
            activity_type=ActivityType(data["activity_type"]),
            detail=data["detail"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )
