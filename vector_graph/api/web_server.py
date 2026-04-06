"""Web server for vector-graph 3D visualization."""

from __future__ import annotations

import http.server
import json
import logging
import os
import urllib.parse
from pathlib import Path
from typing import Any

from vector_graph._types import EdgeType, ImpactResult, NodeLabel
from vector_graph.graph.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data preparation (testable, no HTTP dependency)
# ---------------------------------------------------------------------------

_LABEL_PRIORITY: dict[NodeLabel, int] = {
    NodeLabel.ROS2_NODE: 0, NodeLabel.TOPIC: 1, NodeLabel.SERVICE: 1,
    NodeLabel.ACTION: 1, NodeLabel.PARAMETER: 2,
    NodeLabel.CLASS: 3, NodeLabel.FUNCTION: 4, NodeLabel.FILE: 5,
    NodeLabel.MODULE: 6, NodeLabel.METHOD: 7,
    NodeLabel.VARIABLE: 8, NodeLabel.DECORATOR: 8, NodeLabel.PROPERTY: 8,
    NodeLabel.FOLDER: 99,
}

_MODE_LABELS: dict[str, set[NodeLabel] | None] = {
    "architecture": {NodeLabel.FILE},
    "logic": {NodeLabel.FILE, NodeLabel.FUNCTION, NodeLabel.CLASS, NodeLabel.METHOD},
    "deep": None,  # all labels
}
_MODE_EDGES: dict[str, set[EdgeType] | None] = {
    "architecture": {EdgeType.IMPORTS},
    "logic": {EdgeType.CALLS, EdgeType.IMPORTS, EdgeType.EXTENDS,
              EdgeType.HAS_METHOD, EdgeType.CONTAINS, EdgeType.DECORATES},
    "deep": None,  # all edge types
}
_MODE_MAX_NODES: dict[str, int] = {
    "architecture": 200,
    "logic": 600,
    "deep": 2000,
}


def _node_group(file_path: str, root_path: str) -> str:
    """Derive group name (relative directory) for nebula clustering."""
    if not file_path or not root_path:
        return "other"
    try:
        rel = os.path.relpath(file_path, root_path)
        parts = rel.replace("\\", "/").split("/")
        # Use up to 2 levels of directory: "vector_graph/analysis"
        dir_parts = parts[:-1]  # drop filename
        if not dir_parts:
            return "root"
        return "/".join(dir_parts[:2])
    except ValueError:
        return "other"


def build_graph_data(
    graph: KnowledgeGraph,
    max_nodes: int | None = None,
    root_path: str = "",
    health_map: dict[str, Any] | None = None,
    mode: str = "logic",
) -> dict[str, Any]:
    """Convert KnowledgeGraph to JSON for 3d-force-graph.

    Prioritizes ROS2 > Class > Function > Method > File to ensure
    important nodes are included before the limit is hit.
    Each node includes a ``group`` field for nebula clustering.

    Parameters
    ----------
    mode:
        Visualization mode — one of ``"architecture"``, ``"logic"``, or
        ``"deep"``.  Controls which node labels and edge types are included
        and sets the default max_nodes cap.
    max_nodes:
        Hard cap on included nodes.  Defaults to ``_MODE_MAX_NODES[mode]``
        when *None*.
    """
    if mode not in _MODE_LABELS:
        mode = "logic"
    effective_max_nodes: int = max_nodes if max_nodes is not None else _MODE_MAX_NODES.get(mode, 600)

    allowed_labels: set[NodeLabel] | None = _MODE_LABELS[mode]
    allowed_edges: set[EdgeType] | None = _MODE_EDGES[mode]

    skip_labels = {NodeLabel.FOLDER}
    all_nodes = [
        n for n in graph.iter_nodes()
        if n.label not in skip_labels
        and (allowed_labels is None or n.label in allowed_labels)
    ]
    all_nodes.sort(key=lambda n: _LABEL_PRIORITY.get(n.label, 50))

    nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()

    for node in all_nodes:
        if len(nodes) >= effective_max_nodes:
            break
        group = _node_group(node.properties.file_path, root_path)
        entry: dict[str, Any] = {
            "id": node.id,
            "name": node.properties.name,
            "label": node.label.value,
            "group": group,
            "file": node.properties.file_path or "",
            "line": node.properties.start_line or 0,
            "endLine": node.properties.end_line or 0,
        }
        if node.properties.return_type:
            entry["returnType"] = node.properties.return_type
        if node.properties.parameters:
            entry["params"] = list(node.properties.parameters)
        if node.properties.bases:
            entry["bases"] = list(node.properties.bases)
        if node.properties.decorators:
            entry["decorators"] = list(node.properties.decorators)
        if node.properties.docstring:
            entry["doc"] = node.properties.docstring[:200]
        # Health data (optional, from complexity analysis)
        if health_map and node.id in health_map:
            h = health_map[node.id]
            entry["complexity"] = h.cyclomatic
            entry["healthRisk"] = h.risk
            entry["lineCount"] = h.line_count
        # Inline source snippet for functions/methods (compact)
        # Files and large classes use lazy /api/source fetch
        if (node.properties.file_path and node.properties.start_line
                and node.label in (NodeLabel.FUNCTION, NodeLabel.METHOD,
                                   NodeLabel.CLASS)):
            try:
                all_lines = Path(node.properties.file_path).read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                s = max(0, (node.properties.start_line or 1) - 1)
                e = min(len(all_lines), (node.properties.end_line or s + 30))
                snippet = "\n".join(all_lines[s:e])
                if len(snippet) > 2000:
                    snippet = snippet[:2000] + "\n# ... truncated"
                entry["source"] = snippet
            except OSError:
                pass
        nodes.append(entry)
        node_ids.add(node.id)

    # Connectivity for size-by-importance visualization (v0.8.0)
    for entry in nodes:
        nid = entry["id"]
        fan_in = sum(1 for e in graph.get_edges_to(nid) if e.source_id in node_ids)
        fan_out = sum(1 for e in graph.get_edges_from(nid) if e.target_id in node_ids)
        entry["fanIn"] = fan_in
        entry["fanOut"] = fan_out

    # Architecture mode: enrich FILE nodes with symbol counts from the full graph
    if mode == "architecture":
        file_function_counts: dict[str, int] = {}
        file_class_counts: dict[str, int] = {}
        for n in graph.iter_nodes():
            fp = n.properties.file_path or ""
            if not fp:
                continue
            if n.label == NodeLabel.FUNCTION:
                file_function_counts[fp] = file_function_counts.get(fp, 0) + 1
            elif n.label == NodeLabel.CLASS:
                file_class_counts[fp] = file_class_counts.get(fp, 0) + 1
        for entry in nodes:
            if entry["label"] == NodeLabel.FILE.value:
                fp = entry["file"]
                entry["function_count"] = file_function_counts.get(fp, 0)
                entry["class_count"] = file_class_counts.get(fp, 0)

    links: list[dict[str, Any]] = []
    for edge in graph.iter_edges():
        if edge.source_id in node_ids and edge.target_id in node_ids:
            if allowed_edges is not None and edge.edge_type not in allowed_edges:
                continue
            links.append({
                "source": edge.source_id,
                "target": edge.target_id,
                "type": edge.edge_type.value,
                "confidence": edge.confidence,
            })

    return {"nodes": nodes, "links": links}


def build_source_response(
    file_path: str,
    root_path: str,
    start: int | None = None,
    end: int | None = None,
    context_lines: int = 50,
) -> dict[str, Any]:
    """Read source file content with path traversal protection."""
    resolved = os.path.realpath(file_path)
    root_resolved = os.path.realpath(root_path)
    if not resolved.startswith(root_resolved):
        return {"error": "path outside project root", "content": ""}

    try:
        lines = Path(resolved).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {"error": "file not found", "content": ""}

    total = len(lines)
    if start is not None and end is not None:
        # Show context around the symbol
        s = max(0, start - 1 - context_lines)
        e = min(total, end + context_lines)
        content = "\n".join(lines[s:e])
        return {"content": content, "startLine": s + 1, "endLine": e, "total": total, "language": "python"}
    elif start is not None:
        s = max(0, start - 1 - context_lines)
        e = min(total, start + context_lines)
        content = "\n".join(lines[s:e])
        return {"content": content, "startLine": s + 1, "endLine": e, "total": total, "language": "python"}
    else:
        return {"content": "\n".join(lines), "startLine": 1, "endLine": total, "total": total, "language": "python"}


def build_context_response(graph: KnowledgeGraph, node_id: str) -> dict[str, Any]:
    """360-degree context for a node: details + inbound + outbound."""
    node = graph.get_node(node_id)
    if node is None:
        return {"error": "node not found"}

    inbound = []
    for edge in graph.get_edges_to(node_id):
        src = graph.get_node(edge.source_id)
        if src:
            inbound.append({
                "id": src.id, "name": src.properties.name, "label": src.label.value,
                "file": os.path.basename(src.properties.file_path),
                "edgeType": edge.edge_type.value, "confidence": edge.confidence,
            })

    outbound = []
    for edge in graph.get_edges_from(node_id):
        tgt = graph.get_node(edge.target_id)
        if tgt:
            outbound.append({
                "id": tgt.id, "name": tgt.properties.name, "label": tgt.label.value,
                "file": os.path.basename(tgt.properties.file_path),
                "edgeType": edge.edge_type.value, "confidence": edge.confidence,
            })

    return {
        "node": {
            "id": node.id, "name": node.properties.name, "label": node.label.value,
            "file": node.properties.file_path, "line": node.properties.start_line,
            "endLine": node.properties.end_line,
            "returnType": node.properties.return_type,
            "params": list(node.properties.parameters) if node.properties.parameters else [],
            "bases": list(node.properties.bases) if node.properties.bases else [],
            "decorators": list(node.properties.decorators) if node.properties.decorators else [],
            "doc": node.properties.docstring or "",
        },
        "inbound": inbound,
        "outbound": outbound,
    }


def build_file_tree(graph: KnowledgeGraph, root_path: str) -> dict[str, Any]:
    """Build VS Code-style file tree with symbols per file."""
    import os
    tree: dict[str, Any] = {"name": os.path.basename(root_path), "type": "dir", "children": {}}

    # Collect files and their symbols
    file_symbols: dict[str, list[dict[str, Any]]] = {}
    for node in graph.iter_nodes():
        if node.label.value == "File":
            rel = os.path.relpath(node.properties.file_path, root_path)
            file_symbols.setdefault(rel, [])
        elif node.properties.file_path:
            rel = os.path.relpath(node.properties.file_path, root_path)
            file_symbols.setdefault(rel, []).append({
                "id": node.id, "name": node.properties.name, "label": node.label.value,
                "line": node.properties.start_line or 0,
            })

    # Sort symbols by line
    for syms in file_symbols.values():
        syms.sort(key=lambda s: s.get("line", 0))

    # Build nested tree
    for rel_path in sorted(file_symbols.keys()):
        parts = rel_path.split("/")
        current = tree["children"]
        for i, part in enumerate(parts[:-1]):
            if part not in current:
                current[part] = {"name": part, "type": "dir", "children": {}}
            current = current[part]["children"]
        fname = parts[-1]
        current[fname] = {
            "name": fname, "type": "file", "path": rel_path,
            "symbols": file_symbols[rel_path],
        }

    return tree


def build_search_results(graph: KnowledgeGraph, query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search nodes by name substring."""
    if not query:
        return []
    q = query.lower()
    results: list[dict[str, Any]] = []
    for node in graph.iter_nodes():
        if node.label in (NodeLabel.FOLDER,):
            continue
        if q in node.properties.name.lower():
            results.append({
                "id": node.id, "name": node.properties.name, "label": node.label.value,
                "file": os.path.basename(node.properties.file_path) if node.properties.file_path else "",
            })
            if len(results) >= limit:
                break
    return results


# ---------------------------------------------------------------------------
# HTML template (3d-force-graph + sidebar + inspector)
# ---------------------------------------------------------------------------

_STATIC_DIR = Path(__file__).parent / "static"


def _load_html() -> str:
    """Load and compose the main HTML template from static files."""
    css = (_STATIC_DIR / "graph.css").read_text(encoding="utf-8")
    js = (_STATIC_DIR / "graph.js").read_text(encoding="utf-8")
    html = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return html.replace("{{GRAPH_CSS}}", css).replace("{{GRAPH_JS}}", js)


_HTML = _load_html()


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------

_DEBUG_HTML = """<!DOCTYPE html>
<html><head><title>vector-graph debug</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark-dimmed.min.css">
</head>
<body style="background:#1e1e2e;color:#cdd6f4;font:13px monospace;padding:20px;max-width:800px">
<h2 style="color:#89b4fa">Inspector Debug</h2>
<pre id="log" style="white-space:pre-wrap"></pre>
<div id="code-output" style="margin-top:20px"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/python.min.js"></script>
<script>
function log(msg) { document.getElementById('log').textContent += msg + '\\n'; }

async function run() {
  log('Step 1: Loading /api/data...');
  var data = await fetch('/api/data').then(r => r.json());
  log('  Loaded ' + data.nodes.length + ' nodes');

  var fn = data.nodes.find(n => n.source && n.label === 'Function');
  if (!fn) { log('ERROR: No function with source found!'); return; }
  log('Step 2: Found node: ' + fn.name + ' (' + fn.source.length + ' chars source)');
  log('  First 100: ' + fn.source.substring(0, 100));

  log('Step 3: Testing hljs.highlight...');
  try {
    var result = hljs.highlight(fn.source, {language: 'python'});
    log('  hljs OK: ' + result.value.length + ' chars HTML');

    log('Step 4: Rendering to DOM...');
    document.getElementById('code-output').innerHTML =
      '<h3 style="color:#89b4fa">' + fn.name + '</h3>' +
      '<pre style="background:#11111b;padding:12px;border-radius:6px;border:1px solid #313244;max-height:400px;overflow:auto">' +
      '<code class="hljs">' + result.value + '</code></pre>';
    log('  DOM updated. You should see code below.');
  } catch(e) {
    log('ERROR in hljs: ' + e.message);
    document.getElementById('code-output').innerHTML =
      '<pre style="background:#11111b;padding:12px">' + fn.source.replace(/</g,'&lt;') + '</pre>';
  }

  log('\\nStep 5: Now testing showInspectorImmediate logic...');
  var nd = fn;
  var html = '';
  if (nd.source) {
    log('  nd.source exists: ' + nd.source.length + ' chars');
    var highlighted;
    try {
      highlighted = hljs.highlight(nd.source, {language: 'python'}).value;
      log('  highlight OK');
    } catch(e) {
      highlighted = nd.source.replace(/&/g,'&amp;').replace(/</g,'&lt;');
      log('  highlight failed, using plain: ' + e.message);
    }
    html = '<div style="margin-top:20px"><h3 style="color:#a6e3a1">showInspectorImmediate output:</h3>' +
      '<pre style="background:#11111b;padding:12px;border-radius:6px;border:1px solid #313244;max-height:300px;overflow:auto">' +
      '<code class="hljs">' + highlighted + '</code></pre></div>';
    log('  Built HTML: ' + html.length + ' chars');
  } else {
    log('  nd.source is falsy!');
  }
  document.getElementById('code-output').innerHTML += html;
  log('\\nDone. If you see code above, the logic works.');
}
run();
</script>
</body></html>"""


def serve(
    graph: KnowledgeGraph,
    root_path: str = ".",
    host: str = "127.0.0.1",
    port: int = 5555,
    max_nodes: int = 600,
    change_tracker=None,
) -> None:
    """Start local HTTP server with 3D graph visualization.

    Parameters
    ----------
    graph:
        Fully-built KnowledgeGraph to visualize.
    root_path:
        Project root used for path relativization and source display.
    host / port:
        Bind address.
    max_nodes:
        Maximum nodes included in the graph JSON payload.
    change_tracker:
        Optional ChangeTracker instance.  When provided, the server exposes
        /api/changes (recent events) and /api/session (summary) and
        /api/events (SSE stream) that push real-time change notifications.
    """
    print("Preparing graph data...")
    # Pre-compute health scores for the visualization
    from vector_graph.analysis.complexity import analyze_complexity, build_health_report
    complexity_scores = analyze_complexity(graph)
    cc_map = {s.node_id: s for s in complexity_scores}
    health_report = build_health_report(graph, root_path=root_path)
    health_report_json = json.dumps({
        "total_functions": health_report.total_functions,
        "avg_complexity": health_report.avg_complexity,
        "high_risk_count": health_report.high_risk_count,
        "critical_risk_count": health_report.critical_risk_count,
        "functions": [
            {
                "node_id": f.node_id,
                "name": f.name,
                "file_path": f.file_path,
                "cyclomatic": f.cyclomatic,
                "line_count": f.line_count,
                "parameter_count": f.parameter_count,
                "risk": f.risk,
            }
            for f in health_report.functions
        ],
        "modules": [
            {
                "group": m.group,
                "node_count": m.node_count,
                "avg_complexity": m.avg_complexity,
                "max_complexity": m.max_complexity,
                "coupling_ratio": m.coupling_ratio,
                "cohesion": m.cohesion,
                "god_functions": m.god_functions,
                "god_classes": m.god_classes,
                "risk": m.risk,
            }
            for m in health_report.modules
        ],
    }).encode()
    data_json = json.dumps(
        build_graph_data(graph, max_nodes=max_nodes, root_path=root_path, health_map=cc_map)
    ).encode()
    tree_data = build_file_tree(graph, root_path)
    html_bytes = _HTML.encode("utf-8")
    root_resolved = os.path.realpath(root_path)

    # SSE broadcaster — wired up when a ChangeTracker is provided
    from vector_graph.api.sse_server import SSEBroadcaster
    import queue as _queue
    broadcaster = SSEBroadcaster()
    if change_tracker is not None:
        change_tracker.on_change(lambda evt: broadcaster.push(evt.to_dict(), "change"))

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            params = dict(urllib.parse.parse_qsl(parsed.query))

            if path == "/" or path == "/index.html":
                self._respond(200, "text/html", html_bytes)
            elif path == "/api/logo":
                # Look for logo relative to package root (../../logo.png from api/web_server.py)
                candidates = [
                    Path(__file__).parent.parent.parent / "logo.png",
                    Path(root_resolved) / "logo.png",
                ]
                logo_data = None
                for lp in candidates:
                    if lp.exists():
                        logo_data = lp.read_bytes()
                        break
                if logo_data:
                    self._respond(200, "image/png", logo_data)
                else:
                    self.send_error(404)
            elif path == "/api/data":
                req_mode = params.get("mode", "logic")
                if req_mode not in _MODE_LABELS:
                    req_mode = "logic"
                if req_mode == "logic" and not params.get("mode"):
                    # Use pre-computed payload for the default mode
                    self._respond(200, "application/json", data_json)
                else:
                    payload = json.dumps(
                        build_graph_data(
                            graph,
                            max_nodes=max_nodes if req_mode == "logic" else None,
                            root_path=root_path,
                            health_map=cc_map,
                            mode=req_mode,
                        )
                    ).encode()
                    self._respond(200, "application/json", payload)
            elif path == "/api/source":
                result = build_source_response(
                    params.get("file", ""),
                    root_resolved,
                    int(params["start"]) if "start" in params else None,
                    int(params["end"]) if "end" in params else None,
                )
                self._json(result)
            elif path == "/api/context":
                result = build_context_response(graph, params.get("node", ""))
                self._json(result)
            elif path == "/api/impact":
                node_id = params.get("node", "")
                direction = params.get("direction", "upstream")
                from vector_graph.analysis.impact import analyze_impact
                impact = analyze_impact(graph, node_id, direction=direction, max_depth=3)
                self._json(impact.to_dict())
            elif path == "/api/search":
                results = build_search_results(graph, params.get("q", ""))
                self._json({"results": results})
            elif path == "/api/tree":
                self._json(tree_data)
            elif path == "/api/health":
                self._respond(200, "application/json", health_report_json)
            elif path == "/api/events":
                # Server-Sent Events stream — long-lived connection
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                client_queue = broadcaster.add_client()
                try:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    while True:
                        try:
                            msg = client_queue.get(timeout=15)
                            self.wfile.write(msg.encode())
                            self.wfile.flush()
                        except _queue.Empty:
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    broadcaster.remove_client(client_queue)
            elif path == "/api/changes":
                if change_tracker is not None:
                    limit = int(params.get("limit", "50"))
                    events = change_tracker.get_events(limit=limit)
                    self._json({"events": [e.to_dict() for e in events]})
                else:
                    self._json({"events": []})
            elif path == "/api/session":
                if change_tracker is not None:
                    self._json(change_tracker.session_summary())
                else:
                    self._json({
                        "event_count": 0,
                        "files_changed": 0,
                        "nodes_added": 0,
                        "nodes_modified": 0,
                        "nodes_removed": 0,
                        "high_risk_changes": 0,
                        "groups_affected": [],
                    })
            elif path == "/api/quick-check":
                # Lightweight risk check for hook integration — O(edges) for the file
                file_param = params.get("file", "")
                if not file_param:
                    self._json({"risk": "LOW", "dependents": 0, "nodes": 0})
                else:
                    # Resolve file path against root
                    check_path = os.path.realpath(os.path.join(root_resolved, file_param))
                    dependents = 0
                    node_count = 0
                    for node in graph.iter_nodes():
                        if node.properties.file_path and os.path.realpath(node.properties.file_path) == check_path:
                            node_count += 1
                            for edge in graph.get_edges_to(node.id):
                                if edge.edge_type in (EdgeType.CALLS, EdgeType.IMPORTS):
                                    src = graph.get_node(edge.source_id)
                                    if src and os.path.realpath(src.properties.file_path or "") != check_path:
                                        dependents += 1
                    qc_risk = "LOW"
                    if dependents > 20: qc_risk = "CRITICAL"
                    elif dependents > 10: qc_risk = "HIGH"
                    elif dependents > 3: qc_risk = "MEDIUM"
                    self._json({"risk": qc_risk, "dependents": dependents, "nodes": node_count, "file": file_param})
            elif path == "/api/suggest-tests":
                name = params.get("name", "")
                if not name:
                    self._json({"suggestions": []})
                else:
                    from vector_graph.analysis.suggest_tests import suggest_tests
                    suggestions = suggest_tests(graph, name)
                    self._json({"suggestions": [
                        {
                            "test_file": s.test_file,
                            "test_name": s.test_name,
                            "depth": s.depth,
                        }
                        for s in suggestions
                    ]})
            elif path == "/api/git-history":
                try:
                    from vector_graph.analysis.git_history import (
                        analyze_hotspots,
                        analyze_co_changes,
                        get_git_summary,
                    )
                    days = int(params.get("days", "90"))
                    hotspots = analyze_hotspots(root_resolved, days=days)
                    co_changes = analyze_co_changes(root_resolved, days=days)
                    summary = get_git_summary(root_resolved, days=days)
                    self._json({
                        "hotspots": [
                            {
                                "file": h.file_path,
                                "changes": h.change_count,
                                "recent": h.recent_changes,
                                "score": round(h.hotspot_score, 2),
                                "contributors": list(h.top_contributors),
                                "last_modified": h.last_modified,
                            }
                            for h in sorted(
                                hotspots.values(),
                                key=lambda h: h.hotspot_score,
                                reverse=True,
                            )
                        ],
                        "co_changes": [
                            {
                                "file_a": e.file_a,
                                "file_b": e.file_b,
                                "count": e.co_change_count,
                                "confidence": e.confidence,
                            }
                            for e in co_changes
                        ],
                        "summary": summary,
                    })
                except ImportError:
                    self._json({"error": "git_history module not available", "hotspots": [], "co_changes": [], "summary": {}})
            elif path == "/debug":
                self._respond(200, "text/html", _DEBUG_HTML.encode())
            else:
                self.send_error(404)

        def _respond(self, code: int, content_type: str, body: bytes) -> None:
            try:
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

        def _json(self, obj: Any) -> None:
            body = json.dumps(obj).encode()
            self._respond(200, "application/json", body)

        def log_message(self, fmt: str, *args: Any) -> None:
            pass

    server = http.server.HTTPServer((host, port), Handler)
    print(f"vector-graph 3D running at http://{host}:{port}")
    print("Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        print("\nStopped.")
