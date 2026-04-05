"""Metrics collector — intentionally oversized for health metrics demo.

MetricsCollector is a GOD CLASS: it accumulates counter, gauge, histogram,
timer, rate, tag, snapshot, aggregation, and export responsibilities.
vector-graph should flag it as a high-method-count health issue.
"""
from __future__ import annotations

import json
import time
from typing import Any


class MetricsCollector:
    """GOD CLASS: too many responsibilities.

    vector-graph health analysis should highlight this class for refactoring.
    Method count: 30+, spanning unrelated concerns.
    """

    def __init__(self) -> None:
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}
        self._timers: dict[str, float] = {}
        self._tags: dict[str, list[str]] = {}
        self._rates: dict[str, list[tuple[float, float]]] = {}

    # --- Counters ---

    def increment(self, name: str, value: float = 1) -> None:
        self._counters[name] = self._counters.get(name, 0) + value

    def decrement(self, name: str, value: float = 1) -> None:
        self._counters[name] = self._counters.get(name, 0) - value

    def get_counter(self, name: str) -> float:
        return self._counters.get(name, 0)

    def reset_counter(self, name: str) -> None:
        self._counters.pop(name, None)

    def get_all_counters(self) -> dict[str, float]:
        return dict(self._counters)

    # --- Gauges ---

    def set_gauge(self, name: str, value: float) -> None:
        self._gauges[name] = value

    def get_gauge(self, name: str) -> float:
        return self._gauges.get(name, 0)

    def reset_gauge(self, name: str) -> None:
        self._gauges.pop(name, None)

    def get_all_gauges(self) -> dict[str, float]:
        return dict(self._gauges)

    # --- Histograms ---

    def record_histogram(self, name: str, value: float) -> None:
        self._histograms.setdefault(name, []).append(value)

    def get_histogram(self, name: str) -> list[float]:
        return list(self._histograms.get(name, []))

    def get_histogram_avg(self, name: str) -> float:
        h = self.get_histogram(name)
        return sum(h) / len(h) if h else 0.0

    def get_histogram_min(self, name: str) -> float:
        h = self.get_histogram(name)
        return min(h) if h else 0.0

    def get_histogram_max(self, name: str) -> float:
        h = self.get_histogram(name)
        return max(h) if h else 0.0

    def get_histogram_p50(self, name: str) -> float:
        return self._percentile(name, 50)

    def get_histogram_p90(self, name: str) -> float:
        return self._percentile(name, 90)

    def get_histogram_p99(self, name: str) -> float:
        return self._percentile(name, 99)

    def reset_histogram(self, name: str) -> None:
        self._histograms.pop(name, None)

    # --- Timers ---

    def start_timer(self, name: str) -> None:
        self._timers[name] = time.monotonic()

    def stop_timer(self, name: str) -> float:
        """Stop timer and record elapsed seconds into histogram. Returns elapsed."""
        started = self._timers.pop(name, None)
        if started is None:
            return 0.0
        elapsed = time.monotonic() - started
        self.record_histogram(f"timer.{name}", elapsed)
        return elapsed

    # --- Tags ---

    def tag(self, name: str, tag: str) -> None:
        self._tags.setdefault(name, []).append(tag)

    def get_tags(self, name: str) -> list[str]:
        return list(self._tags.get(name, []))

    # --- Rates ---

    def record_event(self, name: str) -> None:
        self._rates.setdefault(name, []).append((time.monotonic(), 1.0))

    def get_rate(self, name: str, window_seconds: float = 60.0) -> float:
        """Events per second over the last window_seconds."""
        now = time.monotonic()
        events = self._rates.get(name, [])
        recent = [v for ts, v in events if now - ts <= window_seconds]
        return sum(recent) / window_seconds if recent else 0.0

    # --- Aggregation ---

    def reset_all(self) -> None:
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._timers.clear()
        self._tags.clear()
        self._rates.clear()

    def get_all_metrics(self) -> dict[str, Any]:
        return {
            "counters": self.get_all_counters(),
            "gauges": self.get_all_gauges(),
        }

    def snapshot(self) -> dict[str, Any]:
        """Full snapshot including histograms and tags."""
        return {
            "counters": self.get_all_counters(),
            "gauges": self.get_all_gauges(),
            "histograms": {k: list(v) for k, v in self._histograms.items()},
            "tags": {k: list(v) for k, v in self._tags.items()},
        }

    def merge(self, other: "MetricsCollector") -> None:
        """Merge another collector's data into this one."""
        for k, v in other._counters.items():
            self.increment(k, v)
        for k, v in other._gauges.items():
            self.set_gauge(k, v)
        for k, vals in other._histograms.items():
            for v in vals:
                self.record_histogram(k, v)

    # --- Export ---

    def export_json(self) -> str:
        return json.dumps(self.get_all_metrics())

    def export_snapshot_json(self) -> str:
        return json.dumps(self.snapshot(), default=str)

    # --- Internals ---

    def _percentile(self, name: str, p: int) -> float:
        h = sorted(self.get_histogram(name))
        if not h:
            return 0.0
        idx = int(len(h) * p / 100)
        return h[min(idx, len(h) - 1)]
