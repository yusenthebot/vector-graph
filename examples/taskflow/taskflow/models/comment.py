"""Comment and activity log models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ActivityType(Enum):
    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    ASSIGNED = "assigned"
    COMMENTED = "commented"
    SUBTASK_COMPLETED = "subtask_completed"
    PRIORITY_CHANGED = "priority_changed"
    TAGGED = "tagged"
    DELETED = "deleted"


@dataclass(frozen=True)
class Comment:
    id: str
    task_id: str
    author: str
    text: str
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class ActivityEntry:
    id: str
    task_id: str
    activity_type: ActivityType
    detail: str
    timestamp: datetime = field(default_factory=datetime.now)
