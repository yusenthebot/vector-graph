"""User model — identity, roles, and permission management."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Role(Enum):
    VIEWER = "viewer"
    MEMBER = "member"
    ADMIN = "admin"
    OWNER = "owner"


@dataclass(frozen=True)
class Permission:
    resource: str
    action: str  # create, read, update, delete

    def matches(self, resource: str, action: str) -> bool:
        resource_ok = self.resource == "*" or self.resource == resource
        action_ok = self.action == "*" or self.action == action
        return resource_ok and action_ok


@dataclass
class User:
    id: str
    name: str
    email: str
    role: Role = Role.MEMBER
    permissions: list[Permission] = field(default_factory=list)

    def has_permission(self, resource: str, action: str) -> bool:
        if self.role == Role.OWNER:
            return True
        return any(p.matches(resource, action) for p in self.permissions)

    def can_manage_tasks(self) -> bool:
        return self.role in (Role.ADMIN, Role.OWNER) or self.has_permission("task", "update")

    def can_create_projects(self) -> bool:
        return self.role in (Role.ADMIN, Role.OWNER) or self.has_permission("project", "create")

    def can_delete(self, resource: str) -> bool:
        return self.has_permission(resource, "delete")

    def is_admin_or_above(self) -> bool:
        return self.role in (Role.ADMIN, Role.OWNER)

    def add_permission(self, permission: Permission) -> None:
        if permission not in self.permissions:
            self.permissions.append(permission)

    def revoke_permission(self, resource: str, action: str) -> bool:
        before = len(self.permissions)
        self.permissions = [
            p for p in self.permissions
            if not (p.resource == resource and p.action == action)
        ]
        return len(self.permissions) < before
