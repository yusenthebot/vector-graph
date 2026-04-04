"""Export knowledge graph to JSON and DOT formats.

Both functions are pure — no side effects, no file I/O. They return strings.
"""

from __future__ import annotations

import json

from vector_graph.graph.protocols import GraphProtocol


def export_json(graph: GraphProtocol) -> str:
    """Export full graph as JSON.

    Format::

        {
            "nodes": [{"id": "...", "label": "...", "properties": {...}}, ...],
            "edges": [
                {
                    "id": "...",
                    "source_id": "...",
                    "target_id": "...",
                    "edge_type": "...",
                    "confidence": 0.9
                },
                ...
            ]
        }

    Parameters
    ----------
    graph:
        Any object that satisfies GraphProtocol (e.g. KnowledgeGraph).

    Returns
    -------
    str
        Pretty-printed JSON string.
    """
    nodes = [node.to_dict() for node in graph.iter_nodes()]
    edges = [edge.to_dict() for edge in graph.iter_edges()]
    return json.dumps({"nodes": nodes, "edges": edges}, indent=2)


def export_dot(graph: GraphProtocol) -> str:
    """Export graph as DOT (Graphviz) format.

    Format::

        digraph G {
          "n1" [label="foo (Function)"];
          "n2" [label="bar (Function)"];
          "n1" -> "n2" [label="CALLS"];
        }

    Parameters
    ----------
    graph:
        Any object that satisfies GraphProtocol (e.g. KnowledgeGraph).

    Returns
    -------
    str
        DOT-format string suitable for Graphviz.
    """
    lines = ["digraph G {"]

    for node in graph.iter_nodes():
        label = f"{node.properties.name} ({node.label.value})"
        # Escape double-quotes inside the label string
        label = label.replace('"', '\\"')
        lines.append(f'  "{node.id}" [label="{label}"];')

    for edge in graph.iter_edges():
        edge_label = edge.edge_type.value
        lines.append(f'  "{edge.source_id}" -> "{edge.target_id}" [label="{edge_label}"];')

    lines.append("}")
    return "\n".join(lines)
