"""Track file changes and compute diffs against the knowledge graph.

Records before/after snapshots around graph mutations to produce structured
ChangeEvent objects that describe what nodes were added, modified, or removed,
along with blast-radius impact metadata.
"""

from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from vector_graph._types import NodeLabel
from vector_graph.graph.knowledge_graph import KnowledgeGraph


@dataclass(frozen=True)
class ChangeEvent:
    """A single tracked file change with before/after node diff."""

    timestamp: float
    file_path: str
    change_type: str  # "created" | "modified" | "deleted"
    nodes_added: tuple[str, ...] = ()
    nodes_modified: tuple[str, ...] = ()
    nodes_removed: tuple[str, ...] = ()
    risk: str = "LOW"
    affected_count: int = 0
    affected_groups: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict representation."""
        return {
            "timestamp": self.timestamp,
            "file": self.file_path,
            "type": self.change_type,
            "nodes_added": list(self.nodes_added),
            "nodes_modified": list(self.nodes_modified),
            "nodes_removed": list(self.nodes_removed),
            "impact": {
                "risk": self.risk,
                "affected_count": self.affected_count,
                "affected_groups": list(self.affected_groups),
            },
        }


# Labels that represent structural meta-nodes, not code symbols
_SKIP_LABELS = frozenset({NodeLabel.FILE, NodeLabel.FOLDER})


class ChangeTracker:
    """Track file changes with before/after graph state comparison.

    Usage pattern:
        1. Call snapshot_file(path) BEFORE the graph is mutated for that file.
        2. After the graph has been updated, call record_change(path, event_type).
        3. Optionally register listeners with on_change(callback).
    """

    MAX_EVENTS: int = 500

    def __init__(self, graph: KnowledgeGraph) -> None:
        self._graph = graph
        self._events: deque[ChangeEvent] = deque(maxlen=self.MAX_EVENTS)
        self._session_start: float = time.time()
        # Before-snapshot: file_path -> set of (name, label_value)
        self._file_snapshot: dict[str, set[tuple[str, str]]] = {}
        self._listeners: list[Callable[[ChangeEvent], None]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def snapshot_file(self, file_path: str) -> None:
        """Record the current set of symbols for file_path.

        Must be called BEFORE the graph is modified (nodes removed / re-added).
        """
        nodes: set[tuple[str, str]] = set()
        for node in self._graph.get_nodes_by_file(file_path):
            if node.label not in _SKIP_LABELS:
                nodes.add((node.properties.name, node.label.value))
        self._file_snapshot[file_path] = nodes

    def record_change(self, file_path: str, change_type: str) -> ChangeEvent:
        """Compare current graph state with snapshot and emit a ChangeEvent.

        Consumes and removes the snapshot for file_path.
        """
        before: set[tuple[str, str]] = self._file_snapshot.pop(file_path, set())

        after: set[tuple[str, str]] = set()
        if change_type != "deleted":
            for node in self._graph.get_nodes_by_file(file_path):
                if node.label not in _SKIP_LABELS:
                    after.add((node.properties.name, node.label.value))

        added: set[tuple[str, str]] = after - before
        removed: set[tuple[str, str]] = before - after

        # Modified = names present in both snapshots (surviving across modify)
        modified: set[tuple[str, str]] = set()
        if change_type == "modified":
            before_names = {n for n, _ in before}
            common_names = {n for n, _ in after} & before_names
            modified = {(n, l) for n, l in after if n in common_names}

        # Compute blast-radius impact for all changed nodes
        risk, affected_count, affected_groups = self._compute_impact(
            file_path, added | modified | removed
        )

        event = ChangeEvent(
            timestamp=time.time(),
            file_path=file_path,
            change_type=change_type,
            nodes_added=tuple(sorted(n for n, _ in added)),
            nodes_modified=tuple(sorted(n for n, _ in modified)),
            nodes_removed=tuple(sorted(n for n, _ in removed)),
            risk=risk,
            affected_count=affected_count,
            affected_groups=tuple(sorted(affected_groups)),
        )
        self._events.append(event)
        self._notify(event)
        return event

    def on_change(self, callback: Callable[[ChangeEvent], None]) -> None:
        """Register a listener that is called with each new ChangeEvent."""
        self._listeners.append(callback)

    def get_events(self, limit: int = 50) -> list[ChangeEvent]:
        """Return recent events, newest first, up to limit."""
        events = list(self._events)
        events.reverse()
        return events[:limit]

    def session_summary(self) -> dict[str, Any]:
        """Aggregate summary of all changes tracked since this ChangeTracker was created."""
        events = list(self._events)
        files: set[str] = set()
        total_added = 0
        total_modified = 0
        total_removed = 0
        high_risk = 0
        groups_affected: set[str] = set()

        for e in events:
            files.add(e.file_path)
            total_added += len(e.nodes_added)
            total_modified += len(e.nodes_modified)
            total_removed += len(e.nodes_removed)
            if e.risk in ("HIGH", "CRITICAL"):
                high_risk += 1
            groups_affected.update(e.affected_groups)

        return {
            "session_start": self._session_start,
            "event_count": len(events),
            "files_changed": len(files),
            "nodes_added": total_added,
            "nodes_modified": total_modified,
            "nodes_removed": total_removed,
            "high_risk_changes": high_risk,
            "groups_affected": sorted(groups_affected),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_impact(
        self,
        file_path: str,
        changed_symbols: set[tuple[str, str]],
    ) -> tuple[str, int, set[str]]:
        """Run blast-radius analysis for all changed node names.

        Returns (risk, max_affected_count, affected_groups).
        """
        if not changed_symbols:
            return "LOW", 0, set()

        from vector_graph.analysis.impact import analyze_impact

        changed_names = {n for n, _ in changed_symbols}
        risk = "LOW"
        affected_count = 0
        affected_groups: set[str] = set()

        _RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

        for node in self._graph.iter_nodes():
            if (
                node.properties.name in changed_names
                and node.properties.file_path == file_path
            ):
                result = analyze_impact(
                    self._graph, node.id, direction="upstream", max_depth=2
                )
                affected_count = max(affected_count, result.impacted_count)
                if _RISK_ORDER.get(result.risk, 0) > _RISK_ORDER.get(risk, 0):
                    risk = result.risk
                for entry in result.entries:
                    parts = entry.file_path.replace("\\", "/").split("/") if entry.file_path else []
                    if len(parts) >= 2:
                        affected_groups.add("/".join(parts[-2:]))

        return risk, affected_count, affected_groups

    def _notify(self, event: ChangeEvent) -> None:
        """Call all registered listeners, swallowing any exceptions."""
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                pass
