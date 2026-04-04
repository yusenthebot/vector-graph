"""Web server for vector-graph visualization. Serves interactive graph at localhost."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>vector-graph</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #1e1e2e; color: #cdd6f4; font-family: 'JetBrains Mono', 'Fira Code', monospace; overflow: hidden; }

#app { display: flex; height: 100vh; }
#sidebar { width: 320px; background: #181825; border-right: 1px solid #313244; display: flex; flex-direction: column; overflow: hidden; }
#graph-container { flex: 1; position: relative; overflow: hidden; }
#canvas { width: 100%; height: 100%; display: block; }

/* Header */
#header { padding: 16px; border-bottom: 1px solid #313244; }
#header h1 { font-size: 16px; color: #89b4fa; margin-bottom: 4px; }
#header .stats { font-size: 11px; color: #a6adc8; }
#header .stats span { color: #89b4fa; }

/* Search */
#search-box { padding: 8px 16px; border-bottom: 1px solid #313244; }
#search { width: 100%; padding: 8px 12px; background: #313244; border: 1px solid #45475a; border-radius: 6px; color: #cdd6f4; font-size: 12px; font-family: inherit; outline: none; }
#search:focus { border-color: #89b4fa; }
#search::placeholder { color: #585b70; }

/* Filters */
#filters { padding: 8px 16px; border-bottom: 1px solid #313244; display: flex; flex-wrap: wrap; gap: 4px; }
.filter-btn { padding: 3px 8px; border-radius: 10px; border: 1px solid #45475a; background: transparent; color: #a6adc8; font-size: 10px; cursor: pointer; font-family: inherit; transition: all 0.15s; }
.filter-btn.active { border-color: var(--c); color: var(--c); background: color-mix(in srgb, var(--c) 15%, transparent); }
.filter-btn:hover { border-color: #585b70; }

/* Node detail */
#detail { flex: 1; overflow-y: auto; padding: 16px; }
#detail::-webkit-scrollbar { width: 4px; }
#detail::-webkit-scrollbar-thumb { background: #45475a; border-radius: 2px; }
#detail-empty { color: #585b70; font-size: 12px; text-align: center; margin-top: 40px; }
.detail-header { font-size: 14px; font-weight: bold; margin-bottom: 8px; }
.detail-label { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; margin-bottom: 8px; }
.detail-section { margin-top: 12px; }
.detail-section h3 { font-size: 11px; color: #a6adc8; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
.detail-item { font-size: 12px; padding: 3px 0; color: #bac2de; cursor: pointer; }
.detail-item:hover { color: #89b4fa; }
.detail-field { font-size: 12px; color: #a6adc8; padding: 2px 0; }
.detail-field .val { color: #cdd6f4; }

/* Impact panel */
#impact-panel { border-top: 1px solid #313244; max-height: 200px; overflow-y: auto; padding: 12px 16px; }
#impact-panel h3 { font-size: 11px; color: #a6adc8; text-transform: uppercase; margin-bottom: 6px; }
.impact-item { font-size: 11px; padding: 2px 0; }
.risk-CRITICAL { color: #f38ba8; }
.risk-HIGH { color: #fab387; }
.risk-MEDIUM { color: #f9e2af; }
.risk-LOW { color: #a6e3a1; }

/* Bottom bar */
#bottombar { position: absolute; bottom: 16px; left: 50%; transform: translateX(-50%); display: flex; gap: 8px; background: #181825ee; border: 1px solid #313244; border-radius: 8px; padding: 6px 12px; font-size: 11px; color: #a6adc8; }
#bottombar kbd { background: #313244; padding: 1px 6px; border-radius: 3px; color: #cdd6f4; }
</style>
</head>
<body>
<div id="app">
  <div id="sidebar">
    <div id="header">
      <h1>vector-graph</h1>
      <div class="stats" id="stats"></div>
    </div>
    <div id="search-box"><input id="search" placeholder="Search nodes..." autocomplete="off"></div>
    <div id="filters"></div>
    <div id="detail"><div id="detail-empty">Click a node to inspect</div></div>
    <div id="impact-panel"><h3>Impact</h3><div id="impact-content" style="color:#585b70;font-size:11px">Select a node</div></div>
  </div>
  <div id="graph-container">
    <canvas id="canvas"></canvas>
    <div id="bottombar">
      <span><kbd>Scroll</kbd> zoom</span>
      <span><kbd>Drag</kbd> pan</span>
      <span><kbd>Click</kbd> inspect</span>
      <span><kbd>F</kbd> focus</span>
    </div>
  </div>
</div>
<script>
let DATA = {nodes: [], edges: []};

const COLORS = {
  File: '#585b70', Function: '#89b4fa', Class: '#cba6f7', Method: '#94e2d5',
  Variable: '#a6adc8', Module: '#fab387', ROS2Node: '#f38ba8', Topic: '#f9e2af',
  Service: '#a6e3a1', Action: '#f5c2e7', Parameter: '#89dceb',
  Community: '#b4befe', Process: '#f2cdcd'
};
const SIZES = { Class: 8, ROS2Node: 9, Function: 5, Method: 4, Topic: 6, Service: 6 };
const EDGE_COLORS = {
  CALLS: '#89b4fa44', IMPORTS: '#fab38744', HAS_METHOD: '#94e2d544',
  EXTENDS: '#cba6f744', PUBLISHES_TO: '#a6e3a166', SUBSCRIBES_TO: '#f9e2af66',
};

// --- State ---
let nodes = DATA.nodes;
let edges = DATA.edges;
let activeFilters = new Set(Object.keys(COLORS));
let selectedId = null;
let hoveredId = null;
let camera = { x: 0, y: 0, zoom: 1 };
let drag = { active: false, sx: 0, sy: 0, cx: 0, cy: 0 };
const positions = new Map();

// --- Layout: force-directed (simple) ---
function initPositions() {
  const n = nodes.length;
  nodes.forEach((nd, i) => {
    const angle = (i / n) * Math.PI * 2;
    const r = 200 + Math.random() * 300;
    positions.set(nd.id, { x: Math.cos(angle) * r, y: Math.sin(angle) * r, vx: 0, vy: 0 });
  });
}

function simulate(steps) {
  const nodeMap = new Map(nodes.map(n => [n.id, n]));
  for (let s = 0; s < steps; s++) {
    // Repulsion
    const pos = [...positions.entries()];
    for (let i = 0; i < pos.length; i++) {
      for (let j = i + 1; j < pos.length; j++) {
        const [, a] = pos[i], [, b] = pos[j];
        let dx = a.x - b.x, dy = a.y - b.y;
        let d2 = dx * dx + dy * dy + 1;
        let f = 800 / d2;
        a.vx += dx * f; a.vy += dy * f;
        b.vx -= dx * f; b.vy -= dy * f;
      }
    }
    // Attraction (edges)
    edges.forEach(e => {
      const a = positions.get(e.source), b = positions.get(e.target);
      if (!a || !b) return;
      let dx = b.x - a.x, dy = b.y - a.y;
      let d = Math.sqrt(dx * dx + dy * dy) + 0.1;
      let f = (d - 80) * 0.01;
      a.vx += dx * f; a.vy += dy * f;
      b.vx -= dx * f; b.vy -= dy * f;
    });
    // Damping + apply
    positions.forEach(p => {
      p.vx *= 0.85; p.vy *= 0.85;
      p.x += p.vx; p.y += p.vy;
    });
  }
}

// --- Canvas rendering ---
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');

function resize() {
  const r = canvas.parentElement.getBoundingClientRect();
  canvas.width = r.width * devicePixelRatio;
  canvas.height = r.height * devicePixelRatio;
  canvas.style.width = r.width + 'px';
  canvas.style.height = r.height + 'px';
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
}

function worldToScreen(wx, wy) {
  const cx = canvas.width / devicePixelRatio / 2;
  const cy = canvas.height / devicePixelRatio / 2;
  return { x: (wx - camera.x) * camera.zoom + cx, y: (wy - camera.y) * camera.zoom + cy };
}

function screenToWorld(sx, sy) {
  const cx = canvas.width / devicePixelRatio / 2;
  const cy = canvas.height / devicePixelRatio / 2;
  return { x: (sx - cx) / camera.zoom + camera.x, y: (sy - cy) / camera.zoom + camera.y };
}

function draw() {
  const w = canvas.width / devicePixelRatio, h = canvas.height / devicePixelRatio;
  ctx.clearRect(0, 0, w, h);

  const visibleNodes = new Set();
  nodes.forEach(nd => { if (activeFilters.has(nd.label)) visibleNodes.add(nd.id); });

  // Edges
  ctx.lineWidth = 0.5;
  edges.forEach(e => {
    if (!visibleNodes.has(e.source) || !visibleNodes.has(e.target)) return;
    const a = positions.get(e.source), b = positions.get(e.target);
    if (!a || !b) return;
    const sa = worldToScreen(a.x, a.y), sb = worldToScreen(b.x, b.y);
    ctx.strokeStyle = (selectedId && (e.source === selectedId || e.target === selectedId))
      ? (EDGE_COLORS[e.type] || '#585b70').replace('44','cc').replace('66','cc')
      : (EDGE_COLORS[e.type] || '#585b7033');
    ctx.beginPath(); ctx.moveTo(sa.x, sa.y); ctx.lineTo(sb.x, sb.y); ctx.stroke();
  });

  // Nodes
  nodes.forEach(nd => {
    if (!visibleNodes.has(nd.id)) return;
    const p = positions.get(nd.id);
    if (!p) return;
    const s = worldToScreen(p.x, p.y);
    const r = (SIZES[nd.label] || 4) * camera.zoom;
    const color = COLORS[nd.label] || '#cdd6f4';
    const isSelected = nd.id === selectedId;
    const isHovered = nd.id === hoveredId;

    ctx.beginPath();
    ctx.arc(s.x, s.y, r, 0, Math.PI * 2);
    ctx.fillStyle = isSelected ? '#f5e0dc' : color;
    ctx.fill();
    if (isSelected || isHovered) {
      ctx.strokeStyle = '#f5e0dc';
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    if (camera.zoom > 0.6 && r > 3) {
      ctx.fillStyle = '#cdd6f4';
      ctx.font = `${Math.max(8, 10 * camera.zoom)}px monospace`;
      ctx.textAlign = 'center';
      ctx.fillText(nd.name, s.x, s.y + r + 12);
    }
  });

  requestAnimationFrame(draw);
}

function hitTest(sx, sy) {
  const w = screenToWorld(sx, sy);
  let closest = null, minD = Infinity;
  nodes.forEach(nd => {
    if (!activeFilters.has(nd.label)) return;
    const p = positions.get(nd.id);
    if (!p) return;
    const d = Math.hypot(p.x - w.x, p.y - w.y);
    const r = (SIZES[nd.label] || 4) / camera.zoom + 5;
    if (d < r && d < minD) { minD = d; closest = nd; }
  });
  return closest;
}

// --- UI ---
function renderStats() {
  document.getElementById('stats').innerHTML =
    `<span>${nodes.length}</span> nodes &middot; <span>${edges.length}</span> edges`;
}

function renderFilters() {
  const el = document.getElementById('filters');
  const labels = [...new Set(nodes.map(n => n.label))].sort();
  el.innerHTML = labels.map(l => {
    const c = COLORS[l] || '#cdd6f4';
    const active = activeFilters.has(l) ? 'active' : '';
    return `<button class="filter-btn ${active}" style="--c:${c}" data-label="${l}">${l}</button>`;
  }).join('');
  el.querySelectorAll('.filter-btn').forEach(btn => {
    btn.onclick = () => {
      const l = btn.dataset.label;
      activeFilters.has(l) ? activeFilters.delete(l) : activeFilters.add(l);
      btn.classList.toggle('active');
    };
  });
}

function renderDetail(nd) {
  const el = document.getElementById('detail');
  if (!nd) { el.innerHTML = '<div id="detail-empty">Click a node to inspect</div>'; return; }

  const c = COLORS[nd.label] || '#cdd6f4';
  let html = `<div class="detail-header" style="color:${c}">${nd.name}</div>`;
  html += `<span class="detail-label" style="background:${c}22;color:${c}">${nd.label}</span>`;

  if (nd.file) html += `<div class="detail-field">File: <span class="val">${nd.file.split('/').pop()}</span></div>`;
  if (nd.line) html += `<div class="detail-field">Line: <span class="val">${nd.line}</span></div>`;
  if (nd.return_type) html += `<div class="detail-field">Returns: <span class="val">${nd.return_type}</span></div>`;
  if (nd.params) html += `<div class="detail-field">Params: <span class="val">${nd.params}</span></div>`;
  if (nd.bases) html += `<div class="detail-field">Bases: <span class="val">${nd.bases}</span></div>`;

  // Incoming edges
  const inEdges = edges.filter(e => e.target === nd.id);
  if (inEdges.length) {
    html += `<div class="detail-section"><h3>Called by (${inEdges.length})</h3>`;
    inEdges.slice(0, 15).forEach(e => {
      const src = nodes.find(n => n.id === e.source);
      if (src) html += `<div class="detail-item" data-id="${src.id}">${src.name} <span style="color:#585b70">${e.type}</span></div>`;
    });
    if (inEdges.length > 15) html += `<div style="color:#585b70;font-size:11px">+${inEdges.length-15} more</div>`;
    html += '</div>';
  }

  // Outgoing edges
  const outEdges = edges.filter(e => e.source === nd.id);
  if (outEdges.length) {
    html += `<div class="detail-section"><h3>Calls (${outEdges.length})</h3>`;
    outEdges.slice(0, 15).forEach(e => {
      const tgt = nodes.find(n => n.id === e.target);
      if (tgt) html += `<div class="detail-item" data-id="${tgt.id}">${tgt.name} <span style="color:#585b70">${e.type}</span></div>`;
    });
    if (outEdges.length > 15) html += `<div style="color:#585b70;font-size:11px">+${outEdges.length-15} more</div>`;
    html += '</div>';
  }

  el.innerHTML = html;
  el.querySelectorAll('.detail-item').forEach(item => {
    item.onclick = () => selectNode(item.dataset.id);
  });
}

function renderImpact(nd) {
  const el = document.getElementById('impact-content');
  if (!nd) { el.innerHTML = '<span style="color:#585b70">Select a node</span>'; return; }

  // BFS upstream depth 2
  const visited = new Set([nd.id]);
  let frontier = [nd.id];
  const levels = [];
  for (let d = 0; d < 2; d++) {
    const next = [];
    frontier.forEach(nid => {
      edges.forEach(e => {
        if (e.target === nid && !visited.has(e.source)) {
          visited.add(e.source);
          next.push({ id: e.source, depth: d + 1, type: e.type });
        }
      });
    });
    levels.push(...next);
    frontier = next.map(n => n.id);
  }

  if (!levels.length) { el.innerHTML = '<span style="color:#585b70">No upstream impact</span>'; return; }
  const risk = levels.filter(l => l.depth === 1).length >= 8 ? 'CRITICAL' :
               levels.filter(l => l.depth === 1).length >= 4 ? 'HIGH' :
               levels.length >= 3 ? 'MEDIUM' : 'LOW';
  let html = `<div class="impact-item risk-${risk}">Risk: ${risk} (${levels.length} affected)</div>`;
  levels.slice(0, 10).forEach(l => {
    const n = nodes.find(nd => nd.id === l.id);
    const cls = l.depth === 1 ? 'risk-HIGH' : 'risk-LOW';
    html += `<div class="impact-item ${cls}">d=${l.depth} ${n ? n.name : l.id}</div>`;
  });
  el.innerHTML = html;
}

function selectNode(id) {
  selectedId = id;
  const nd = nodes.find(n => n.id === id);
  renderDetail(nd);
  renderImpact(nd);
  if (nd) {
    const p = positions.get(nd.id);
    if (p) { camera.x = p.x; camera.y = p.y; }
  }
}

// --- Events ---
canvas.addEventListener('wheel', e => {
  e.preventDefault();
  const factor = e.deltaY > 0 ? 0.9 : 1.1;
  camera.zoom = Math.max(0.05, Math.min(10, camera.zoom * factor));
}, { passive: false });

canvas.addEventListener('mousedown', e => {
  drag.active = true;
  drag.sx = e.clientX; drag.sy = e.clientY;
  drag.cx = camera.x; drag.cy = camera.y;
});
canvas.addEventListener('mousemove', e => {
  if (drag.active) {
    camera.x = drag.cx - (e.clientX - drag.sx) / camera.zoom;
    camera.y = drag.cy - (e.clientY - drag.sy) / camera.zoom;
  }
  const rect = canvas.getBoundingClientRect();
  const nd = hitTest(e.clientX - rect.left, e.clientY - rect.top);
  hoveredId = nd ? nd.id : null;
  canvas.style.cursor = hoveredId ? 'pointer' : 'grab';
});
canvas.addEventListener('mouseup', e => {
  if (drag.active && Math.abs(e.clientX - drag.sx) < 3 && Math.abs(e.clientY - drag.sy) < 3) {
    const rect = canvas.getBoundingClientRect();
    const nd = hitTest(e.clientX - rect.left, e.clientY - rect.top);
    selectNode(nd ? nd.id : null);
  }
  drag.active = false;
});

document.getElementById('search').addEventListener('input', e => {
  const q = e.target.value.toLowerCase();
  if (!q) return;
  const match = nodes.find(n => n.name.toLowerCase().includes(q));
  if (match) {
    selectNode(match.id);
  }
});

document.addEventListener('keydown', e => {
  if (e.key === 'f' && selectedId) {
    const p = positions.get(selectedId);
    if (p) { camera.x = p.x; camera.y = p.y; camera.zoom = 2; }
  }
});

// --- Loading screen ---
function drawLoading() {
  resize();
  const w = canvas.width / devicePixelRatio, h = canvas.height / devicePixelRatio;
  ctx.fillStyle = '#1e1e2e';
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = '#89b4fa';
  ctx.font = '16px monospace';
  ctx.textAlign = 'center';
  ctx.fillText('Loading graph data...', w / 2, h / 2);
}

// --- Init ---
window.addEventListener('resize', resize);
resize();
drawLoading();

fetch('/api/data').then(r => {
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}).then(d => {
  DATA = d;
  nodes = DATA.nodes;
  edges = DATA.edges;
  console.log('Loaded', nodes.length, 'nodes', edges.length, 'edges');
  initPositions();
  simulate(200);
  // Center camera on graph centroid
  let cx = 0, cy = 0;
  positions.forEach(p => { cx += p.x; cy += p.y; });
  if (positions.size > 0) { camera.x = cx / positions.size; camera.y = cy / positions.size; }
  camera.zoom = 0.5;
  renderStats();
  renderFilters();
  draw();
  document.getElementById('detail-empty').textContent = 'Click a node to inspect';
}).catch(err => {
  console.error('Failed to load:', err);
  const w = canvas.width / devicePixelRatio, h = canvas.height / devicePixelRatio;
  ctx.fillStyle = '#1e1e2e';
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = '#f38ba8';
  ctx.font = '14px monospace';
  ctx.textAlign = 'center';
  ctx.fillText('Failed to load: ' + err.message, w / 2, h / 2);
});
</script>
</body>
</html>"""


def _graph_to_json(graph: KnowledgeGraph, max_nodes: int = 600) -> dict[str, Any]:
    """Convert KnowledgeGraph to JSON for the web frontend."""
    from vector_graph._types import NodeLabel

    skip_labels = {NodeLabel.FILE, NodeLabel.FOLDER}
    node_list = []
    node_ids: set[str] = set()

    for node in graph.iter_nodes():
        if node.label in skip_labels:
            continue
        if len(node_list) >= max_nodes:
            break
        entry: dict[str, Any] = {
            "id": node.id,
            "name": node.properties.name,
            "label": node.label.value,
        }
        if node.properties.file_path:
            entry["file"] = node.properties.file_path
        if node.properties.start_line:
            entry["line"] = node.properties.start_line
        if node.properties.return_type:
            entry["return_type"] = node.properties.return_type
        if node.properties.parameters:
            entry["params"] = ", ".join(node.properties.parameters)
        if node.properties.bases:
            entry["bases"] = ", ".join(node.properties.bases)
        node_list.append(entry)
        node_ids.add(node.id)

    edge_list = []
    for edge in graph.iter_edges():
        if edge.source_id in node_ids and edge.target_id in node_ids:
            edge_list.append({
                "source": edge.source_id,
                "target": edge.target_id,
                "type": edge.edge_type.value,
            })

    return {"nodes": node_list, "edges": edge_list}


def serve(
    graph: KnowledgeGraph,
    host: str = "127.0.0.1",
    port: int = 5555,
    max_nodes: int = 600,
) -> None:
    """Start a local HTTP server serving the interactive graph visualization."""
    import http.server
    import threading

    data = _graph_to_json(graph, max_nodes=max_nodes)
    data_json = json.dumps(data)
    html = _HTML_TEMPLATE

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/" or self.path == "/index.html":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode())
            elif self.path == "/api/data":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data_json.encode())
            else:
                self.send_error(404)

        def log_message(self, format: str, *args: Any) -> None:
            pass  # Suppress access logs

    server = http.server.HTTPServer((host, port), Handler)
    print(f"vector-graph server running at http://{host}:{port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        print("\nStopped.")
