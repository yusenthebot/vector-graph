// ── panels.js — Changes panel, resize, legend, minimap, startup ──
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
        html += '<div style="font-size:10px;padding:1px 0;cursor:pointer;color:var(--subtext)" onclick="previewNode(\'' + dep.id + '\')">';
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
        html += '<div style="font-size:10px;padding:1px 0;cursor:pointer;color:var(--subtext)" onclick="previewNode(\'' + dep.id + '\')">';
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

// ── Resizable panels ───────────────────────────────────────
function initResize() {
  const sidebar = document.getElementById('sidebar');
  const inspector = document.getElementById('inspector');
  const sidebarHandle = document.getElementById('sidebar-resize');
  const inspectorHandle = document.getElementById('inspector-resize');

  // Restore saved widths
  const savedSidebar = localStorage.getItem('vg-sidebar-width');
  const savedInspector = localStorage.getItem('vg-inspector-width');
  if (savedSidebar) sidebar.style.width = savedSidebar + 'px';
  if (savedInspector) inspector.style.width = savedInspector + 'px';

  function makeDraggable(handle, panel, side, min, max) {
    let startX, startW;
    handle.addEventListener('pointerdown', function(e) {
      e.preventDefault();
      startX = e.clientX;
      startW = panel.getBoundingClientRect().width;
      handle.classList.add('active');
      handle.setPointerCapture(e.pointerId);

      function onMove(e) {
        const dx = e.clientX - startX;
        const newW = Math.min(max, Math.max(min, side === 'left' ? startW + dx : startW - dx));
        panel.style.width = newW + 'px';
        panel.style.minWidth = newW + 'px';
        if (graph3d) graph3d.width(document.getElementById('graph-container').clientWidth);
      }
      function onUp(e) {
        handle.classList.remove('active');
        handle.releasePointerCapture(e.pointerId);
        handle.removeEventListener('pointermove', onMove);
        handle.removeEventListener('pointerup', onUp);
        const w = panel.getBoundingClientRect().width;
        localStorage.setItem(side === 'left' ? 'vg-sidebar-width' : 'vg-inspector-width', Math.round(w));
        if (graph3d) graph3d.width(document.getElementById('graph-container').clientWidth);
        // Resize 2D impact graph if present
        if (impactGraph2d) {
          const ic = document.getElementById('impact-graph-container');
          if (ic) impactGraph2d.width(ic.clientWidth);
        }
      }
      handle.addEventListener('pointermove', onMove);
      handle.addEventListener('pointerup', onUp);
    });
  }

  makeDraggable(sidebarHandle, sidebar, 'left', 200, 500);
  makeDraggable(inspectorHandle, inspector, 'right', 280, 600);
}

// Initialize resize after DOM ready
initResize();
if (sidebarCollapsed) {
  document.getElementById('sidebar').classList.add('collapsed');
  document.getElementById('sidebar-resize').classList.add('hidden');
}

// ── Legend ──────────────────────────────────────────────────
function buildLegend() {
  var body = document.getElementById('legend-body');
  if (!body) return;
  // Shape unicode icons per type
  var shapes = {
    File:'\u2B21', Class:'\u25A0', Function:'\u25CF', Method:'\u25C6',
    Variable:'\u25B2', Decorator:'\u25CB', Module:'\u2B22',
    ROS2Node:'\u2B53', Topic:'\u25BC', Service:'\u25AF', Action:'\u2B24', Parameter:'\u2022'
  };
  // Only show types present in current data
  var visibleTypes = new Set(allNodes.map(function(n) { return n.label; }));
  var html = '';
  Object.keys(COLORS).forEach(function(type) {
    if (!visibleTypes.has(type)) return;
    var shape = shapes[type] || '\u25CF';
    html += '<div class="legend-row">';
    html += '<span class="legend-dot" style="background:' + COLORS[type] + '"></span>';
    html += '<span class="legend-shape">' + shape + '</span>';
    html += '<span>' + type + '</span>';
    html += '</div>';
  });
  body.innerHTML = html;
}

// ── Minimap ─────────────────────────────────────────────────
var _minimapLast = 0;
function updateMinimap() {
  var now = performance.now();
  if (now - _minimapLast < 200) return; // 5fps throttle
  _minimapLast = now;
  var canvas = document.getElementById('minimap');
  if (!canvas || !graph3d) return;
  var ctx = canvas.getContext('2d');
  var w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  var nodes = graph3d.graphData().nodes;
  if (!nodes.length) return;

  // Compute bounding box (XZ plane)
  var minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
  nodes.forEach(function(n) {
    var x = n.x || 0, z = n.z || 0;
    if (x < minX) minX = x; if (x > maxX) maxX = x;
    if (z < minZ) minZ = z; if (z > maxZ) maxZ = z;
  });
  var rangeX = (maxX - minX) || 1, rangeZ = (maxZ - minZ) || 1;
  var pad = 10;

  // Draw nodes as dots
  nodes.forEach(function(n) {
    var px = pad + ((n.x || 0) - minX) / rangeX * (w - pad * 2);
    var py = pad + ((n.z || 0) - minZ) / rangeZ * (h - pad * 2);
    ctx.fillStyle = GROUP_COLORS[n.group] || COLORS[n.label] || '#585b70';
    ctx.globalAlpha = 0.7;
    ctx.beginPath();
    ctx.arc(px, py, 1.5, 0, Math.PI * 2);
    ctx.fill();
  });

  // Draw viewport rectangle approximation
  try {
    var cam = graph3d.camera();
    var cx = pad + (cam.position.x - minX) / rangeX * (w - pad * 2);
    var cz = pad + (cam.position.z - minZ) / rangeZ * (h - pad * 2);
    ctx.globalAlpha = 0.6;
    ctx.strokeStyle = '#cdd6f4';
    ctx.lineWidth = 1;
    var dist = Math.sqrt(cam.position.x * cam.position.x + cam.position.y * cam.position.y + cam.position.z * cam.position.z) || 200;
    var vSize = Math.min(Math.max(dist * 0.1, 10), 40);
    ctx.strokeRect(cx - vSize / 2, cz - vSize / 2, vSize, vSize);
  } catch (e) {}
  ctx.globalAlpha = 1;
}

// Minimap click — fly camera to world position
document.addEventListener('DOMContentLoaded', function() {
  var canvas = document.getElementById('minimap');
  if (!canvas) return;
  canvas.addEventListener('click', function(e) {
    if (!graph3d) return;
    var rect = canvas.getBoundingClientRect();
    var mx = e.clientX - rect.left, my = e.clientY - rect.top;
    var w = canvas.width, h = canvas.height, pad = 10;

    var nodes = graph3d.graphData().nodes;
    if (!nodes.length) return;
    var minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
    nodes.forEach(function(n) {
      if (n.x < minX) minX = n.x; if (n.x > maxX) maxX = n.x;
      if (n.z < minZ) minZ = n.z; if (n.z > maxZ) maxZ = n.z;
    });
    var rangeX = (maxX - minX) || 1, rangeZ = (maxZ - minZ) || 1;

    var worldX = minX + (mx - pad) / (w - pad * 2) * rangeX;
    var worldZ = minZ + (my - pad) / (h - pad * 2) * rangeZ;
    var cam = graph3d.camera();
    graph3d.cameraPosition(
      {x: worldX + 80, y: cam.position.y, z: worldZ + 80},
      {x: worldX, y: 0, z: worldZ},
      1000
    );
  });
});

// Minimap render loop (throttled to 5fps via _minimapLast guard)
(function minimapLoop() {
  updateMinimap();
  requestAnimationFrame(minimapLoop);
})();

// ── Start ───────────────────────────────────────────────────
// Request notification permission on load
if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
  Notification.requestPermission();
}
loadData();
