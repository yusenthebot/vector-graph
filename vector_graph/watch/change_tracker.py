"""Track file changes and compute diffs against the knowledge graph.

Records before/after snapshots around graph mutations to produce structured
ChangeEvent objects that describe what nodes were added, modified, or removed,
along with blast-radius impact metadata and unified source diffs.

v0.4.1: Node ID tracking + AST signature comparison for real modification detection.
v0.4.2: Source code snapshots + unified diffs per changed symbol.
"""

from __future__ import annotations

import difflib
import json
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from vector_graph._types import GraphNode, NodeLabel
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
    node_ids_added: tuple[str, ...] = ()
    node_ids_modified: tuple[str, ...] = ()
    node_ids_removed: tuple[str, ...] = ()
    risk: str = "LOW"
    affected_count: int = 0
    affected_groups: tuple[str, ...] = ()
    # Unified diffs (or full source) per changed symbol name.
    # Each entry: (symbol_name, diff_string)
    diffs: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict representation."""
        return {
            "timestamp": self.timestamp,
            "file": self.file_path,
            "type": self.change_type,
            "nodes_added": list(self.nodes_added),
            "nodes_modified": list(self.nodes_modified),
            "nodes_removed": list(self.nodes_removed),
            "node_ids_added": list(self.node_ids_added),
            "node_ids_modified": list(self.node_ids_modified),
            "node_ids_removed": list(self.node_ids_removed),
            "impact": {
                "risk": self.risk,
                "affected_count": self.affected_count,
                "affected_groups": list(self.affected_groups),
            },
            "diffs": {name: diff for name, diff in self.diffs},
        }


# Labels that represent structural meta-nodes, not code symbols
_SKIP_LABELS = frozenset({NodeLabel.FILE, NodeLabel.FOLDER})


def _read_source_lines(file_path: str, start: int, end: int) -> str:
    """Read source lines [start, end] (1-based, inclusive) from file.

    Returns empty string on any I/O error or if line numbers are invalid.
    """
    try:
        lines = Path(file_path).read_text(encoding="utf-8", errors="replace").splitlines()
        s = max(0, start - 1)
        e = min(len(lines), end)
        return "\n".join(lines[s:e])
    except OSError:
        return ""


def _node_signature(node: GraphNode) -> str:
    """Compute a content-based signature for detecting real modifications.

    Compares: parameter count, parameter names, return type, decorators,
    and line span (end - start). If any of these change, the function
    is considered "modified".
    """
    p = node.properties
    parts = [
        str(p.parameter_count or 0),
        ",".join(p.parameters),
        str(p.return_type or ""),
        ",".join(p.decorators),
        str((p.end_line or 0) - (p.start_line or 0)),
    ]
    return "|".join(parts)


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
        # Before-snapshot: file_path -> {(name, label_value): (node_id, sig_hash, source_lines)}
        self._file_snapshot: dict[str, dict[tuple[str, str], tuple[str, str, str]]] = {}
        self._listeners: list[Callable[[ChangeEvent], None]] = []
        # Persistent file content cache — stores the LAST KNOWN content per file.
        # Updated AFTER each change cycle so snapshots always use the previous version.
        self._file_content_cache: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def snapshot_file(self, file_path: str) -> None:
        """Record the current set of symbols for file_path.

        Must be called BEFORE the graph is modified (nodes removed / re-added).
        Captures node IDs, AST signatures, and source code for diff computation.

        Source uses the persistent content cache (previous file version) so that
        diffs compare OLD content vs NEW content, not new vs new.
        """
        snapshot: dict[tuple[str, str], tuple[str, str, str]] = {}

        # Use cached content (the PREVIOUS version of the file) for old source.
        # If no cache exists (first time), read from disk — this is fine for the
        # initial snapshot since there's no "before" to compare against anyway.
        cached_lines = self._file_content_cache.get(file_path)
        if cached_lines is None:
            try:
                cached_lines = Path(file_path).read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                self._file_content_cache[file_path] = cached_lines
            except OSError:
                cached_lines = []

        for node in self._graph.get_nodes_by_file(file_path):
            if node.label not in _SKIP_LABELS:
                key = (node.properties.name, node.label.value)
                sig = _node_signature(node)

                source = ""
                start = node.properties.start_line
                end = node.properties.end_line
                if start and end and cached_lines:
                    s = max(0, start - 1)
                    e = min(len(cached_lines), end)
                    source = "\n".join(cached_lines[s:e])

                snapshot[key] = (node.id, sig, source)
        self._file_snapshot[file_path] = snapshot

    def record_change(self, file_path: str, change_type: str) -> ChangeEvent:
        """Compare current graph state with snapshot and emit a ChangeEvent.

        Consumes and removes the snapshot for file_path.
        Uses AST signature comparison to detect real modifications
        (not just surviving names). Computes unified diffs for changed symbols.
        """
        before = self._file_snapshot.pop(file_path, {})

        after: dict[tuple[str, str], tuple[str, str, str]] = {}
        if change_type != "deleted":
            # Read current source per node; cache file content for this pass
            _file_content_cache: dict[str, list[str]] = {}
            for node in self._graph.get_nodes_by_file(file_path):
                if node.label not in _SKIP_LABELS:
                    key = (node.properties.name, node.label.value)
                    sig = _node_signature(node)

                    source = ""
                    node_fp = node.properties.file_path or ""
                    start = node.properties.start_line
                    end = node.properties.end_line
                    if node_fp and start and end:
                        if node_fp not in _file_content_cache:
                            try:
                                _file_content_cache[node_fp] = Path(node_fp).read_text(
                                    encoding="utf-8", errors="replace"
                                ).splitlines()
                            except OSError:
                                _file_content_cache[node_fp] = []
                        lines = _file_content_cache[node_fp]
                        s = max(0, start - 1)
                        e = min(len(lines), end)
                        source = "\n".join(lines[s:e])

                    after[key] = (node.id, sig, source)

        before_keys = set(before.keys())
        after_keys = set(after.keys())

        added_keys = after_keys - before_keys
        removed_keys = before_keys - after_keys
        common_keys = before_keys & after_keys

        # Modified = common keys where AST signature actually changed
        modified_keys: set[tuple[str, str]] = set()
        if change_type == "modified":
            for key in common_keys:
                _, before_sig, _ = before[key]
                _, after_sig, _ = after[key]
                if before_sig != after_sig:
                    modified_keys.add(key)

        # Build name lists (backward compat) and node ID lists
        nodes_added = tuple(sorted(name for name, _ in added_keys))
        nodes_modified = tuple(sorted(name for name, _ in modified_keys))
        nodes_removed = tuple(sorted(name for name, _ in removed_keys))

        node_ids_added = tuple(sorted(after[k][0] for k in added_keys))
        node_ids_modified = tuple(sorted(after[k][0] for k in modified_keys))
        node_ids_removed = tuple(sorted(before[k][0] for k in removed_keys))

        # Compute unified diffs for changed symbols
        diffs_list: list[tuple[str, str]] = []

        for key in sorted(modified_keys):
            name, _ = key
            _, _, old_source = before[key]
            _, _, new_source = after[key]
            if old_source and new_source:
                diff_lines = list(difflib.unified_diff(
                    old_source.splitlines(keepends=True),
                    new_source.splitlines(keepends=True),
                    fromfile="before",
                    tofile="after",
                    lineterm="",
                ))
                if diff_lines:
                    diffs_list.append((name, "\n".join(diff_lines)))
            elif new_source:
                diffs_list.append((name, new_source))
            elif old_source:
                diffs_list.append((name, old_source))

        for key in sorted(added_keys):
            name, _ = key
            _, _, new_source = after[key]
            if new_source:
                diffs_list.append((name, new_source))

        for key in sorted(removed_keys):
            name, _ = key
            _, _, old_source = before[key]
            if old_source:
                diffs_list.append((name, old_source))

        # Compute blast-radius impact for added + modified nodes
        changed_ids = {after[k][0] for k in added_keys | modified_keys}
        risk, affected_count, affected_groups = self._compute_impact(
            file_path, changed_ids
        )

        event = ChangeEvent(
            timestamp=time.time(),
            file_path=file_path,
            change_type=change_type,
            nodes_added=nodes_added,
            nodes_modified=nodes_modified,
            nodes_removed=nodes_removed,
            node_ids_added=node_ids_added,
            node_ids_modified=node_ids_modified,
            node_ids_removed=node_ids_removed,
            risk=risk,
            affected_count=affected_count,
            affected_groups=tuple(sorted(affected_groups)),
            diffs=tuple(diffs_list),
        )
        self._events.append(event)
        self._notify(event)

        # Update file content cache with the CURRENT (new) version.
        # Next snapshot_file() call will use this as the "before" content.
        if change_type == "deleted":
            self._file_content_cache.pop(file_path, None)
        else:
            try:
                self._file_content_cache[file_path] = Path(file_path).read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
            except OSError:
                self._file_content_cache.pop(file_path, None)

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
        changed_node_ids: set[str],
    ) -> tuple[str, int, set[str]]:
        """Run blast-radius analysis for changed nodes by ID.

        Returns (risk, max_affected_count, affected_groups).
        """
        if not changed_node_ids:
            return "LOW", 0, set()

        from vector_graph.analysis.impact import analyze_impact

        risk = "LOW"
        affected_count = 0
        affected_groups: set[str] = set()

        _RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

        for node_id in changed_node_ids:
            node = self._graph.get_node(node_id)
            if node is None:
                continue
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
