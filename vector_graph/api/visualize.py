"""Visualization for vector-graph: Rich CLI tables + interactive HTML graph."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from vector_graph._types import (
    AnalysisResult,
    EdgeType,
    ImpactResult,
    NodeLabel,
)
from vector_graph.graph.knowledge_graph import KnowledgeGraph


# ---------------------------------------------------------------------------
# Color mappings
# ---------------------------------------------------------------------------

_LABEL_COLOR: dict[str, str] = {
    "File": "#585b70",
    "Function": "#89b4fa",
    "Class": "#cba6f7",
    "Method": "#94e2d5",
    "Variable": "#a6adc8",
    "Module": "#fab387",
    "ROS2Node": "#f38ba8",
    "Topic": "#f9e2af",
    "Service": "#a6e3a1",
    "Action": "#f5c2e7",
    "Parameter": "#89dceb",
    "Community": "#b4befe",
    "Process": "#f2cdcd",
}

_EDGE_COLOR: dict[str, str] = {
    "CALLS": "#89b4fa",
    "IMPORTS": "#fab387",
    "HAS_METHOD": "#94e2d5",
    "EXTENDS": "#cba6f7",
    "PUBLISHES_TO": "#a6e3a1",
    "SUBSCRIBES_TO": "#f9e2af",
    "PROVIDES_SERVICE": "#f38ba8",
    "USES_PARAMETER": "#89dceb",
}


# ---------------------------------------------------------------------------
# Rich CLI output
# ---------------------------------------------------------------------------

def print_summary(result: AnalysisResult) -> None:
    """Print analysis summary as a Rich table."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel

    console = Console()
    console.print(Panel(
        f"[bold #89b4fa]{result.root}[/]",
        title="vector-graph analysis",
        border_style="#45475a",
    ))

    table = Table(
        border_style="#45475a",
        header_style="bold #89b4fa",
        row_styles=["", "on #181825"],
    )
    table.add_column("Metric", min_width=16)
    table.add_column("Count", justify="right", min_width=8)

    table.add_row("Files", str(result.file_count))
    table.add_row("Functions", str(result.function_count))
    table.add_row("Classes", str(result.class_count))
    table.add_row("Imports", str(result.import_count))
    table.add_row("Call edges", str(result.call_count))
    table.add_row("Total nodes", str(result.node_count))
    table.add_row("Total edges", str(result.edge_count))
    table.add_row("Communities", str(result.community_count))
    table.add_row("Exec flows", str(result.process_count))
    console.print(table)


def print_impact(impact: ImpactResult) -> None:
    """Print impact analysis as a Rich table."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text

    console = Console()
    risk_color = {"LOW": "green", "MEDIUM": "yellow", "HIGH": "red", "CRITICAL": "bold red"}.get(impact.risk, "white")

    console.print(Panel(
        f"[bold]{impact.target_name}[/] ({impact.target_file.split('/')[-1]})\n"
        f"Direction: {impact.direction} | Risk: [{risk_color}]{impact.risk}[/] | Affected: {impact.impacted_count}",
        title="[bold #89b4fa]Impact Analysis[/]",
        border_style=risk_color.replace("bold ", ""),
    ))

    if not impact.entries:
        console.print("[dim]No affected symbols.[/]")
        return

    table = Table(
        border_style="#45475a",
        header_style="bold #89b4fa",
        row_styles=["", "on #181825"],
    )
    table.add_column("Depth", justify="center", width=6)
    table.add_column("Type", width=12)
    table.add_column("Symbol", min_width=24)
    table.add_column("File", min_width=20)

    for entry in impact.entries[:30]:
        depth_color = {1: "red", 2: "yellow", 3: "dim"}.get(entry.depth, "dim")
        fname = os.path.basename(entry.file_path)
        table.add_row(
            Text(str(entry.depth), style=depth_color),
            entry.edge_type,
            entry.name,
            fname,
        )

    console.print(table)
    if impact.impacted_count > 30:
        console.print(f"[dim]... and {impact.impacted_count - 30} more[/]")


# ---------------------------------------------------------------------------
# Interactive HTML graph (pyvis)
# ---------------------------------------------------------------------------

def export_html(
    graph: KnowledgeGraph,
    output: str | Path = "graph.html",
    *,
    max_nodes: int = 500,
    include_files: bool = False,
    edge_types: set[EdgeType] | None = None,
    title: str = "vector-graph",
) -> Path:
    """Export the knowledge graph as an interactive HTML visualization.

    Uses pyvis (vis.js wrapper) for a force-directed graph in the browser.
    """
    from pyvis.network import Network

    net = Network(
        height="100vh",
        width="100%",
        bgcolor="#1e1e2e",
        font_color="#cdd6f4",
        directed=True,
        notebook=False,
        select_menu=True,
        filter_menu=True,
    )
    net.set_options("""
    {
        "physics": {
            "forceAtlas2Based": {
                "gravitationalConstant": -80,
                "centralGravity": 0.01,
                "springLength": 120,
                "springConstant": 0.08,
                "damping": 0.4
            },
            "solver": "forceAtlas2Based",
            "stabilization": {"iterations": 100}
        },
        "nodes": {
            "font": {"size": 12, "face": "monospace"},
            "borderWidth": 2
        },
        "edges": {
            "arrows": {"to": {"enabled": true, "scaleFactor": 0.5}},
            "smooth": {"type": "continuous"},
            "font": {"size": 8, "align": "middle"}
        },
        "interaction": {
            "hover": true,
            "tooltipDelay": 100,
            "navigationButtons": true,
            "keyboard": true
        }
    }
    """)

    # Collect nodes (skip Files unless requested)
    skip_labels = set()
    if not include_files:
        skip_labels.add(NodeLabel.FILE)

    added_nodes: set[str] = set()
    count = 0
    for node in graph.iter_nodes():
        if node.label in skip_labels:
            continue
        if count >= max_nodes:
            break

        color = _LABEL_COLOR.get(node.label.value, "#cdd6f4")
        size = {"Class": 20, "ROS2Node": 22, "Function": 12, "Method": 10}.get(node.label.value, 14)
        shape = {"Class": "diamond", "ROS2Node": "star", "Topic": "triangle", "Service": "square"}.get(node.label.value, "dot")

        tooltip = f"{node.label.value}: {node.properties.name}"
        if node.properties.file_path:
            tooltip += f"\n{os.path.basename(node.properties.file_path)}"
        if node.properties.start_line:
            tooltip += f":{node.properties.start_line}"

        net.add_node(
            node.id,
            label=node.properties.name,
            color=color,
            size=size,
            shape=shape,
            title=tooltip,
            group=node.label.value,
        )
        added_nodes.add(node.id)
        count += 1

    # Add edges (only between added nodes)
    for edge in graph.iter_edges():
        if edge.source_id not in added_nodes or edge.target_id not in added_nodes:
            continue
        if edge_types and edge.edge_type not in edge_types:
            continue

        color = _EDGE_COLOR.get(edge.edge_type.value, "#585b70")
        net.add_edge(
            edge.source_id,
            edge.target_id,
            color=color,
            title=f"{edge.edge_type.value} ({edge.confidence:.2f})",
            width=max(1, edge.confidence * 2),
        )

    output_path = Path(output)
    net.save_graph(str(output_path))

    # Inject title into HTML
    html = output_path.read_text()
    html = html.replace("<head>", f"<head><title>{title}</title>")
    output_path.write_text(html)

    return output_path
