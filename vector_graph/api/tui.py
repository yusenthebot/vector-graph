"""Terminal UI dashboard for live change monitoring.

Uses 'rich' for formatted output. Falls back to plain print if rich is not installed.
"""

from __future__ import annotations

import sys
import time
from typing import Any

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text

    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False


# Risk level display styles (used with rich; also used as labels in plain mode)
_RISK_STYLES: dict[str, str] = {
    "CRITICAL": "bold red",
    "HIGH": "bold yellow",
    "MEDIUM": "yellow",
    "LOW": "green",
}

# Change-type prefix characters
_TYPE_PREFIX: dict[str, str] = {
    "created": "+",
    "modified": "~",
    "deleted": "-",
}


# ---------------------------------------------------------------------------
# Public formatting helpers (pure functions — no I/O)
# ---------------------------------------------------------------------------

def format_change_event(event: Any) -> str:
    """Format a ChangeEvent as a human-readable single-line string.

    Format::

        [HH:MM:SS] ~ myfile.py (+N new ~M mod -P del) [RISK] → K affected

    Parameters
    ----------
    event:
        A ``ChangeEvent`` instance (from ``vector_graph.watch.change_tracker``).

    Returns
    -------
    str
        Formatted, human-readable description of the event.
    """
    ts = time.strftime("%H:%M:%S", time.localtime(event.timestamp))
    file_name = event.file_path.split("/")[-1] if event.file_path else "unknown"

    prefix = _TYPE_PREFIX.get(event.change_type, "?")
    parts = [f"[{ts}]", f"{prefix} {file_name}"]

    node_parts: list[str] = []
    if event.nodes_added:
        node_parts.append(f"+{len(event.nodes_added)} new")
    if event.nodes_modified:
        node_parts.append(f"~{len(event.nodes_modified)} mod")
    if event.nodes_removed:
        node_parts.append(f"-{len(event.nodes_removed)} del")
    if node_parts:
        parts.append(f"({', '.join(node_parts)})")

    parts.append(f"[{event.risk}]")

    if event.affected_count > 0:
        parts.append(f"→ {event.affected_count} affected")

    return " ".join(parts)


def format_session_summary(summary: dict[str, Any]) -> str:
    """Format a session summary dict as a multi-line human-readable string.

    Parameters
    ----------
    summary:
        Dict as returned by ``ChangeTracker.session_summary()``.

    Returns
    -------
    str
        Multi-line summary suitable for printing to stdout.
    """
    lines = [
        "── Session Summary ──",
        f"Changes:  {summary.get('event_count', 0)}",
        f"Files:    {summary.get('files_changed', 0)}",
        (
            f"Nodes:    "
            f"+{summary.get('nodes_added', 0)} added  "
            f"~{summary.get('nodes_modified', 0)} modified  "
            f"-{summary.get('nodes_removed', 0)} removed"
        ),
        f"High risk: {summary.get('high_risk_changes', 0)}",
    ]
    groups = summary.get("groups_affected", [])
    if groups:
        lines.append(f"Groups:   {', '.join(groups)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# TUI runners
# ---------------------------------------------------------------------------

def run_tui(change_tracker: Any, graph_result: Any | None = None) -> None:
    """Run the TUI dashboard. Blocks until Ctrl+C.

    Parameters
    ----------
    change_tracker:
        A ``ChangeTracker`` instance whose ``on_change`` will drive updates.
    graph_result:
        Optional ``AnalysisResult`` used to display graph stats in the header.
        Accepts any object with ``node_count``, ``edge_count``, ``file_count`` attrs,
        or ``None``.
    """
    if _HAS_RICH:
        _run_rich_tui(change_tracker, graph_result)
    else:
        _run_plain_tui(change_tracker)


def _run_plain_tui(change_tracker: Any) -> None:
    """Fallback plain-text TUI (no rich dependency)."""
    print("vector-graph watch  (install 'rich' for a richer display)")
    print("Watching for changes... (Ctrl+C to stop)\n")

    change_tracker.on_change(lambda e: print(format_change_event(e)))

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print()
        print(format_session_summary(change_tracker.session_summary()))


def _run_rich_tui(change_tracker: Any, graph_result: Any | None) -> None:
    """Rich-powered TUI with live updating display."""
    console = Console()

    # Build header subtitle
    if graph_result is not None:
        subtitle = (
            f"[dim]{graph_result.node_count} nodes · "
            f"{graph_result.edge_count} edges · "
            f"{graph_result.file_count} files[/]"
        )
    else:
        subtitle = "[dim]ready[/]"

    console.print(
        Panel(
            f"[bold cyan]vector-graph[/] Live Radar\n{subtitle}",
            title="[bold]TUI Dashboard[/]",
            border_style="cyan",
        )
    )
    console.print("[dim]Watching for changes... (Ctrl+C to stop)[/]\n")

    def _on_change(event: Any) -> None:
        text = Text()
        ts = time.strftime("%H:%M:%S", time.localtime(event.timestamp))
        text.append(f"[{ts}] ", style="dim")

        type_style = {"created": "green", "modified": "yellow", "deleted": "red"}.get(
            event.change_type, ""
        )
        prefix = _TYPE_PREFIX.get(event.change_type, "?")
        file_name = event.file_path.split("/")[-1] if event.file_path else "unknown"
        text.append(f"{prefix} {file_name} ", style=type_style)

        if event.nodes_added:
            text.append(f"+{len(event.nodes_added)} ", style="green")
        if event.nodes_modified:
            text.append(f"~{len(event.nodes_modified)} ", style="yellow")
        if event.nodes_removed:
            text.append(f"-{len(event.nodes_removed)} ", style="red")

        risk_style = _RISK_STYLES.get(event.risk, "")
        text.append(f"[{event.risk}] ", style=risk_style)

        if event.affected_count > 0:
            text.append(f"→ {event.affected_count} affected", style="dim")

        console.print(text)

    change_tracker.on_change(_on_change)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        console.print()
        summary = change_tracker.session_summary()

        table = Table(title="Session Summary", border_style="cyan")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")
        table.add_row("Changes", str(summary.get("event_count", 0)))
        table.add_row("Files", str(summary.get("files_changed", 0)))
        table.add_row("Nodes added", str(summary.get("nodes_added", 0)))
        table.add_row("Nodes modified", str(summary.get("nodes_modified", 0)))
        table.add_row("Nodes removed", str(summary.get("nodes_removed", 0)))
        table.add_row("High risk", str(summary.get("high_risk_changes", 0)))
        groups = summary.get("groups_affected", [])
        if groups:
            table.add_row("Groups affected", ", ".join(groups))

        console.print(table)
