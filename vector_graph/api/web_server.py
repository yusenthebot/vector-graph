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

def build_graph_data(graph: KnowledgeGraph, max_nodes: int = 600) -> dict[str, Any]:
    """Convert KnowledgeGraph to JSON for 3d-force-graph."""
    skip_labels = {NodeLabel.FOLDER}
    nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()

    for node in graph.iter_nodes():
        if node.label in skip_labels:
            continue
        if len(nodes) >= max_nodes:
            break
        entry: dict[str, Any] = {
            "id": node.id,
            "name": node.properties.name,
            "label": node.label.value,
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
#sidebar { width:250px; min-width:250px; background:var(--mantle); border-right:1px solid var(--surface0); display:flex; flex-direction:column; overflow:hidden; z-index:10; }
#sidebar-header { padding:12px; border-bottom:1px solid var(--surface0); }
#sidebar-header h1 { font-size:14px; color:var(--blue); margin-bottom:6px; }
#search { width:100%; padding:6px 10px; background:var(--surface0); border:1px solid var(--surface1); border-radius:4px; color:var(--text); font-size:11px; font-family:inherit; outline:none; }
#search:focus { border-color:var(--blue); }
#search-results { position:absolute; top:100%; left:0; right:0; background:var(--base); border:1px solid var(--surface1); border-radius:4px; max-height:200px; overflow-y:auto; z-index:50; display:none; }
#search-results .sr { padding:5px 10px; cursor:pointer; display:flex; align-items:center; gap:6px; }
#search-results .sr:hover { background:var(--surface0); }
.search-wrap { position:relative; }

#filters { flex:1; overflow-y:auto; padding:8px 12px; }
#filters::-webkit-scrollbar { width:3px; }
#filters::-webkit-scrollbar-thumb { background:var(--surface1); border-radius:2px; }
.filter-group { margin-bottom:10px; }
.filter-group h3 { font-size:9px; color:var(--overlay0); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px; }
.ftoggle { display:flex; align-items:center; gap:6px; padding:2px 0; cursor:pointer; user-select:none; }
.ftoggle:hover { color:var(--text); }
.ftoggle.off { color:var(--surface2); text-decoration:line-through; }
.fdot { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
.ftoggle.off .fdot { opacity:0.25; }
.fcount { margin-left:auto; color:var(--overlay0); font-size:10px; }

.depth-bar { display:flex; gap:4px; margin-top:6px; }
.depth-btn { padding:2px 8px; border-radius:3px; border:1px solid var(--surface1); background:transparent; color:var(--subtext); cursor:pointer; font-family:inherit; font-size:10px; }
.depth-btn.active { background:var(--blue); color:var(--bg); border-color:var(--blue); }

#sidebar-stats { padding:8px 12px; border-top:1px solid var(--surface0); font-size:10px; color:var(--overlay0); }

/* Graph */
#graph-container { flex:1; position:relative; background:var(--bg); }

/* Inspector */
#inspector { width:380px; min-width:300px; max-width:500px; background:var(--mantle); border-left:1px solid var(--surface0); display:none; flex-direction:column; overflow:hidden; z-index:10; }
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
        <input id="search" placeholder="Search nodes... (Ctrl+K)" autocomplete="off">
        <div id="search-results"></div>
      </div>
    </div>
    <div id="filters"></div>
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
let depthFilter = 0; // 0 = all
let graph3d = null;

// ── Data loading ────────────────────────────────────────────
async function loadData() {
  const r = await fetch('/api/data');
  const d = await r.json();
  allNodes = d.nodes;
  allLinks = d.links;
  initGraph();
  buildFilters();
  updateStats();
}

// ── Graph init ──────────────────────────────────────────────
function initGraph() {
  const container = document.getElementById('graph-container');
  const {nodes, links} = getFilteredData();

  graph3d = ForceGraph3D()(container)
    .graphData({nodes, links})
    .backgroundColor('#11111b')
    .nodeColor(n => selectedId === n.id ? '#f5e0dc' : (COLORS[n.label] || '#cdd6f4'))
    .nodeRelSize(4)
    .nodeVal(n => (SIZES[n.label] || 2))
    .nodeOpacity(0.85)
    .nodeLabel(n => {
      const c = COLORS[n.label] || '#cdd6f4';
      let t = '<div style="background:#181825ee;padding:6px 10px;border-radius:4px;font:11px monospace;color:#cdd6f4;border:1px solid ' + c + '">';
      t += '<b style="color:' + c + '">' + n.label + '</b> ' + n.name;
      if (n.file) t += '<br><span style="color:#a6adc8;font-size:10px">' + n.file.split('/').pop() + (n.line ? ':' + n.line : '') + '</span>';
      t += '</div>';
      return t;
    })
    .linkColor(l => EDGE_COLORS[l.type] || '#45475a')
    .linkOpacity(0.15)
    .linkWidth(0.3)
    .linkDirectionalArrowLength(3)
    .linkDirectionalArrowRelPos(1)
    .linkDirectionalParticles(l => l.type === 'CALLS' ? 1 : 0)
    .linkDirectionalParticleWidth(1)
    .linkDirectionalParticleSpeed(0.005)
    .linkDirectionalParticleColor(l => EDGE_COLORS[l.type] || '#89b4fa')
    .onNodeClick(n => { if (n) selectNode(n.id); })
    .onBackgroundClick(() => { deselectNode(); })
    .warmupTicks(40)
    .cooldownTicks(60);
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
      for (const l of allLinks) {
        const sid = typeof l.source === 'object' ? l.source.id : l.source;
        const tid = typeof l.target === 'object' ? l.target.id : l.target;
        if (sid === nid && !visited.has(tid)) { visited.add(tid); next.push(tid); }
        if (tid === nid && !visited.has(sid)) { visited.add(sid); next.push(sid); }
      }
    }
    frontier = next;
  }
  return visited;
}

function refreshGraph() {
  if (!graph3d) return;
  const {nodes, links} = getFilteredData();
  graph3d.graphData({nodes, links});
  updateStats();
}

// ── Selection ───────────────────────────────────────────────
function selectNode(id) {
  selectedId = id;
  graph3d.nodeColor(graph3d.nodeColor()); // refresh colors for selection
  openInspector(id);
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
  updateDepthButtons();
}

function deselectNode() {
  selectedId = null;
  depthFilter = 0;
  document.getElementById('inspector').classList.remove('open');
  graph3d.nodeColor(graph3d.nodeColor());
  refreshGraph();
  updateDepthButtons();
}

// ── Inspector ───────────────────────────────────────────────
async function openInspector(nodeId) {
  const panel = document.getElementById('inspector');
  panel.classList.add('open');

  // Fetch context + impact in parallel
  const [ctxR, impR] = await Promise.all([
    fetch('/api/context?node=' + encodeURIComponent(nodeId)).then(r=>r.json()),
    fetch('/api/impact?node=' + encodeURIComponent(nodeId)).then(r=>r.json()),
  ]);

  if (ctxR.error) { panel.classList.remove('open'); return; }
  const nd = ctxR.node;
  const color = COLORS[nd.label] || '#cdd6f4';

  // Header
  document.getElementById('insp-badge').textContent = nd.label;
  document.getElementById('insp-badge').style.cssText = `background:${color}22;color:${color}`;
  document.getElementById('insp-name').textContent = nd.name;

  // Meta
  let meta = '';
  if (nd.file) meta += nd.file.split('/').pop();
  if (nd.line) meta += ':' + nd.line;
  if (nd.endLine) meta += '-' + nd.endLine;
  if (nd.params && nd.params.length) meta += ' | params: (' + nd.params.join(', ') + ')';
  if (nd.returnType) meta += ' → ' + nd.returnType;
  if (nd.bases && nd.bases.length) meta += ' | extends: ' + nd.bases.join(', ');
  document.getElementById('insp-meta').textContent = meta;

  // Body
  let html = '';

  // Docstring
  if (nd.doc) {
    html += `<div class="insp-section"><h4>Documentation</h4><pre><code>${escHtml(nd.doc)}</code></pre></div>`;
  }

  // Decorators
  if (nd.decorators && nd.decorators.length) {
    html += `<div class="insp-section"><h4>Decorators</h4>`;
    nd.decorators.forEach(d => { html += `<div style="color:var(--pink)">@${d}</div>`; });
    html += '</div>';
  }

  // Source code
  if (nd.file && nd.line) {
    const srcR = await fetch('/api/source?file=' + encodeURIComponent(nd.file) + '&start=' + nd.line + '&end=' + (nd.endLine||nd.line)).then(r=>r.json());
    if (srcR.content) {
      const highlighted = hljs.highlight(srcR.content, {language:'python'}).value;
      html += `<div class="insp-section"><h4>Source (lines ${srcR.startLine}-${srcR.endLine})</h4><pre><code class="hljs">${highlighted}</code></pre></div>`;
    }
  } else if (nd.file && nd.label === 'File') {
    const srcR = await fetch('/api/source?file=' + encodeURIComponent(nd.file)).then(r=>r.json());
    if (srcR.content) {
      const truncated = srcR.content.length > 3000 ? srcR.content.slice(0,3000) + '\n...' : srcR.content;
      const highlighted = hljs.highlight(truncated, {language:'python'}).value;
      html += `<div class="insp-section"><h4>Source (${srcR.total} lines)</h4><pre><code class="hljs">${highlighted}</code></pre></div>`;
    }
  }

  // Inbound (called by)
  if (ctxR.inbound.length) {
    html += `<div class="insp-section"><h4>Called by (${ctxR.inbound.length})</h4>`;
    ctxR.inbound.slice(0,20).forEach(r => {
      html += `<div class="rel-item" onclick="selectNode('${r.id}')"><span class="fdot" style="background:${COLORS[r.label]||'#cdd6f4'}"></span>${r.name} <span class="rel-type">${r.edgeType} · ${r.file}</span></div>`;
    });
    if (ctxR.inbound.length > 20) html += `<div style="color:var(--overlay0)">+${ctxR.inbound.length-20} more</div>`;
    html += '</div>';
  }

  // Outbound (calls)
  if (ctxR.outbound.length) {
    html += `<div class="insp-section"><h4>Calls (${ctxR.outbound.length})</h4>`;
    ctxR.outbound.slice(0,20).forEach(r => {
      html += `<div class="rel-item" onclick="selectNode('${r.id}')"><span class="fdot" style="background:${COLORS[r.label]||'#cdd6f4'}"></span>${r.name} <span class="rel-type">${r.edgeType} · ${r.file}</span></div>`;
    });
    if (ctxR.outbound.length > 20) html += `<div style="color:var(--overlay0)">+${ctxR.outbound.length-20} more</div>`;
    html += '</div>';
  }

  // Impact
  if (impR && impR.risk) {
    html += `<div class="insp-section"><h4>Impact Analysis</h4>`;
    html += `<span class="risk-badge risk-${impR.risk}">${impR.risk}</span> ${impR.impacted_count||0} affected symbols`;
    if (impR.entries) {
      impR.entries.slice(0,8).forEach(e => {
        html += `<div class="rel-item" style="font-size:10px"><span style="color:${e.depth===1?'var(--red)':'var(--overlay0)'}">d=${e.depth}</span> ${e.name} <span class="rel-type">${e.edge_type}</span></div>`;
      });
    }
    html += '</div>';
  }

  document.getElementById('insp-body').innerHTML = html;
}

function escHtml(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

// ── Sidebar filters ─────────────────────────────────────────
function buildFilters() {
  const el = document.getElementById('filters');
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

  el.innerHTML = html;
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
  document.getElementById('sidebar-stats').textContent = `${nodes.length} nodes · ${links.length} edges (of ${allNodes.length} total)`;
  document.getElementById('topbar').innerHTML = `<span>${allNodes.length}</span> nodes &middot; <span>${allLinks.length}</span> edges &middot; <span>${new Set(allNodes.map(n=>n.file)).size}</span> files`;
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
  if (e.key === 'Escape') { deselectNode(); searchResults.style.display = 'none'; searchInput.blur(); }
});

document.getElementById('insp-close').addEventListener('click', deselectNode);

// ── Start ───────────────────────────────────────────────────
loadData();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------

def serve(
    graph: KnowledgeGraph,
    root_path: str = ".",
    host: str = "127.0.0.1",
    port: int = 5555,
    max_nodes: int = 600,
) -> None:
    """Start local HTTP server with 3D graph visualization."""
    print("Preparing graph data...")
    data_json = json.dumps(build_graph_data(graph, max_nodes=max_nodes)).encode()
    html_bytes = _HTML.encode("utf-8")
    root_resolved = os.path.realpath(root_path)

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
            else:
                self.send_error(404)

        def _respond(self, code: int, content_type: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

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
