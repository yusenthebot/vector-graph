// ── selection.js — Node selection, preview, inspector panel ──

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
  refreshNodeAppearance();
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
  // F5: Selection glow halo
  addSelectionGlow(id);
  // F8: Constellation expand — briefly push 1-hop neighbors outward
  if (graph3d && highlightNodes.size > 0) {
    var selNodePos = graph3d.graphData().nodes.find(function(n) { return n.id === id; });
    if (selNodePos) {
      var cx = selNodePos.x || 0, cy = selNodePos.y || 0, cz = selNodePos.z || 0;
      var neighborSet = new Set(highlightNodes);
      graph3d.d3Force('constellation', function(alpha) {
        graph3d.graphData().nodes.forEach(function(n) {
          if (!neighborSet.has(n.id)) return;
          var dx = (n.x || 0) - cx, dy = (n.y || 0) - cy, dz = (n.z || 0) - cz;
          var dist = Math.sqrt(dx*dx + dy*dy + dz*dz) || 1;
          var push = alpha * 40 / dist;
          n.vx = (n.vx || 0) + dx * push;
          n.vy = (n.vy || 0) + dy * push;
          n.vz = (n.vz || 0) + dz * push;
        });
      });
      // Restart simulation briefly
      graph3d.d3ReheatSimulation();
      // Remove force after 1.5s — clear any pending timeout to avoid conflicts on rapid re-selection
      if (_constellationTimeout) clearTimeout(_constellationTimeout);
      _constellationTimeout = setTimeout(function() {
        if (graph3d) graph3d.d3Force('constellation', null);
        _constellationTimeout = null;
      }, 1500);
    }
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
  updateStatusBar();
}

function toggleSidebar() {
  sidebarCollapsed = !sidebarCollapsed;
  document.getElementById('sidebar').classList.toggle('collapsed', sidebarCollapsed);
  document.getElementById('sidebar-resize').classList.toggle('hidden', sidebarCollapsed);
  localStorage.setItem('vg-sidebar-collapsed', sidebarCollapsed);
  setTimeout(function() { if (graph3d) graph3d.width(document.getElementById('graph-container').clientWidth); }, 50);
}

function toggleInspector() {
  var inspector = document.getElementById('inspector');
  if (!inspector.classList.contains('open')) return;
  inspector.classList.toggle('collapsed');
  document.getElementById('inspector-resize').classList.toggle('hidden');
  setTimeout(function() { if (graph3d) graph3d.width(document.getElementById('graph-container').clientWidth); }, 50);
}

function deselectNode() {
  document.getElementById('inspector').classList.remove('collapsed');
  document.getElementById('inspector-resize').classList.remove('hidden');
  selectedId = null;
  removeSelectionGlow();
  if (graph3d) graph3d.d3Force('constellation', null);
  depthFilter = 0;
  highlightNodes.clear();
  highlightLinks.clear();
  document.getElementById('inspector').classList.remove('open');
  setTimeout(function() { if (graph3d) graph3d.width(document.getElementById('graph-container').clientWidth); }, 100);
  refreshNodeAppearance();
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
  updateStatusBar();
}

// ── Preview (fly to node without clearing change context) ──

function previewNode(id) {
  const node = graph3d.graphData().nodes.find(n => n.id === id);
  if (!node) return;
  const dist = 80;
  graph3d.cameraPosition(
    {x: node.x + dist, y: node.y + dist/2, z: node.z + dist},
    {x: node.x, y: node.y, z: node.z},
    1000
  );
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
