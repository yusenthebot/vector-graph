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
    max_nodes: int = 600,
    root_path: str = "",
    health_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert KnowledgeGraph to JSON for 3d-force-graph.

    Prioritizes ROS2 > Class > Function > Method > File to ensure
    important nodes are included before the limit is hit.
    Each node includes a ``group`` field for nebula clustering.
    """
    skip_labels = {NodeLabel.FOLDER}
    all_nodes = [n for n in graph.iter_nodes() if n.label not in skip_labels]
    all_nodes.sort(key=lambda n: _LABEL_PRIORITY.get(n.label, 50))

    nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()

    for node in all_nodes:
        if len(nodes) >= max_nodes:
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

    links: list[dict[str, Any]] = []
    for edge in graph.iter_edges():
        if edge.source_id in node_ids and edge.target_id in node_ids:
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

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>vector-graph</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark-dimmed.min.css">
<style>
:root {
  --bg: #11111b; --base: #1e1e2e; --mantle: #181825; --surface0: #313244;
  --surface1: #45475a; --surface2: #585b70; --overlay0: #6c7086;
  --text: #cdd6f4; --subtext: #a6adc8; --blue: #89b4fa; --green: #a6e3a1;
  --yellow: #f9e2af; --red: #f38ba8; --mauve: #cba6f7; --teal: #94e2d5;
  --sky: #89dceb; --peach: #fab387; --pink: #f5c2e7; --lavender: #b4befe;
}
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:'JetBrains Mono','Fira Code',monospace; overflow:hidden; font-size:12px; }
#app { display:flex; height:100vh; }

/* Sidebar */
#sidebar { width:280px; min-width:280px; background:var(--mantle); border-right:1px solid var(--surface0); display:flex; flex-direction:column; overflow:hidden; z-index:10; }
#sidebar-header { padding:10px 12px; border-bottom:1px solid var(--surface0); }
#sidebar-header h1 { font-size:13px; color:var(--blue); margin-bottom:6px; }
#search { width:100%; padding:5px 8px; background:var(--surface0); border:1px solid var(--surface1); border-radius:4px; color:var(--text); font-size:11px; font-family:inherit; outline:none; }
#search:focus { border-color:var(--blue); }
#search-results { position:absolute; top:100%; left:0; right:0; background:var(--base); border:1px solid var(--surface1); border-radius:4px; max-height:200px; overflow-y:auto; z-index:50; display:none; }
#search-results .sr { padding:4px 8px; cursor:pointer; display:flex; align-items:center; gap:6px; font-size:11px; }
#search-results .sr:hover { background:var(--surface0); }
.search-wrap { position:relative; }

/* Tabs */
.sidebar-tabs { display:flex; border-bottom:1px solid var(--surface0); }
.sidebar-tab { flex:1; padding:6px 0; text-align:center; font-size:10px; color:var(--overlay0); cursor:pointer; border-bottom:2px solid transparent; text-transform:uppercase; letter-spacing:0.5px; }
.sidebar-tab:hover { color:var(--text); }
.sidebar-tab.active { color:var(--blue); border-bottom-color:var(--blue); }
.sidebar-panel { flex:1; overflow-y:auto; display:none; }
.sidebar-panel.active { display:block; }
.sidebar-panel::-webkit-scrollbar { width:3px; }
.sidebar-panel::-webkit-scrollbar-thumb { background:var(--surface1); border-radius:2px; }

/* File tree */
.tree-dir { cursor:pointer; user-select:none; }
.tree-dir-label { display:flex; align-items:center; gap:4px; padding:1px 0 1px 0; color:var(--subtext); font-size:11px; }
.tree-dir-label:hover { color:var(--text); }
.tree-dir-label .arrow { color:var(--overlay0); font-size:8px; width:10px; display:inline-block; }
.tree-dir.collapsed > .tree-children { display:none; }
.tree-dir.collapsed > .tree-dir-label .arrow { transform:rotate(-90deg); }
.tree-children { padding-left:12px; }
.tree-file { display:flex; align-items:center; gap:4px; padding:1px 0; cursor:pointer; font-size:11px; color:var(--subtext); }
.tree-file:hover { color:var(--blue); }
.tree-file.active { color:var(--blue); background:var(--surface0); margin:0 -4px; padding:1px 4px; border-radius:2px; }
.tree-symbol { display:flex; align-items:center; gap:4px; padding:0 0 0 8px; cursor:pointer; font-size:10px; color:var(--overlay0); }
.tree-symbol:hover { color:var(--text); }

/* Filters */
.filter-group { margin-bottom:8px; }
.filter-group h3 { font-size:9px; color:var(--overlay0); text-transform:uppercase; letter-spacing:1px; margin-bottom:3px; }
.ftoggle { display:flex; align-items:center; gap:5px; padding:1px 0; cursor:pointer; user-select:none; font-size:11px; }
.ftoggle:hover { color:var(--text); }
.ftoggle.off { color:var(--surface2); text-decoration:line-through; }
.fdot { width:7px; height:7px; border-radius:50%; flex-shrink:0; }
.ftoggle.off .fdot { opacity:0.2; }
.fcount { margin-left:auto; color:var(--overlay0); font-size:10px; }
.depth-bar { display:flex; gap:3px; margin-top:4px; }
.depth-btn { padding:2px 7px; border-radius:3px; border:1px solid var(--surface1); background:transparent; color:var(--subtext); cursor:pointer; font-family:inherit; font-size:10px; }
.depth-btn.active { background:var(--blue); color:var(--bg); border-color:var(--blue); }

#sidebar-stats { padding:6px 12px; border-top:1px solid var(--surface0); font-size:10px; color:var(--overlay0); }

/* Graph */
#graph-container { flex:1; position:relative; background:var(--bg); overflow:hidden; min-width:0; }
#graph-container > div { position:absolute !important; width:100% !important; height:100% !important; }
#graph-container canvas { cursor:grab; }
#graph-container canvas:active { cursor:grabbing; }

/* Inspector */
#inspector { width:380px; min-width:300px; max-width:500px; background:var(--mantle); border-left:1px solid var(--surface0); display:none; flex-direction:column; overflow:hidden; z-index:20; position:relative; }
#inspector.open { display:flex; }
#insp-header { padding:10px 12px; border-bottom:1px solid var(--surface0); display:flex; align-items:center; gap:8px; }
.type-badge { padding:1px 6px; border-radius:3px; font-size:9px; font-weight:bold; text-transform:uppercase; }
#insp-name { font-size:13px; font-weight:bold; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
#insp-close { background:none; border:none; color:var(--overlay0); cursor:pointer; font-size:16px; font-family:inherit; }
#insp-close:hover { color:var(--red); }
#insp-meta { padding:6px 12px; font-size:10px; color:var(--subtext); border-bottom:1px solid var(--surface0); }
#insp-body { flex:1; overflow-y:auto; }
#insp-body::-webkit-scrollbar { width:3px; }
#insp-body::-webkit-scrollbar-thumb { background:var(--surface1); border-radius:2px; }
.insp-section { padding:8px 12px; border-bottom:1px solid var(--surface0); }
.insp-section h4 { font-size:9px; color:var(--overlay0); text-transform:uppercase; letter-spacing:0.5px; margin-bottom:6px; }
.insp-section pre { background:var(--base); border-radius:4px; padding:8px; overflow-x:auto; font-size:11px; max-height:300px; overflow-y:auto; }
.insp-section code { font-family:inherit; }
.rel-item { padding:3px 0; cursor:pointer; display:flex; align-items:center; gap:6px; }
.rel-item:hover { color:var(--blue); }
.rel-type { font-size:9px; color:var(--overlay0); }
.risk-badge { padding:1px 6px; border-radius:3px; font-size:9px; font-weight:bold; }
.risk-CRITICAL { background:#f38ba822; color:var(--red); }
.risk-HIGH { background:#fab38722; color:var(--peach); }
.risk-MEDIUM { background:#f9e2af22; color:var(--yellow); }
.risk-LOW { background:#a6e3a122; color:var(--green); }

/* Top bar */
#topbar { position:absolute; top:10px; left:50%; transform:translateX(-50%); background:var(--mantle)dd; border:1px solid var(--surface0); border-radius:6px; padding:4px 14px; font-size:11px; color:var(--subtext); z-index:20; display:flex; gap:12px; backdrop-filter:blur(8px); }
#topbar span { color:var(--blue); }

/* Bottom help */
#helpbar { position:absolute; bottom:10px; left:50%; transform:translateX(-50%); background:var(--mantle)cc; border:1px solid var(--surface0); border-radius:6px; padding:3px 10px; font-size:10px; color:var(--overlay0); z-index:20; display:flex; gap:10px; backdrop-filter:blur(8px); }
#helpbar kbd { background:var(--surface0); padding:0 4px; border-radius:2px; color:var(--subtext); }
</style>
</head>
<body>
<div id="app">
  <div id="sidebar">
    <div id="sidebar-header">
      <h1>vector-graph</h1>
      <div class="search-wrap">
        <input id="search" placeholder="Search... (Ctrl+K)" autocomplete="off">
        <div id="search-results"></div>
      </div>
    </div>
    <div class="sidebar-tabs">
      <div class="sidebar-tab active" onclick="switchTab('explorer')">Explorer</div>
      <div class="sidebar-tab" onclick="switchTab('groups')">Groups</div>
      <div class="sidebar-tab" onclick="switchTab('filters')">Filters</div>
      <div class="sidebar-tab" onclick="switchTab('changes')">Changes</div>
    </div>
    <div id="panel-explorer" class="sidebar-panel active" style="padding:6px 8px"></div>
    <div id="panel-groups" class="sidebar-panel" style="padding:6px 12px"></div>
    <div id="panel-filters" class="sidebar-panel" style="padding:6px 12px"></div>
    <div id="panel-changes" class="sidebar-panel" style="padding:6px 8px"></div>
    <div id="sidebar-stats"></div>
  </div>
  <div id="graph-container">
    <div id="topbar"></div>
    <div id="helpbar">
      <span><kbd>Click</kbd> inspect</span>
      <span><kbd>Scroll</kbd> zoom</span>
      <span><kbd>Drag</kbd> rotate</span>
      <span><kbd>Right-drag</kbd> pan</span>
      <span><kbd>Esc</kbd> deselect</span>
      <span><kbd>Group</kbd> click sidebar to focus</span>
    </div>
  </div>
  <aside id="inspector">
    <div id="insp-header">
      <span class="type-badge" id="insp-badge"></span>
      <span id="insp-name"></span>
      <button id="insp-close">&times;</button>
    </div>
    <div id="insp-meta"></div>
    <div id="insp-body"></div>
  </aside>
</div>

<script src="https://unpkg.com/three@0.137.0/build/three.min.js"></script>
<script src="https://unpkg.com/three@0.137.0/examples/js/postprocessing/EffectComposer.js"></script>
<script src="https://unpkg.com/three@0.137.0/examples/js/postprocessing/RenderPass.js"></script>
<script src="https://unpkg.com/three@0.137.0/examples/js/postprocessing/UnrealBloomPass.js"></script>
<script src="https://unpkg.com/3d-force-graph@1.79.1/dist/3d-force-graph.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/python.min.js"></script>
<script>
// ── Config ──────────────────────────────────────────────────
const COLORS = {
  File:'#585b70', Folder:'#585b70', Module:'#fab387',
  Function:'#89b4fa', Class:'#cba6f7', Method:'#94e2d5',
  Variable:'#a6adc8', Property:'#a6adc8', Decorator:'#f5c2e7',
  ROS2Node:'#f38ba8', Topic:'#f9e2af', Service:'#a6e3a1',
  Action:'#f5c2e7', Parameter:'#89dceb',
  Community:'#b4befe', Process:'#f2cdcd'
};
const SIZES = {
  File:2, Folder:2, Module:3, Function:4, Class:6, Method:3,
  Variable:2, Property:2, Decorator:2,
  ROS2Node:5, Topic:4, Service:4, Action:4, Parameter:3,
  Community:3, Process:3
};
const EDGE_COLORS = {
  CALLS:'#89b4fa', IMPORTS:'#fab387', HAS_METHOD:'#94e2d5',
  EXTENDS:'#cba6f7', IMPLEMENTS:'#cba6f7', CONTAINS:'#45475a',
  DEFINES:'#45475a', DECORATES:'#f5c2e7', HAS_PROPERTY:'#a6adc8',
  PUBLISHES_TO:'#a6e3a1', SUBSCRIBES_TO:'#f9e2af',
  PROVIDES_SERVICE:'#f38ba8', CALLS_SERVICE:'#f38ba8',
  PROVIDES_ACTION:'#f5c2e7', CALLS_ACTION:'#f5c2e7',
  USES_PARAMETER:'#89dceb', STEP_IN_PROCESS:'#b4befe', MEMBER_OF:'#b4befe'
};
const GROUPS = {
  Structure: ['File','Folder','Module'],
  Code: ['Function','Class','Method','Variable','Property','Decorator'],
  ROS2: ['ROS2Node','Topic','Service','Action','Parameter'],
};

// ── State ───────────────────────────────────────────────────
let allNodes = [], allLinks = [];
let enabledLabels = new Set(Object.keys(COLORS));
let enabledEdges = new Set(Object.keys(EDGE_COLORS));
let selectedId = null;
let highlightNodes = new Set();
let highlightLinks = new Set();
let depthFilter = 0; // 0 = all
let graph3d = null;
let linkIndex = {from: {}, to: {}}; // pre-built for O(1) lookups
let GROUP_COLORS = {}; // populated in loadData after nodes arrive
let nebulaGroup = null;
let healthMode = false; // OFF by default — show per-type label colors

// ── Change tracking state (Live Radar) ──
let activeChangeIds = new Set();    // nodes directly changed (persistent until next change)
let activeImpactIds = new Set();    // impact chain nodes (depth 1-2 callers)
let cumulativeHeat = {};            // nodeId -> change count this session
let changeHighlightActive = false;  // true when showing change overlay

// ── Data loading ────────────────────────────────────────────
async function loadData() {
  const r = await fetch('/api/data');
  const d = await r.json();
  allNodes = d.nodes;
  allLinks = d.links;
  // Build link index for O(1) lookups (perf optimization)
  linkIndex = {from: {}, to: {}};
  allLinks.forEach(l => {
    const sid = typeof l.source === 'object' ? l.source.id : l.source;
    const tid = typeof l.target === 'object' ? l.target.id : l.target;
    (linkIndex.from[sid] = linkIndex.from[sid] || []).push(l);
    (linkIndex.to[tid] = linkIndex.to[tid] || []).push(l);
  });
  // Generate group colors using golden-ratio hue spacing
  const groupNames = [...new Set(allNodes.map(n => n.group))].sort();
  GROUP_COLORS = {};
  groupNames.forEach((g, i) => {
    const hue = (i * 137.508) % 360;
    GROUP_COLORS[g] = `hsl(${hue}, 80%, 58%)`;
  });
  initGraph();
  buildFilters();
  buildExplorer();
  buildGroupsPanel();
  updateChangesPanel();
  updateStats();
}

// ── Graph init ──────────────────────────────────────────────
function initGraph() {
  const container = document.getElementById('graph-container');
  const {nodes, links} = getFilteredData();

  graph3d = ForceGraph3D()(container)
    .graphData({nodes, links})
    .backgroundColor('#11111b')
    .showNavInfo(false)
    // Node appearance — dim unconnected when something is selected
    .nodeColor(n => {
      // 1. User selection (click) — highest priority
      if (selectedId) {
        if (n.id === selectedId) return '#ffffff';
        if (highlightNodes.has(n.id)) return GROUP_COLORS[n.group] || COLORS[n.label] || '#cdd6f4';
        return '#08080e';
      }
      // 2. Change highlight — soft: changed nodes glow, rest keeps color but dimmed
      if (changeHighlightActive) {
        if (activeChangeIds.has(n.id)) return '#f9e2af'; // bright yellow — directly changed
        if (activeImpactIds.has(n.id)) return '#fab387'; // warm orange — impact chain
        // Everything else keeps its group color but dimmed
        // Convert HSL to dimmed version by reducing lightness
        const gc = GROUP_COLORS[n.group] || '#45475a';
        if (gc.startsWith('hsl')) {
          return gc.replace(/\d+%\)$/, '25%)'); // reduce lightness to 25%
        }
        return '#1a1a2e';
      }
      // 3. Cumulative heat (session-level, always shown)
      const heat = cumulativeHeat[n.id] || 0;
      if (heat > 0) {
        if (heat >= 4) return '#f38ba8'; // hot red — changed 4+ times
        if (heat >= 2) return '#fab387'; // warm orange — changed 2-3 times
        // heat == 1: subtle warm tint — blend with group color
      }
      // 4. Health gradient (opt-in toggle)
      if (healthMode && n.healthRisk) {
        if (n.healthRisk === 'CRITICAL') return '#f38ba8';
        if (n.healthRisk === 'HIGH') return '#fab387';
        if (n.healthRisk === 'MEDIUM') return '#f9e2af';
        return '#a6e3a1';
      }
      // 5. Default: group color
      return GROUP_COLORS[n.group] || COLORS[n.label] || '#cdd6f4';
    })
    .nodeRelSize(4)
    .nodeVal(n => {
      // User selection dimming
      if (selectedId && n.id !== selectedId && !highlightNodes.has(n.id)) return 0.3;
      // Change highlight sizing — changed nodes larger, rest normal
      if (changeHighlightActive) {
        if (activeChangeIds.has(n.id)) return 8;
        if (activeImpactIds.has(n.id)) return 5;
        return SIZES[n.label] || 2; // keep normal size
      }
      const base = SIZES[n.label] || 2;
      if (n.complexity) return base + Math.min(n.complexity * 0.3, 5);
      return base;
    })
    .nodeOpacity(0.9)
    .nodeLabel(n => {
      const c = COLORS[n.label] || '#cdd6f4';
      let t = '<div style="background:#181825f0;padding:8px 12px;border-radius:6px;font:11px monospace;color:#cdd6f4;border:1px solid ' + c + ';max-width:360px;line-height:1.5">';
      t += '<b style="color:' + c + ';font-size:12px">' + n.name + '</b>';
      t += ' <span style="background:' + c + '22;color:' + c + ';padding:1px 5px;border-radius:3px;font-size:9px">' + n.label + '</span>';
      if (n.file) t += '<br><span style="color:#a6adc8">&#128196; ' + n.file.split('/').pop() + (n.line ? ':' + n.line : '') + '</span>';
      if (n.returnType) t += '<br><span style="color:#94e2d5">&#8594; ' + n.returnType + '</span>';
      if (n.params && n.params.length) t += '<br><span style="color:#89dceb">(' + n.params.join(', ') + ')</span>';
      if (n.bases && n.bases.length) t += '<br><span style="color:#cba6f7">extends ' + n.bases.join(', ') + '</span>';
      // Health metrics
      if (n.complexity) {
        const riskColor = n.healthRisk === 'CRITICAL' ? '#f38ba8' : n.healthRisk === 'HIGH' ? '#fab387' : n.healthRisk === 'MEDIUM' ? '#f9e2af' : '#a6e3a1';
        t += '<br><span style="color:' + riskColor + '">&#9632; cc=' + n.complexity + ' ' + (n.healthRisk||'') + '</span>';
        if (n.lineCount) t += ' <span style="color:#585b70">' + n.lineCount + ' lines</span>';
      }
      // Show connections summary (use pre-built index)
      const inCount = linkIndex.to[n.id] ? linkIndex.to[n.id].length : 0;
      const outCount = linkIndex.from[n.id] ? linkIndex.from[n.id].length : 0;
      if (inCount || outCount) t += '<br><span style="color:#585b70">&#8592;' + inCount + ' &#8594;' + outCount + '</span>';
      t += '</div>';
      return t;
    })
    // Edge appearance — highlight connected edges
    .linkColor(l => {
      const sid = typeof l.source === 'object' ? l.source.id : l.source;
      const tid = typeof l.target === 'object' ? l.target.id : l.target;
      // User selection
      if (selectedId) {
        if (sid === selectedId || tid === selectedId) return EDGE_COLORS[l.type] || '#89b4fa';
        return '#08080e';
      }
      // Change highlight — show impact chain edges
      if (changeHighlightActive) {
        const srcHit = activeChangeIds.has(sid) || activeImpactIds.has(sid);
        const tgtHit = activeChangeIds.has(tid) || activeImpactIds.has(tid);
        if (srcHit && tgtHit) return '#fab387'; // orange impact chain
        if (activeChangeIds.has(sid) || activeChangeIds.has(tid)) return '#f9e2af55'; // faint for partial
        return '#08080e00'; // invisible
      }
      return EDGE_COLORS[l.type] || '#45475a';
    })
    .linkOpacity(l => {
      const sid = typeof l.source === 'object' ? l.source.id : l.source;
      const tid = typeof l.target === 'object' ? l.target.id : l.target;
      if (selectedId) {
        return (sid === selectedId || tid === selectedId) ? 0.9 : 0.0;
      }
      if (changeHighlightActive) {
        const srcHit = activeChangeIds.has(sid) || activeImpactIds.has(sid);
        const tgtHit = activeChangeIds.has(tid) || activeImpactIds.has(tid);
        if (srcHit && tgtHit) return 0.8;
        return 0.0;
      }
      return 0.1;
    })
    .linkWidth(l => {
      const sid = typeof l.source === 'object' ? l.source.id : l.source;
      const tid = typeof l.target === 'object' ? l.target.id : l.target;
      if (selectedId) {
        return (sid === selectedId || tid === selectedId) ? 2.0 : 0.0;
      }
      if (changeHighlightActive) {
        const srcHit = activeChangeIds.has(sid) || activeImpactIds.has(sid);
        const tgtHit = activeChangeIds.has(tid) || activeImpactIds.has(tid);
        if (srcHit && tgtHit) return 2.5;
        return 0.0;
      }
      return 0.15;
    })
    .linkCurvature(l => {
      if (l.type === 'CALLS') return 0.15;
      if (l.type === 'IMPORTS') return 0.2;
      if (l.type === 'EXTENDS') return 0.25;
      return 0.1;
    })
    .linkCurveRotation(l => l.type === 'IMPORTS' ? Math.PI * 0.5 : 0)
    .linkDirectionalArrowLength(l => {
      if (!selectedId) return 0; // hide arrows when nothing selected — big perf win
      const sid = typeof l.source === 'object' ? l.source.id : l.source;
      const tid = typeof l.target === 'object' ? l.target.id : l.target;
      return (sid === selectedId || tid === selectedId) ? 3 : 0;
    })
    .linkDirectionalArrowRelPos(1)
    .linkDirectionalParticles(l => {
      const sid = typeof l.source === 'object' ? l.source.id : l.source;
      const tid = typeof l.target === 'object' ? l.target.id : l.target;
      // Change highlight: particles flow along impact chain
      if (changeHighlightActive) {
        const srcHit = activeChangeIds.has(sid) || activeImpactIds.has(sid);
        const tgtHit = activeChangeIds.has(tid) || activeImpactIds.has(tid);
        return (srcHit && tgtHit) ? 3 : 0;
      }
      // User selection
      if (selectedId) {
        return (sid === selectedId || tid === selectedId) ? 2 : 0;
      }
      return 0;
    })
    .linkDirectionalParticleWidth(1.5)
    .linkDirectionalParticleSpeed(0.008)
    .linkDirectionalParticleColor(l => {
      if (changeHighlightActive) return '#f9e2af'; // warm yellow particles for changes
      return EDGE_COLORS[l.type] || '#89b4fa';
    })
    .onNodeClick(n => { if (n) selectNode(n.id); })
    .onBackgroundClick(() => { deselectNode(); clearChangeHighlight(); })
    .warmupTicks(80)
    .cooldownTicks(120)
    .d3AlphaDecay(0.04)
    .d3VelocityDecay(0.4)
    .d3AlphaMin(0.01)
    .enableNodeDrag(true)
    .enableNavigationControls(true)


  // Seed initial positions by group — spread groups apart before simulation
  _seedGroupPositions(nodes);

  // Inject clustering force — strong enough to overcome link/charge forces
  graph3d.d3Force('cluster', clusterForce(0.6));
  // Weaker charge so groups stay compact, stronger inter-group repulsion handled by cluster
  graph3d.d3Force('charge').strength(-15);
  // Weaker link distance so intra-group links pull tight
  graph3d.d3Force('link').distance(20).strength(0.3);

  // Render nebulae once when simulation stabilizes
  graph3d.onEngineStop(() => updateNebulae());
}

function _seedGroupPositions(nodes) {
  // Assign initial positions to separate groups spatially
  const groups = {};
  nodes.forEach(n => {
    const g = n.group || 'other';
    if (!groups[g]) groups[g] = [];
    groups[g].push(n);
  });
  const groupNames = Object.keys(groups);
  const spread = 250; // wider spread for clearer group separation
  groupNames.forEach((g, i) => {
    // Arrange group centers on a sphere using fibonacci sphere
    const phi = Math.acos(1 - 2 * (i + 0.5) / groupNames.length);
    const theta = Math.PI * (1 + Math.sqrt(5)) * i;
    const gx = spread * Math.sin(phi) * Math.cos(theta);
    const gy = spread * Math.sin(phi) * Math.sin(theta);
    const gz = spread * Math.cos(phi);
    groups[g].forEach(n => {
      n.x = gx + (Math.random() - 0.5) * 30;
      n.y = gy + (Math.random() - 0.5) * 30;
      n.z = gz + (Math.random() - 0.5) * 30;
    });
  });
}

function clusterForce(strength) {
  let nodes;
  function force(alpha) {
    // Compute group centroids
    const centroids = {};
    const counts = {};
    nodes.forEach(n => {
      const g = n.group || 'other';
      if (!centroids[g]) { centroids[g] = {x:0,y:0,z:0}; counts[g] = 0; }
      centroids[g].x += n.x || 0;
      centroids[g].y += n.y || 0;
      centroids[g].z += n.z || 0;
      counts[g]++;
    });
    Object.keys(centroids).forEach(g => {
      centroids[g].x /= counts[g];
      centroids[g].y /= counts[g];
      centroids[g].z /= counts[g];
    });

    // Pull nodes toward their own group centroid
    const k = strength * alpha;
    nodes.forEach(n => {
      const c = centroids[n.group || 'other'];
      if (c) {
        n.vx += (c.x - n.x) * k;
        n.vy += (c.y - n.y) * k;
        n.vz += (c.z - n.z) * k;
      }
    });

    // Push group centroids apart from each other (inter-group repulsion)
    const gNames = Object.keys(centroids);
    const repel = 2000 * alpha;
    for (let i = 0; i < gNames.length; i++) {
      for (let j = i + 1; j < gNames.length; j++) {
        const a = centroids[gNames[i]], b = centroids[gNames[j]];
        const dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
        const dist2 = dx*dx + dy*dy + dz*dz + 1;
        const f = repel / dist2;
        // Apply to all nodes in each group
        const cntA = counts[gNames[i]], cntB = counts[gNames[j]];
        nodes.forEach(n => {
          if (n.group === gNames[i]) { n.vx += dx * f / cntA; n.vy += dy * f / cntA; n.vz += dz * f / cntA; }
          if (n.group === gNames[j]) { n.vx -= dx * f / cntB; n.vy -= dy * f / cntB; n.vz -= dz * f / cntB; }
        });
      }
    }
  }
  force.initialize = (_nodes) => { nodes = _nodes; };
  return force;
}

function getFilteredData() {
  let nodes = allNodes.filter(n => enabledLabels.has(n.label));
  let nodeSet = new Set(nodes.map(n => n.id));

  // Depth filter (BFS from selected)
  if (selectedId && depthFilter > 0) {
    const visible = bfsFromNode(selectedId, depthFilter);
    nodes = nodes.filter(n => visible.has(n.id));
    nodeSet = new Set(nodes.map(n => n.id));
  }

  const links = allLinks.filter(l => {
    const sid = typeof l.source === 'object' ? l.source.id : l.source;
    const tid = typeof l.target === 'object' ? l.target.id : l.target;
    return nodeSet.has(sid) && nodeSet.has(tid) && enabledEdges.has(l.type);
  });
  return {nodes, links};
}

function bfsFromNode(startId, maxDepth) {
  const visited = new Set([startId]);
  let frontier = [startId];
  for (let d = 0; d < maxDepth; d++) {
    const next = [];
    for (const nid of frontier) {
      // Use index instead of scanning all links
      (linkIndex.from[nid] || []).forEach(l => {
        const tid = typeof l.target === 'object' ? l.target.id : l.target;
        if (!visited.has(tid)) { visited.add(tid); next.push(tid); }
      });
      (linkIndex.to[nid] || []).forEach(l => {
        const sid = typeof l.source === 'object' ? l.source.id : l.source;
        if (!visited.has(sid)) { visited.add(sid); next.push(sid); }
      });
    }
    frontier = next;
  }
  return visited;
}

function refreshGraph() {
  if (!graph3d) return;
  const {nodes, links} = getFilteredData();
  _seedGroupPositions(nodes);
  graph3d.graphData({nodes, links});
  updateStats();
}

// ── Selection ───────────────────────────────────────────────
function selectNode(id) {
  selectedId = id;
  // Build highlight sets using pre-built index
  highlightNodes.clear();
  highlightLinks.clear();
  (linkIndex.from[id] || []).forEach(l => {
    const tid = typeof l.target === 'object' ? l.target.id : l.target;
    highlightNodes.add(tid); highlightLinks.add(l);
  });
  (linkIndex.to[id] || []).forEach(l => {
    const sid = typeof l.source === 'object' ? l.source.id : l.source;
    highlightNodes.add(sid); highlightLinks.add(l);
  });
  // Force re-render — update colors, sizes, edges
  graph3d.nodeColor(graph3d.nodeColor());
  graph3d.nodeVal(graph3d.nodeVal());
  graph3d.linkColor(graph3d.linkColor());
  graph3d.linkWidth(graph3d.linkWidth());
  graph3d.linkOpacity(graph3d.linkOpacity());
  graph3d.linkDirectionalParticles(graph3d.linkDirectionalParticles());
  // Show inspector immediately with local data, then fetch details async
  showInspectorImmediate(id);
  fetchInspectorDetails(id);
  // Camera fly-to
  const node = graph3d.graphData().nodes.find(n => n.id === id);
  if (node) {
    const dist = 80;
    graph3d.cameraPosition(
      {x: node.x + dist, y: node.y + dist/2, z: node.z + dist},
      {x: node.x, y: node.y, z: node.z},
      1000
    );
  }
  // Nebula highlighting for selected node's group
  if (nebulaGroup) {
    const selNode = allNodes.find(n => n.id === id);
    nebulaGroup.children.forEach(child => {
      if (!child.userData) return;
      const match = selNode && child.userData.groupName === selNode.group;
      if (child.userData.isNebula) {
        child.material.opacity = match ? 0.15 : 0.02;
      }
      if (child.userData.isLabel) {
        child.material.opacity = match ? 1.0 : 0.3;
      }
    });
  }
  updateDepthButtons();
}

function deselectNode() {
  selectedId = null;
  depthFilter = 0;
  highlightNodes.clear();
  highlightLinks.clear();
  document.getElementById('inspector').classList.remove('open');
  setTimeout(function() { if (graph3d) graph3d.width(document.getElementById('graph-container').clientWidth); }, 100);
  graph3d.nodeColor(graph3d.nodeColor());
  graph3d.nodeVal(graph3d.nodeVal());
  graph3d.linkColor(graph3d.linkColor());
  graph3d.linkWidth(graph3d.linkWidth());
  graph3d.linkOpacity(graph3d.linkOpacity());
  // Reset nebula opacities
  if (nebulaGroup) {
    nebulaGroup.children.forEach(child => {
      if (!child.userData) return;
      if (child.userData.isNebula) child.material.opacity = 0.07;
      if (child.userData.isLabel) child.material.opacity = 1.0;
    });
  }
  refreshGraph();
  updateDepthButtons();
}

// ── Inspector ───────────────────────────────────────────────

function showInspectorImmediate(nodeId) {
  // Show panel immediately with data we already have (from allNodes)
  const panel = document.getElementById('inspector');
  const nd = allNodes.find(n => n.id === nodeId);
  if (!nd) return;

  panel.classList.add('open');
  // Resize graph to fit new available space
  setTimeout(function() { if (graph3d) graph3d.width(document.getElementById('graph-container').clientWidth); }, 100);
  const color = COLORS[nd.label] || '#cdd6f4';

  // Header
  document.getElementById('insp-badge').textContent = nd.label;
  document.getElementById('insp-badge').style.cssText = 'background:' + color + '22;color:' + color;
  document.getElementById('insp-name').textContent = nd.name;

  // Meta
  var meta = '';
  if (nd.file) meta += nd.file.split('/').pop();
  if (nd.line) meta += ':' + nd.line;
  if (nd.params && nd.params.length) meta += ' | (' + nd.params.join(', ') + ')';
  if (nd.returnType) meta += ' -> ' + nd.returnType;
  if (nd.bases && nd.bases.length) meta += ' | extends ' + nd.bases.join(', ');
  document.getElementById('insp-meta').textContent = meta;

  // Build connections from local data immediately
  var html = '';
  var inLinks = linkIndex.to[nodeId] || [];
  var outLinks = linkIndex.from[nodeId] || [];

  if (inLinks.length) {
    html += '<div class="insp-section"><h4>Called by (' + inLinks.length + ')</h4>';
    inLinks.slice(0, 20).forEach(function(l) {
      var sid = typeof l.source === 'object' ? l.source.id : l.source;
      var src = allNodes.find(function(n) { return n.id === sid; });
      if (src) {
        var c = COLORS[src.label] || '#cdd6f4';
        html += '<div class="rel-item" onclick="selectNode(\'' + sid + '\')"><span class="fdot" style="background:' + c + '"></span>' + src.name + ' <span class="rel-type">' + l.type + '</span></div>';
      }
    });
    html += '</div>';
  }

  if (outLinks.length) {
    html += '<div class="insp-section"><h4>Calls (' + outLinks.length + ')</h4>';
    outLinks.slice(0, 20).forEach(function(l) {
      var tid = typeof l.target === 'object' ? l.target.id : l.target;
      var tgt = allNodes.find(function(n) { return n.id === tid; });
      if (tgt) {
        var c = COLORS[tgt.label] || '#cdd6f4';
        html += '<div class="rel-item" onclick="selectNode(\'' + tid + '\')"><span class="fdot" style="background:' + c + '"></span>' + tgt.name + ' <span class="rel-type">' + l.type + '</span></div>';
      }
    });
    html += '</div>';
  }

  // Health metrics section
  if (nd.complexity) {
    var riskColor = nd.healthRisk === 'CRITICAL' ? 'var(--red)' : nd.healthRisk === 'HIGH' ? 'var(--peach)' : nd.healthRisk === 'MEDIUM' ? 'var(--yellow)' : 'var(--green)';
    html += '<div class="insp-section"><h4>Health</h4>';
    html += '<span class="risk-badge risk-' + (nd.healthRisk||'LOW') + '">' + (nd.healthRisk||'LOW') + '</span> ';
    html += '<span style="color:' + riskColor + '">complexity=' + nd.complexity + '</span>';
    if (nd.lineCount) html += ' &middot; ' + nd.lineCount + ' lines';
    html += '</div>';
  }

  // Source code — inline for functions/methods, lazy fetch for files
  if (nd.source) {
    var highlighted;
    try {
      highlighted = (typeof hljs !== 'undefined') ? hljs.highlight(nd.source, {language: 'python'}).value : escHtml(nd.source);
    } catch(e) {
      highlighted = escHtml(nd.source);
    }
    html += '<div class="insp-section"><h4>Source</h4><pre style="max-height:350px;overflow:auto"><code class="hljs">' + highlighted + '</code></pre></div>';
  } else if (nd.file) {
    html += '<div id="insp-source-lazy" class="insp-section"><h4>Source</h4><div style="color:var(--overlay0)">Loading...</div></div>';
  }

  html += '<div id="insp-impact"></div>';

  document.getElementById('insp-body').innerHTML = html;
}

function fetchInspectorDetails(nodeId) {
  var nd = allNodes.find(function(n) { return n.id === nodeId; });

  // Lazy-load source for File nodes (not inlined to keep payload small)
  if (nd && nd.file && !nd.source) {
    var srcUrl = '/api/source?file=' + encodeURIComponent(nd.file);
    if (nd.line > 0) srcUrl += '&start=' + nd.line + '&end=' + (nd.endLine || nd.line);
    fetch(srcUrl)
      .then(function(r) { return r.json(); })
      .then(function(srcR) {
        var el = document.getElementById('insp-source-lazy');
        if (!el || selectedId !== nodeId) return;
        if (srcR && srcR.content) {
          var code = srcR.content.length > 5000 ? srcR.content.slice(0, 5000) + '\n# ...' : srcR.content;
          var hi;
          try { hi = hljs.highlight(code, {language: 'python'}).value; } catch(e) { hi = escHtml(code); }
          el.innerHTML = '<h4>Source</h4><pre style="max-height:350px;overflow:auto"><code class="hljs">' + hi + '</code></pre>';
        }
      })
      .catch(function(err) { console.error('lazy source:', err); });
  }

  // Fetch impact
  fetch('/api/impact?node=' + encodeURIComponent(nodeId))
    .then(function(r) { return r.json(); })
    .then(function(impR) {
      var el = document.getElementById('insp-impact');
      if (!el || selectedId !== nodeId) return;
      if (impR && impR.risk) {
        var h = '<div class="insp-section"><h4>Impact</h4>';
        h += '<span class="risk-badge risk-' + impR.risk + '">' + impR.risk + '</span> ' + (impR.impacted_count || 0) + ' affected';
        if (impR.entries) {
          impR.entries.slice(0, 5).forEach(function(e) {
            h += '<div style="font-size:10px;padding:2px 0;color:' + (e.depth===1 ? 'var(--red)' : 'var(--overlay0)') + '">d=' + e.depth + ' ' + e.name + '</div>';
          });
        }
        h += '</div>';
        el.innerHTML = h;
      }
    })
    .catch(function(err) { console.error('impact fetch error:', err); });
}

function escHtml(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function updateNebulae() {
  if (!graph3d || typeof THREE === 'undefined') return;
  const scene = graph3d.scene();
  if (!scene) return;

  // Remove old nebulae
  if (nebulaGroup) scene.remove(nebulaGroup);
  nebulaGroup = new THREE.Group();

  // Group real nodes by group field
  const groups = {};
  graph3d.graphData().nodes.forEach(n => {
    const g = n.group || 'other';
    if (!groups[g]) groups[g] = [];
    groups[g].push(n);
  });

  Object.entries(groups).forEach(([name, nodes]) => {
    if (nodes.length < 2) return;

    // Centroid
    let cx = 0, cy = 0, cz = 0;
    nodes.forEach(n => { cx += n.x||0; cy += n.y||0; cz += n.z||0; });
    cx /= nodes.length; cy /= nodes.length; cz /= nodes.length;

    // Radius
    let maxDist = 0;
    nodes.forEach(n => {
      const d = Math.sqrt(((n.x||0)-cx)**2 + ((n.y||0)-cy)**2 + ((n.z||0)-cz)**2);
      if (d > maxDist) maxDist = d;
    });
    const radius = Math.max(maxDist * 1.4, 20);

    const color = new THREE.Color(GROUP_COLORS[name] || '#888888');

    // ── 1. Transparent sphere shell ──
    const shellGeo = new THREE.SphereGeometry(radius, 32, 24);
    const shellMat = new THREE.MeshBasicMaterial({
      color: color,
      transparent: true,
      opacity: 0.07,
      depthWrite: false,
      side: THREE.BackSide,
    });
    const shell = new THREE.Mesh(shellGeo, shellMat);
    shell.position.set(cx, cy, cz);
    shell.userData = { groupName: name, isNebula: true };
    nebulaGroup.add(shell);

    // ── 2. Inner glow sphere ──
    const glowGeo = new THREE.SphereGeometry(radius * 0.4, 16, 12);
    const glowMat = new THREE.MeshBasicMaterial({
      color: color,
      transparent: true,
      opacity: 0.05,
      depthWrite: false,
    });
    const glow = new THREE.Mesh(glowGeo, glowMat);
    glow.position.set(cx, cy, cz);
    nebulaGroup.add(glow);

    // ── 3. Stardust particles ──
    const dustCount = Math.min(Math.max(Math.floor(nodes.length * 0.5), 10), 80);
    const positions = new Float32Array(dustCount * 3);
    const colors = new Float32Array(dustCount * 3);

    for (let i = 0; i < dustCount; i++) {
      // Uniform distribution inside sphere
      let dx, dy, dz;
      do {
        dx = (Math.random() - 0.5) * 2;
        dy = (Math.random() - 0.5) * 2;
        dz = (Math.random() - 0.5) * 2;
      } while (dx*dx + dy*dy + dz*dz > 1);

      positions[i*3]     = cx + dx * radius * 0.85;
      positions[i*3 + 1] = cy + dy * radius * 0.85;
      positions[i*3 + 2] = cz + dz * radius * 0.85;

      // Slight color variation
      const brightness = 0.7 + Math.random() * 0.3;
      colors[i*3]     = color.r * brightness;
      colors[i*3 + 1] = color.g * brightness;
      colors[i*3 + 2] = color.b * brightness;
    }

    const dustGeo = new THREE.BufferGeometry();
    dustGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    dustGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    const dustMat = new THREE.PointsMaterial({
      size: 1.5,
      transparent: true,
      opacity: 0.5,
      vertexColors: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true,
    });
    nebulaGroup.add(new THREE.Points(dustGeo, dustMat));

    // ── 4. Orbital ring ──
    const ringGeo = new THREE.TorusGeometry(radius * 0.95, 0.4, 8, 64);
    const ringMat = new THREE.MeshBasicMaterial({
      color: color,
      transparent: true,
      opacity: 0.15,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.position.set(cx, cy, cz);
    ring.rotation.x = Math.random() * Math.PI;
    ring.rotation.z = Math.random() * Math.PI * 0.5;
    nebulaGroup.add(ring);

    // ── 5. Group name label (always visible sprite) ──
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    canvas.width = 1024;
    canvas.height = 128;

    // Glow background
    ctx.shadowColor = GROUP_COLORS[name] || '#888';
    ctx.shadowBlur = 30;
    ctx.font = 'bold 52px monospace';
    ctx.fillStyle = GROUP_COLORS[name] || '#cdd6f4';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const shortName = name.split('/').pop() || name;
    ctx.fillText(shortName, 512, 50);
    // Count subtitle
    ctx.shadowBlur = 0;
    ctx.font = '28px monospace';
    ctx.globalAlpha = 0.6;
    ctx.fillText(nodes.length + ' nodes', 512, 100);

    const texture = new THREE.CanvasTexture(canvas);
    const spriteMat = new THREE.SpriteMaterial({
      map: texture,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const sprite = new THREE.Sprite(spriteMat);
    const scale = Math.max(radius * 1.2, 35);
    sprite.position.set(cx, cy + radius + 10, cz);
    sprite.scale.set(scale, scale * 0.125, 1);
    sprite.userData = { groupName: name, isLabel: true };
    nebulaGroup.add(sprite);
  });

  scene.add(nebulaGroup);
}

// ── Groups sidebar panel ─────────────────────────────────────
function buildGroupsPanel() {
  const el = document.getElementById('panel-groups');
  const groupCounts = {};
  allNodes.forEach(n => {
    const g = n.group || 'other';
    groupCounts[g] = (groupCounts[g] || 0) + 1;
  });

  const sorted = Object.entries(groupCounts).sort((a,b) => b[1] - a[1]);
  let html = '<div class="filter-group"><h3>Packages</h3>';
  sorted.forEach(([name, count]) => {
    const color = GROUP_COLORS[name] || '#888';
    const shortName = name.split('/').pop() || name;
    html += `<div class="ftoggle" onclick="focusGroup('${name.replace(/'/g, "\\'")}')">
      <span class="fdot" style="background:${color}"></span>
      ${shortName}
      <span class="fcount">${count}</span>
    </div>`;
  });
  html += '</div>';
  el.innerHTML = html;
}

function focusGroup(groupName) {
  const groupNodes = graph3d.graphData().nodes.filter(n => n.group === groupName);
  if (!groupNodes.length) return;

  let cx = 0, cy = 0, cz = 0;
  groupNodes.forEach(n => { cx += n.x||0; cy += n.y||0; cz += n.z||0; });
  cx /= groupNodes.length; cy /= groupNodes.length; cz /= groupNodes.length;

  let maxDist = 0;
  groupNodes.forEach(n => {
    const d = Math.sqrt(((n.x||0)-cx)**2 + ((n.y||0)-cy)**2 + ((n.z||0)-cz)**2);
    if (d > maxDist) maxDist = d;
  });
  const dist = Math.max(maxDist * 2, 50);

  graph3d.cameraPosition(
    {x: cx + dist * 0.7, y: cy + dist * 0.4, z: cz + dist * 0.7},
    {x: cx, y: cy, z: cz},
    1500
  );

  // Nebula highlight for focused group
  if (nebulaGroup) {
    nebulaGroup.children.forEach(child => {
      if (!child.userData) return;
      const match = child.userData.groupName === groupName;
      if (child.userData.isNebula) child.material.opacity = match ? 0.18 : 0.02;
      if (child.userData.isLabel) child.material.opacity = match ? 1.0 : 0.25;
    });
  }
}

// ── Sidebar tabs ────────────────────────────────────────────
function switchTab(tab) {
  document.querySelectorAll('.sidebar-tab').forEach(t => t.classList.toggle('active', t.textContent.toLowerCase().includes(tab)));
  document.querySelectorAll('.sidebar-panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-' + tab).classList.add('active');
}

// ── File tree (Explorer tab) ────────────────────────────────
async function buildExplorer() {
  try {
    const tree = await fetch('/api/tree').then(r => r.json());
    const el = document.getElementById('panel-explorer');
    el.innerHTML = renderTreeNode(tree);
  } catch(e) {
    document.getElementById('panel-explorer').innerHTML = '<div style="padding:8px;color:var(--overlay0)">Failed to load tree</div>';
  }
}

function renderTreeNode(node) {
  if (node.type === 'file') {
    const hasSymbols = node.symbols && node.symbols.length > 0;
    let html = '<div class="tree-dir' + (hasSymbols ? '' : '') + '">';
    html += '<div class="tree-file" onclick="' + (hasSymbols ? "this.parentElement.classList.toggle('collapsed');" : '') + "focusFile('" + escAttr(node.path) + "')\">";
    if (hasSymbols) html += '<span class="arrow" style="font-size:7px">&#9660;</span> ';
    html += '<span style="color:var(--blue)">&#128196;</span> ' + node.name + '</div>';
    if (hasSymbols) {
      html += '<div class="tree-children">';
      node.symbols.forEach(s => {
        const c = COLORS[s.label] || '#a6adc8';
        const icon = s.label === 'Class' ? '&#9670;' : s.label === 'Method' ? '&#9702;' : '&#402;';
        html += '<div class="tree-symbol" onclick="event.stopPropagation();selectNode(\'' + s.id + '\')">';
        html += '<span style="color:' + c + '">' + icon + '</span> ' + s.name;
        html += ' <span style="color:var(--surface2);font-size:9px">' + s.label + '</span>';
        html += '</div>';
      });
      html += '</div>';
    }
    html += '</div>';
    return html;
  }
  // Directory — collapsed by default except top level
  let html = '<div class="tree-dir collapsed">';
  html += '<div class="tree-dir-label" onclick="this.parentElement.classList.toggle(\'collapsed\')">';
  html += '<span class="arrow">&#9660;</span> &#128193; ' + node.name + '</div>';
  html += '<div class="tree-children">';
  if (node.children) {
    const sorted = Object.values(node.children).sort((a,b) => {
      if (a.type !== b.type) return a.type === 'dir' ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    sorted.forEach(child => { html += renderTreeNode(child); });
  }
  html += '</div></div>';
  return html;
}

function escAttr(s) { return s.replace(/'/g, "\\'").replace(/"/g, '&quot;'); }

function focusFile(relPath) {
  // Find a node in this file and select it
  const fileNode = allNodes.find(n => n.label === 'File' && n.file && n.file.endsWith('/' + relPath));
  if (fileNode) selectNode(fileNode.id);
}

// ── Sidebar filters (Filters tab) ──────────────────────────
function buildFilters() {
  const el = document.getElementById('panel-filters');
  let html = '';

  // Count nodes per label
  const counts = {};
  allNodes.forEach(n => { counts[n.label] = (counts[n.label]||0) + 1; });

  // Node type groups
  for (const [group, labels] of Object.entries(GROUPS)) {
    const present = labels.filter(l => counts[l]);
    if (!present.length) continue;
    html += `<div class="filter-group"><h3>${group}</h3>`;
    present.forEach(l => {
      const on = enabledLabels.has(l);
      html += `<div class="ftoggle ${on?'':'off'}" data-label="${l}" onclick="toggleLabel('${l}')">
        <span class="fdot" style="background:${COLORS[l]}"></span>${l}<span class="fcount">${counts[l]}</span></div>`;
    });
    html += '</div>';
  }

  // Edge types
  const edgeCounts = {};
  allLinks.forEach(l => { edgeCounts[l.type] = (edgeCounts[l.type]||0) + 1; });
  const presentEdges = Object.keys(EDGE_COLORS).filter(e => edgeCounts[e]);
  if (presentEdges.length) {
    html += `<div class="filter-group"><h3>Edges</h3>`;
    presentEdges.forEach(e => {
      const on = enabledEdges.has(e);
      html += `<div class="ftoggle ${on?'':'off'}" data-edge="${e}" onclick="toggleEdge('${e}')">
        <span class="fdot" style="background:${EDGE_COLORS[e]}"></span>${e}<span class="fcount">${edgeCounts[e]}</span></div>`;
    });
    html += '</div>';
  }

  // Depth filter
  html += `<div class="filter-group"><h3>Depth (select node first)</h3><div class="depth-bar" id="depth-bar">
    <button class="depth-btn active" onclick="setDepth(0)">All</button>
    <button class="depth-btn" onclick="setDepth(1)">1</button>
    <button class="depth-btn" onclick="setDepth(2)">2</button>
    <button class="depth-btn" onclick="setDepth(3)">3</button>
  </div></div>`;

  // Health mode toggle
  html += `<div class="filter-group"><h3>Node Color Mode</h3>
    <div class="ftoggle" id="health-toggle" onclick="toggleHealthMode()" style="cursor:pointer">
      <span class="fdot" style="background:var(--green)"></span>
      <span id="health-toggle-label">Label colors</span>
      <span class="fcount" style="font-size:9px">click to toggle</span>
    </div>
    <div style="font-size:10px;color:var(--overlay0);margin-top:4px">
      <span style="color:#a6e3a1">&#9679;</span> LOW &nbsp;
      <span style="color:#f9e2af">&#9679;</span> MEDIUM &nbsp;
      <span style="color:#fab387">&#9679;</span> HIGH &nbsp;
      <span style="color:#f38ba8">&#9679;</span> CRITICAL
    </div>
  </div>`;

  el.innerHTML = html;
}

function toggleHealthMode() {
  healthMode = !healthMode;
  const label = document.getElementById('health-toggle-label');
  if (label) label.textContent = healthMode ? 'Health gradient' : 'Label colors';
  const dot = document.querySelector('#health-toggle .fdot');
  if (dot) dot.style.background = healthMode ? '#f38ba8' : 'var(--green)';
  if (graph3d) graph3d.nodeColor(graph3d.nodeColor());
}

function toggleLabel(label) {
  enabledLabels.has(label) ? enabledLabels.delete(label) : enabledLabels.add(label);
  document.querySelectorAll(`[data-label="${label}"]`).forEach(el => el.classList.toggle('off'));
  refreshGraph();
}

function toggleEdge(edge) {
  enabledEdges.has(edge) ? enabledEdges.delete(edge) : enabledEdges.add(edge);
  document.querySelectorAll(`[data-edge="${edge}"]`).forEach(el => el.classList.toggle('off'));
  refreshGraph();
}

function setDepth(d) {
  depthFilter = d;
  updateDepthButtons();
  refreshGraph();
}

function updateDepthButtons() {
  document.querySelectorAll('.depth-btn').forEach((btn, i) => {
    btn.classList.toggle('active', i === depthFilter);
  });
}

function updateStats() {
  const {nodes, links} = getFilteredData();
  const groupCount = new Set(allNodes.map(n => n.group)).size;
  document.getElementById('sidebar-stats').textContent = `${nodes.length} nodes · ${links.length} edges · ${groupCount} groups`;
  document.getElementById('topbar').innerHTML = `<span>${allNodes.length}</span> nodes &middot; <span>${allLinks.length}</span> edges &middot; <span>${groupCount}</span> groups`;
}

// ── Search ──────────────────────────────────────────────────
const searchInput = document.getElementById('search');
const searchResults = document.getElementById('search-results');
let searchTimeout = null;

searchInput.addEventListener('input', () => {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(async () => {
    const q = searchInput.value.trim();
    if (!q) { searchResults.style.display = 'none'; return; }
    const r = await fetch('/api/search?q=' + encodeURIComponent(q)).then(r=>r.json());
    if (!r.results || !r.results.length) { searchResults.style.display = 'none'; return; }
    searchResults.innerHTML = r.results.map(n =>
      `<div class="sr" onclick="selectNode('${n.id}');searchResults.style.display='none';searchInput.value='';">
        <span class="fdot" style="background:${COLORS[n.label]||'#cdd6f4'}"></span>
        <span>${escHtml(n.name)}</span>
        <span style="color:var(--overlay0);font-size:10px">${n.label} · ${n.file}</span>
      </div>`
    ).join('');
    searchResults.style.display = 'block';
  }, 200);
});

searchInput.addEventListener('blur', () => { setTimeout(() => searchResults.style.display = 'none', 200); });
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); searchInput.focus(); }
  if (e.key === 'Escape') { deselectNode(); clearChangeHighlight(); searchResults.style.display = 'none'; searchInput.blur(); }
});

document.getElementById('insp-close').addEventListener('click', deselectNode);

// ── Live Radar: SSE change events ──────────────────────────
let changeHistory = [];
const MAX_CHANGE_HISTORY = 100;

function initSSE() {
  const evtSource = new EventSource('/api/events');

  evtSource.addEventListener('change', function(e) {
    try {
      const change = JSON.parse(e.data);
      changeHistory.unshift(change);
      if (changeHistory.length > MAX_CHANGE_HISTORY) changeHistory.pop();
      handleChangeEvent(change);
      updateChangesPanel();
    } catch(err) {
      console.error('SSE parse error:', err);
    }
  });

  evtSource.onerror = function() {
    // Auto-reconnect is built into EventSource
    console.log('SSE connection lost, reconnecting...');
  };
}

// Start SSE after graph loads
setTimeout(initSSE, 1000);

function handleChangeEvent(change) {
  if (!graph3d) return;
  const gData = graph3d.graphData();

  // Clear user selection — change view takes over
  if (selectedId) {
    selectedId = null;
    highlightNodes.clear();
    highlightLinks.clear();
    document.getElementById('inspector').classList.remove('open');
  }

  // 1. Find directly changed node IDs
  const changedNames = new Set([
    ...(change.nodes_added || []),
    ...(change.nodes_modified || []),
  ]);
  const changedFile = (change.file || '').split('/').pop();

  activeChangeIds.clear();
  activeImpactIds.clear();

  gData.nodes.forEach(n => {
    if (changedNames.has(n.name) && n.file && n.file.endsWith(changedFile)) {
      activeChangeIds.add(n.id);
    }
  });

  // If no exact name match, match all nodes in the changed file
  if (activeChangeIds.size === 0) {
    gData.nodes.forEach(n => {
      if (n.file && changedFile && n.file.endsWith(changedFile)) {
        activeChangeIds.add(n.id);
      }
    });
  }

  // 2. Update cumulative heat
  activeChangeIds.forEach(id => {
    cumulativeHeat[id] = (cumulativeHeat[id] || 0) + 1;
  });

  // 3. Build impact chain — BFS depth 1-2 upstream through callers
  let frontier = [...activeChangeIds];
  let visited = new Set(frontier);
  for (let depth = 0; depth < 2; depth++) {
    const next = [];
    for (const nid of frontier) {
      (linkIndex.to[nid] || []).forEach(l => {
        const sid = typeof l.source === 'object' ? l.source.id : l.source;
        if (!visited.has(sid)) {
          visited.add(sid);
          activeImpactIds.add(sid);
          next.push(sid);
        }
      });
      // Also downstream
      (linkIndex.from[nid] || []).forEach(l => {
        const tid = typeof l.target === 'object' ? l.target.id : l.target;
        if (!visited.has(tid)) {
          visited.add(tid);
          activeImpactIds.add(tid);
          next.push(tid);
        }
      });
    }
    frontier = next;
  }

  // 4. Activate change highlight mode — only if we found affected nodes
  if (activeChangeIds.size === 0) {
    changeHighlightActive = false;
    return; // no matching nodes found, skip visualization
  }
  changeHighlightActive = true;

  // 5. Camera fly-to centroid of changed nodes
  if (activeChangeIds.size > 0) {
    let cx = 0, cy = 0, cz = 0, count = 0;
    gData.nodes.forEach(n => {
      if (activeChangeIds.has(n.id)) {
        cx += n.x || 0; cy += n.y || 0; cz += n.z || 0; count++;
      }
    });
    if (count > 0) {
      cx /= count; cy /= count; cz /= count;
      const dist = 60;
      graph3d.cameraPosition(
        {x: cx + dist, y: cy + dist * 0.4, z: cz + dist},
        {x: cx, y: cy, z: cz},
        1200
      );
    }
  }

  // 6. Trigger full re-render
  graph3d.nodeColor(graph3d.nodeColor());
  graph3d.nodeVal(graph3d.nodeVal());
  graph3d.linkColor(graph3d.linkColor());
  graph3d.linkWidth(graph3d.linkWidth());
  graph3d.linkOpacity(graph3d.linkOpacity());
  graph3d.linkDirectionalParticles(graph3d.linkDirectionalParticles());
  graph3d.linkDirectionalParticleColor(graph3d.linkDirectionalParticleColor());

  // 7. Nebula: softly highlight affected group
  if (nebulaGroup) {
    const affectedGroups = new Set();
    gData.nodes.forEach(n => {
      if (activeChangeIds.has(n.id) && n.group) affectedGroups.add(n.group);
    });
    nebulaGroup.children.forEach(child => {
      if (!child.userData) return;
      if (child.userData.isNebula) {
        child.material.opacity = affectedGroups.has(child.userData.groupName) ? 0.15 : 0.05;
      }
      if (child.userData.isLabel) {
        child.material.opacity = affectedGroups.has(child.userData.groupName) ? 1.0 : 0.5;
      }
    });
  }

  // 8. Open impact tree panel (in inspector area)
  showImpactPanel(change);
}

function showImpactPanel(change) {
  const gData = graph3d ? graph3d.graphData() : {nodes:[]};
  const story = buildChangeStory(change);
  const file = (change.file || '').split('/').pop();
  const risk = change.impact ? change.impact.risk : 'LOW';
  const riskColor = risk === 'CRITICAL' ? 'var(--red)' : risk === 'HIGH' ? 'var(--peach)' : risk === 'MEDIUM' ? 'var(--yellow)' : 'var(--green)';
  const typeLabel = change.type === 'created' ? 'NEW' : change.type === 'deleted' ? 'DEL' : 'MOD';
  const typeColor = change.type === 'created' ? 'var(--green)' : change.type === 'deleted' ? 'var(--red)' : 'var(--yellow)';

  // Use the inspector panel
  const panel = document.getElementById('inspector');
  panel.classList.add('open');
  setTimeout(function() { if (graph3d) graph3d.width(document.getElementById('graph-container').clientWidth); }, 100);

  // Header
  document.getElementById('insp-badge').textContent = typeLabel;
  document.getElementById('insp-badge').style.cssText = 'background:' + typeColor + '22;color:' + typeColor;
  document.getElementById('insp-name').textContent = file;
  document.getElementById('insp-meta').innerHTML = '<span class="risk-badge risk-' + risk + '">' + risk + '</span> <span style="color:var(--overlay0)">risk</span> &middot; <span style="color:var(--text)">' + activeChangeIds.size + ' changed</span> &middot; <span style="color:var(--overlay0)">' + activeImpactIds.size + ' affected</span>';

  // Build tree
  let html = '';
  const added = change.nodes_added || [];
  const modified = change.nodes_modified || [];
  const removed = change.nodes_removed || [];

  // ── What Changed ──
  if (added.length + modified.length + removed.length > 0) {
    html += '<div class="insp-section"><h4>What Changed</h4>';
    added.forEach(name => {
      const nd = gData.nodes.find(n => n.name === name && activeChangeIds.has(n.id));
      html += '<div style="padding:2px 0;font-size:11px">';
      html += '<span style="color:var(--green);font-weight:bold">+</span> ';
      if (nd) html += '<span style="cursor:pointer;color:var(--green)" onclick="selectNode(\'' + nd.id + '\')">' + name + '</span>';
      else html += '<span style="color:var(--green)">' + name + '</span>';
      html += ' <span style="color:var(--surface2);font-size:9px">added</span></div>';
    });
    modified.forEach(name => {
      const nd = gData.nodes.find(n => n.name === name && activeChangeIds.has(n.id));
      html += '<div style="padding:2px 0;font-size:11px">';
      html += '<span style="color:var(--yellow);font-weight:bold">~</span> ';
      if (nd) html += '<span style="cursor:pointer;color:var(--yellow)" onclick="selectNode(\'' + nd.id + '\')">' + name + '</span>';
      else html += '<span style="color:var(--yellow)">' + name + '</span>';
      html += '</div>';
    });
    removed.forEach(name => {
      html += '<div style="padding:2px 0;font-size:11px">';
      html += '<span style="color:var(--red);font-weight:bold">-</span> ';
      html += '<span style="color:var(--red)">' + name + '</span>';
      html += ' <span style="color:var(--surface2);font-size:9px">removed</span></div>';
    });
    html += '</div>';
  }

  // ── Calls (outgoing) ──
  if (story.outgoing.length > 0) {
    html += '<div class="insp-section"><h4>Calls (' + story.outgoing.length + ')</h4>';
    story.outgoing.forEach(dep => {
      const c = GROUP_COLORS[gData.nodes.find(n=>n.id===dep.id)?.group] || 'var(--blue)';
      html += '<div class="rel-item" onclick="selectNode(\'' + dep.id + '\')">';
      html += '<span style="color:var(--blue)">&#8594;</span> ';
      html += '<span class="fdot" style="background:' + c + '"></span>';
      html += dep.name;
      html += ' <span class="rel-type">' + dep.file + '</span>';
      html += '</div>';
    });
    html += '</div>';
  }

  // ── Depended on by (incoming) ──
  if (story.incoming.length > 0) {
    html += '<div class="insp-section"><h4>Depended On By (' + story.incoming.length + ')</h4>';
    story.incoming.forEach(dep => {
      const c = GROUP_COLORS[gData.nodes.find(n=>n.id===dep.id)?.group] || 'var(--peach)';
      html += '<div class="rel-item" onclick="selectNode(\'' + dep.id + '\')">';
      html += '<span style="color:var(--peach)">&#8592;</span> ';
      html += '<span class="fdot" style="background:' + c + '"></span>';
      html += dep.name;
      html += ' <span class="rel-type">' + dep.file + '</span>';
      html += '</div>';
    });
    html += '</div>';
  }

  // ── Impact Summary ──
  if (change.impact && change.impact.affected_count > 0) {
    html += '<div class="insp-section"><h4>Impact</h4>';
    html += '<div style="font-size:11px;color:' + riskColor + ';margin-bottom:4px">' + change.impact.affected_count + ' nodes in blast radius</div>';
    html += '<div style="font-size:10px;color:var(--overlay0)">' + story.incoming.length + ' direct dependents</div>';
    html += '<div style="font-size:10px;color:var(--overlay0)">' + activeImpactIds.size + ' total in impact chain</div>';
    if (change.impact.affected_groups && change.impact.affected_groups.length > 0) {
      html += '<div style="font-size:10px;color:var(--overlay0);margin-top:4px">Groups: ';
      change.impact.affected_groups.forEach(g => {
        const gc = GROUP_COLORS[g] || '#888';
        html += '<span style="color:' + gc + '">' + g.split('/').pop() + '</span> ';
      });
      html += '</div>';
    }
    html += '</div>';
  }

  document.getElementById('insp-body').innerHTML = html;
}

function clearChangeHighlight() {
  changeHighlightActive = false;
  activeChangeIds.clear();
  activeImpactIds.clear();
  // Close impact panel
  document.getElementById('inspector').classList.remove('open');
  setTimeout(function() { if (graph3d) graph3d.width(document.getElementById('graph-container').clientWidth); }, 100);
  // Re-render with normal colors
  graph3d.nodeColor(graph3d.nodeColor());
  graph3d.nodeVal(graph3d.nodeVal());
  graph3d.linkColor(graph3d.linkColor());
  graph3d.linkWidth(graph3d.linkWidth());
  graph3d.linkOpacity(graph3d.linkOpacity());
  graph3d.linkDirectionalParticles(graph3d.linkDirectionalParticles());
  // Reset nebula
  if (nebulaGroup) {
    nebulaGroup.children.forEach(child => {
      if (!child.userData) return;
      if (child.userData.isNebula) child.material.opacity = 0.07;
      if (child.userData.isLabel) child.material.opacity = 1.0;
    });
  }
}

// ── Changes sidebar panel ────────────────────────────────────

function buildChangeStory(change) {
  // Compute outgoing calls and incoming dependents for changed nodes
  const gData = graph3d ? graph3d.graphData() : {nodes:[], links:[]};
  const changedNodes = gData.nodes.filter(n => activeChangeIds.has(n.id));

  const outgoing = []; // what changed nodes call
  const incoming = []; // what calls changed nodes
  const seenOut = new Set();
  const seenIn = new Set();

  changedNodes.forEach(n => {
    (linkIndex.from[n.id] || []).forEach(l => {
      if (l.type !== 'CALLS') return;
      const tid = typeof l.target === 'object' ? l.target.id : l.target;
      if (seenOut.has(tid) || activeChangeIds.has(tid)) return;
      seenOut.add(tid);
      const tgt = gData.nodes.find(x => x.id === tid);
      if (tgt) outgoing.push({name: tgt.name, file: (tgt.file||'').split('/').pop(), id: tid, label: tgt.label});
    });
    (linkIndex.to[n.id] || []).forEach(l => {
      if (l.type !== 'CALLS') return;
      const sid = typeof l.source === 'object' ? l.source.id : l.source;
      if (seenIn.has(sid) || activeChangeIds.has(sid)) return;
      seenIn.add(sid);
      const src = gData.nodes.find(x => x.id === sid);
      if (src) incoming.push({name: src.name, file: (src.file||'').split('/').pop(), id: sid, label: src.label});
    });
  });

  return {changedNodes, outgoing, incoming};
}

function updateChangesPanel() {
  const el = document.getElementById('panel-changes');
  if (!el) return;

  if (changeHistory.length === 0) {
    el.innerHTML = '<div style="padding:8px;color:var(--overlay0);font-size:11px">No changes detected yet.<br>Modify a file while <b>--watch</b> is active.</div>';
    return;
  }

  let html = '';

  // ── Session summary bar ──
  const totalAdded = changeHistory.reduce((s,c) => s + (c.nodes_added||[]).length, 0);
  const totalMod = changeHistory.reduce((s,c) => s + (c.nodes_modified||[]).length, 0);
  const totalDel = changeHistory.reduce((s,c) => s + (c.nodes_removed||[]).length, 0);
  const highRisk = changeHistory.filter(c => c.impact && (c.impact.risk === 'HIGH' || c.impact.risk === 'CRITICAL')).length;

  html += '<div style="padding:6px 4px 8px;border-bottom:1px solid var(--surface0);margin-bottom:6px">';
  html += '<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">';
  html += '<span style="font-size:10px;color:var(--overlay0)">SESSION</span>';
  html += '<span style="font-size:11px;color:var(--text)">' + changeHistory.length + ' changes</span>';
  if (totalAdded) html += '<span style="color:var(--green);font-size:10px">+' + totalAdded + '</span>';
  if (totalMod) html += '<span style="color:var(--yellow);font-size:10px">~' + totalMod + '</span>';
  if (totalDel) html += '<span style="color:var(--red);font-size:10px">-' + totalDel + '</span>';
  html += '</div>';
  if (highRisk) html += '<div style="color:var(--red);font-size:10px;margin-bottom:4px">&#9888; ' + highRisk + ' high-risk changes</div>';
  if (changeHighlightActive) {
    html += '<button onclick="clearChangeHighlight()" style="padding:2px 8px;background:var(--surface1);color:var(--text);border:none;border-radius:3px;cursor:pointer;font-size:9px;font-family:inherit">Clear highlight (ESC)</button>';
  }
  html += '</div>';

  // ── Latest change: full story view ──
  const latest = changeHistory[0];
  if (latest) {
    const story = buildChangeStory(latest);
    const file = (latest.file || '').split('/').pop();
    const risk = latest.impact ? latest.impact.risk : 'LOW';
    const riskColor = risk === 'CRITICAL' ? 'var(--red)' : risk === 'HIGH' ? 'var(--peach)' : risk === 'MEDIUM' ? 'var(--yellow)' : 'var(--green)';
    const typeLabel = latest.type === 'created' ? 'NEW FILE' : latest.type === 'deleted' ? 'DELETED' : 'MODIFIED';
    const typeColor = latest.type === 'created' ? 'var(--green)' : latest.type === 'deleted' ? 'var(--red)' : 'var(--yellow)';

    html += '<div style="background:var(--surface0);border-radius:6px;padding:8px;margin-bottom:8px;border-left:3px solid ' + riskColor + '">';

    // Header
    html += '<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">';
    html += '<span style="color:' + typeColor + ';font-size:9px;font-weight:bold;background:' + typeColor + '18;padding:1px 5px;border-radius:3px">' + typeLabel + '</span>';
    html += '<span style="color:var(--text);font-size:12px;font-weight:bold">' + file + '</span>';
    html += '<span class="risk-badge risk-' + risk + '" style="margin-left:auto">' + risk + '</span>';
    html += '</div>';

    // What changed
    const added = latest.nodes_added || [];
    const modified = latest.nodes_modified || [];
    const removed = latest.nodes_removed || [];
    if (added.length + modified.length + removed.length > 0) {
      html += '<div style="margin-bottom:6px">';
      html += '<div style="font-size:9px;color:var(--overlay0);margin-bottom:3px;text-transform:uppercase;letter-spacing:0.5px">Changes</div>';
      added.slice(0,8).forEach(n => {
        html += '<div style="font-size:10px;padding:1px 0;color:var(--green)">+ ' + n + '</div>';
      });
      modified.slice(0,8).forEach(n => {
        html += '<div style="font-size:10px;padding:1px 0;color:var(--yellow)">~ ' + n + '</div>';
      });
      removed.slice(0,8).forEach(n => {
        html += '<div style="font-size:10px;padding:1px 0;color:var(--red)">- ' + n + '</div>';
      });
      html += '</div>';
    }

    // Calls out to (outgoing)
    if (story.outgoing.length > 0) {
      html += '<div style="margin-bottom:6px">';
      html += '<div style="font-size:9px;color:var(--overlay0);margin-bottom:3px;text-transform:uppercase;letter-spacing:0.5px">Calls</div>';
      story.outgoing.slice(0,6).forEach(dep => {
        html += '<div style="font-size:10px;padding:1px 0;cursor:pointer;color:var(--subtext)" onclick="selectNode(\'' + dep.id + '\')">';
        html += '<span style="color:var(--blue)">&#8594;</span> ' + dep.name + ' <span style="color:var(--surface2)">' + dep.file + '</span></div>';
      });
      if (story.outgoing.length > 6) html += '<div style="font-size:9px;color:var(--surface2)">+' + (story.outgoing.length-6) + ' more</div>';
      html += '</div>';
    }

    // Depended on by (incoming)
    if (story.incoming.length > 0) {
      html += '<div style="margin-bottom:6px">';
      html += '<div style="font-size:9px;color:var(--overlay0);margin-bottom:3px;text-transform:uppercase;letter-spacing:0.5px">Depended on by</div>';
      story.incoming.slice(0,6).forEach(dep => {
        html += '<div style="font-size:10px;padding:1px 0;cursor:pointer;color:var(--subtext)" onclick="selectNode(\'' + dep.id + '\')">';
        html += '<span style="color:var(--peach)">&#8592;</span> ' + dep.name + ' <span style="color:var(--surface2)">' + dep.file + '</span></div>';
      });
      if (story.incoming.length > 6) html += '<div style="font-size:9px;color:var(--surface2)">+' + (story.incoming.length-6) + ' more</div>';
      html += '</div>';
    }

    // Risk summary
    if (latest.impact && latest.impact.affected_count > 0) {
      html += '<div style="margin-bottom:6px;padding:4px 6px;background:var(--mantle);border-radius:4px">';
      html += '<div style="font-size:9px;color:var(--overlay0);margin-bottom:2px;text-transform:uppercase;letter-spacing:0.5px">Impact</div>';
      html += '<div style="font-size:10px;color:' + riskColor + '">' + latest.impact.affected_count + ' nodes in blast radius</div>';
      html += '<div style="font-size:9px;color:var(--overlay0)">';
      html += (story.incoming.length) + ' direct dependents, ' + activeImpactIds.size + ' total in chain';
      html += '</div>';
      if (latest.impact.affected_groups && latest.impact.affected_groups.length > 0) {
        html += '<div style="font-size:9px;color:var(--overlay0);margin-top:2px">Groups: ' + latest.impact.affected_groups.slice(0,5).join(', ') + '</div>';
      }
      html += '</div>';
    }

    // Action buttons
    html += '<div style="display:flex;gap:6px">';
    html += '<button onclick="focusChange(0)" style="padding:3px 10px;background:var(--blue);color:var(--bg);border:none;border-radius:3px;cursor:pointer;font-size:9px;font-family:inherit">Show in graph</button>';
    html += '</div>';
    html += '</div>';
  }

  // ── Previous changes: compact list ──
  if (changeHistory.length > 1) {
    html += '<div style="font-size:9px;color:var(--overlay0);margin:6px 0 4px;text-transform:uppercase;letter-spacing:0.5px">Previous</div>';
    changeHistory.slice(1, 20).forEach((c, i) => {
      const time = new Date(c.timestamp * 1000).toLocaleTimeString();
      const file = (c.file || '').split('/').pop();
      const typeIcon = c.type === 'created' ? '+' : c.type === 'deleted' ? '-' : '~';
      const typeColor = c.type === 'created' ? 'var(--green)' : c.type === 'deleted' ? 'var(--red)' : 'var(--yellow)';
      const risk = c.impact ? c.impact.risk : 'LOW';
      const nodeCount = (c.nodes_added||[]).length + (c.nodes_modified||[]).length + (c.nodes_removed||[]).length;

      html += '<div style="padding:3px 4px;border-bottom:1px solid var(--surface0);font-size:10px;cursor:pointer;display:flex;align-items:center;gap:4px" onclick="focusChange(' + (i+1) + ')">';
      html += '<span style="color:var(--overlay0);font-size:9px">' + time + '</span>';
      html += '<span style="color:' + typeColor + ';font-weight:bold">' + typeIcon + '</span>';
      html += '<span style="color:var(--subtext)">' + file + '</span>';
      if (nodeCount) html += '<span style="color:var(--surface2);font-size:9px">' + nodeCount + '</span>';
      html += '<span class="risk-badge risk-' + risk + '" style="margin-left:auto;font-size:7px">' + risk + '</span>';
      html += '</div>';
    });
  }

  el.innerHTML = html;
  switchTab('changes');
}

function focusChange(changeIndex) {
  if (changeIndex >= changeHistory.length) return;
  // Re-trigger the change event handling (re-focus, re-highlight)
  handleChangeEvent(changeHistory[changeIndex]);
}

// ── Start ───────────────────────────────────────────────────
loadData();
</script>
</body>
</html>"""


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
            elif path == "/api/data":
                self._respond(200, "application/json", data_json)
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
