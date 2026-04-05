"""Input validation utilities."""
from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable


def validate_task_id(id: str) -> None:
    """Raise ValueError if task ID contains invalid characters."""
    if not id or not re.match(r"^[a-zA-Z0-9_-]+$", id):
        raise ValueError(f"Invalid task ID: {id!r}")


def validate_task_title(title: str) -> None:
    """Raise ValueError if title is empty or too long."""
    if not title or len(title) > 200:
        raise ValueError(f"Title must be 1-200 chars, got {len(title or '')}")


def validate_email(email: str) -> bool:
    """Return True if email has basic valid structure."""
    return bool(re.match(r"^[^@]+@[^@]+\.[^@]+$", email))


def validate_non_negative(value: float, name: str = "value") -> None:
    """Raise ValueError if value is negative."""
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value}")


def validate_in_range(value: float, lo: float, hi: float, name: str = "value") -> None:
    """Raise ValueError if value is outside [lo, hi]."""
    if not (lo <= value <= hi):
        raise ValueError(f"{name} must be in [{lo}, {hi}], got {value}")


def validate_non_empty_list(items: list, name: str = "list") -> None:
    """Raise ValueError if list is empty."""
    if not items:
        raise ValueError(f"{name} must not be empty")


def validator(func: Callable) -> Callable:
    """Decorator — raises ValueError if the wrapped function returns None."""
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        result = func(*args, **kwargs)
        if result is None:
            raise ValueError(f"Validation failed in {func.__name__}")
        return result
    return wrapper
