"""Web server for vector-graph visualization. Serves interactive graph at localhost."""

from __future__ import annotations

import http.server
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from vector_graph._types import EdgeType, NodeLabel
from vector_graph.graph.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

_LABEL_COLOR: dict[str, str] = {
    "File": "#585b70", "Function": "#89b4fa", "Class": "#cba6f7",
    "Method": "#94e2d5", "Variable": "#a6adc8", "Module": "#fab387",
    "ROS2Node": "#f38ba8", "Topic": "#f9e2af", "Service": "#a6e3a1",
    "Action": "#f5c2e7", "Parameter": "#89dceb", "Community": "#b4befe",
}

_EDGE_COLOR: dict[str, str] = {
    "CALLS": "#89b4fa", "IMPORTS": "#fab387", "HAS_METHOD": "#94e2d5",
    "EXTENDS": "#cba6f7", "PUBLISHES_TO": "#a6e3a1",
    "SUBSCRIBES_TO": "#f9e2af", "PROVIDES_SERVICE": "#f38ba8",
}


def _build_pyvis_html(graph: KnowledgeGraph, max_nodes: int = 400) -> str:
    """Build interactive HTML using pyvis."""
    from pyvis.network import Network

    net = Network(
        height="100vh",
        width="100%",
        bgcolor="#1e1e2e",
        font_color="#cdd6f4",
        directed=True,
        select_menu=False,
        filter_menu=False,
    )

    net.set_options(json.dumps({
        "physics": {
            "forceAtlas2Based": {
                "gravitationalConstant": -60,
                "centralGravity": 0.008,
                "springLength": 150,
                "springConstant": 0.06,
                "damping": 0.5,
            },
            "solver": "forceAtlas2Based",
            "stabilization": {"iterations": 80, "updateInterval": 25},
        },
        "nodes": {
            "font": {"size": 11, "face": "monospace", "color": "#cdd6f4"},
            "borderWidth": 2,
            "borderWidthSelected": 3,
        },
        "edges": {
            "arrows": {"to": {"enabled": True, "scaleFactor": 0.4}},
            "color": {"inherit": False},
            "smooth": {"type": "continuous", "roundness": 0.2},
            "font": {"size": 8, "color": "#585b70", "align": "middle"},
            "width": 0.5,
        },
        "interaction": {
            "hover": True,
            "tooltipDelay": 100,
            "navigationButtons": True,
            "keyboard": {"enabled": True},
            "multiselect": True,
        },
    }))

    skip_labels = {NodeLabel.FILE, NodeLabel.FOLDER}
    added: set[str] = set()
    count = 0

    for node in graph.iter_nodes():
        if node.label in skip_labels:
            continue
        if count >= max_nodes:
            break

        color = _LABEL_COLOR.get(node.label.value, "#cdd6f4")
        size = {"Class": 22, "ROS2Node": 24, "Function": 14, "Method": 10, "Topic": 16, "Service": 16}.get(node.label.value, 12)
        shape = {"Class": "diamond", "ROS2Node": "star", "Topic": "triangle", "Service": "square"}.get(node.label.value, "dot")

        title = f"<b>{node.label.value}: {node.properties.name}</b>"
        if node.properties.file_path:
            title += f"<br>{os.path.basename(node.properties.file_path)}"
        if node.properties.start_line:
            title += f":{node.properties.start_line}"
        if node.properties.return_type:
            title += f"<br>returns: {node.properties.return_type}"
        if node.properties.parameters:
            title += f"<br>params: ({', '.join(node.properties.parameters)})"
        if node.properties.bases:
            title += f"<br>bases: {', '.join(node.properties.bases)}"

        net.add_node(
            node.id,
            label=node.properties.name,
            color=color,
            size=size,
            shape=shape,
            title=title,
            group=node.label.value,
        )
        added.add(node.id)
        count += 1

    for edge in graph.iter_edges():
        if edge.source_id not in added or edge.target_id not in added:
            continue
        color = _EDGE_COLOR.get(edge.edge_type.value, "#45475a")
        net.add_edge(
            edge.source_id,
            edge.target_id,
            color=color,
            title=f"{edge.edge_type.value} ({edge.confidence:.2f})",
            width=max(0.3, edge.confidence),
        )

    # Generate HTML string
    tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
    tmp.close()
    net.save_graph(tmp.name)
    html = Path(tmp.name).read_text()
    os.unlink(tmp.name)

    # Inline the lib/bindings/utils.js that pyvis references locally
    utils_js = _find_pyvis_utils_js()
    if utils_js:
        html = html.replace(
            '<script src="lib/bindings/utils.js"></script>',
            f"<script>{utils_js}</script>",
        )

    # Inject title
    html = html.replace("<head>", "<head><title>vector-graph</title>")
    return html


def _find_pyvis_utils_js() -> str | None:
    """Find and read pyvis's lib/bindings/utils.js from the installed package."""
    try:
        import pyvis
        pkg_dir = Path(pyvis.__file__).parent
        utils_path = pkg_dir / "templates" / "lib" / "bindings" / "utils.js"
        if utils_path.exists():
            return utils_path.read_text()
    except Exception:
        pass
    return None


def serve(
    graph: KnowledgeGraph,
    host: str = "127.0.0.1",
    port: int = 5555,
    max_nodes: int = 400,
) -> None:
    """Start a local HTTP server serving the interactive graph visualization."""
    print("Building visualization...")
    html_bytes = _build_pyvis_html(graph, max_nodes=max_nodes).encode("utf-8")
    print(f"HTML ready ({len(html_bytes) // 1024} KB)")

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/" or self.path == "/index.html":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self.end_headers()
                self.wfile.write(html_bytes)
            else:
                self.send_error(404)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = http.server.HTTPServer((host, port), Handler)
    print(f"vector-graph running at http://{host}:{port}")
    print("Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        print("\nStopped.")
