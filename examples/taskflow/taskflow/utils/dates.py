"""Date/time utilities for task scheduling."""
from __future__ import annotations

from datetime import datetime, timedelta


def days_until(dt: datetime) -> int:
    """Return signed number of days until dt from now."""
    return (dt - datetime.now()).days


def is_weekend(dt: datetime) -> bool:
    """Return True if dt falls on Saturday or Sunday."""
    return dt.weekday() >= 5


def next_business_day(dt: datetime) -> datetime:
    """Return the next weekday after dt."""
    d = dt + timedelta(days=1)
    while is_weekend(d):
        d += timedelta(days=1)
    return d


def business_days_between(start: datetime, end: datetime) -> int:
    """Count weekdays between start and end (inclusive of end, exclusive of start)."""
    count = 0
    current = start + timedelta(days=1)
    while current <= end:
        if not is_weekend(current):
            count += 1
        current += timedelta(days=1)
    return count


def is_past(dt: datetime) -> bool:
    """Return True if dt is in the past."""
    return datetime.now() > dt


def clamp_to_future(dt: datetime) -> datetime:
    """If dt is in the past, return now instead."""
    now = datetime.now()
    return dt if dt > now else now


def format_iso8601_extended(dt: datetime) -> str:
    """INTENTIONAL ORPHAN — never called anywhere in the codebase.

    Formats a datetime in extended ISO 8601 format including microseconds.
    vector-graph should detect this as an orphan (no incoming CALLS edges).
    """
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
