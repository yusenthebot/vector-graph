// ── sidebar.js — Sidebar tabs, file explorer, filters, status bar ──
// ── Sidebar tabs ────────────────────────────────────────────
function switchTab(tab) {
  document.querySelectorAll('.sidebar-tab').forEach(function(t) { t.classList.remove('active'); });
  document.querySelectorAll('.sidebar-panel').forEach(function(p) { p.classList.remove('active'); });
  var tabEl = document.querySelector('.sidebar-tab[onclick*="' + tab + '"]');
  var panelEl = document.getElementById('panel-' + tab);
  if (tabEl) tabEl.classList.add('active');
  if (panelEl) panelEl.classList.add('active');
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

  // Tooltip descriptions for node types
  const _nodeDesc = {
    File: 'Python source file — one node per .py file in the project',
    Function: 'Standalone function defined at module level (def foo)',
    Class: 'Class definition (class Foo). Contains methods as children',
    Method: 'Method defined inside a class (class.method)',
    Variable: 'Module-level variable or constant assignment',
    Property: 'Class property defined with @property decorator',
    Decorator: 'Decorator function used with @ syntax',
    Module: 'Python module (directory with __init__.py)',
    ROS2Node: 'ROS2 node discovered in rclpy.create_node() calls',
    Topic: 'ROS2 topic used in publish/subscribe',
    Service: 'ROS2 service endpoint',
    Action: 'ROS2 action server/client',
    Parameter: 'ROS2 parameter declared on a node',
  };
  const _edgeDesc = {
    CALLS: 'Function/method calls another function/method',
    IMPORTS: 'File imports from another file (import / from...import)',
    HAS_METHOD: 'Class contains this method',
    EXTENDS: 'Class inherits from another class (subclass)',
    IMPLEMENTS: 'Class implements a protocol/interface',
    CONTAINS: 'File contains this symbol (structural parent)',
    DEFINES: 'Module defines this symbol',
    DECORATES: 'Decorator is applied to this function/class',
    HAS_PROPERTY: 'Class has this @property',
    PUBLISHES_TO: 'ROS2 node publishes to this topic',
    SUBSCRIBES_TO: 'ROS2 node subscribes to this topic',
    PROVIDES_SERVICE: 'ROS2 node provides this service',
    CALLS_SERVICE: 'ROS2 node calls this service',
    PROVIDES_ACTION: 'ROS2 node provides this action',
    CALLS_ACTION: 'ROS2 node calls this action',
    USES_PARAMETER: 'ROS2 node declares/uses this parameter',
    STEP_IN_PROCESS: 'Step in an execution flow trace',
    MEMBER_OF: 'Member of a community/cluster',
  };

  // Node type groups
  for (const [group, labels] of Object.entries(GROUPS)) {
    const present = labels.filter(l => counts[l]);
    if (!present.length) continue;
    html += `<div class="filter-group"><h3>${group}</h3>`;
    present.forEach(l => {
      const on = enabledLabels.has(l);
      const tip = _nodeDesc[l] || l;
      html += `<div class="ftoggle ${on?'':'off'}" data-label="${l}" onclick="toggleLabel('${l}')" title="${tip} — click to toggle visibility">
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
      const tip = _edgeDesc[e] || e;
      html += `<div class="ftoggle ${on?'':'off'}" data-edge="${e}" onclick="toggleEdge('${e}')" title="${tip} — click to toggle visibility">
        <span class="fdot" style="background:${EDGE_COLORS[e]}"></span>${e}<span class="fcount">${edgeCounts[e]}</span></div>`;
    });
    html += '</div>';
  }

  // Depth filter
  html += `<div class="filter-group"><h3 title="Select a node first, then use depth to show only nodes within N hops">Depth (select node first)</h3><div class="depth-bar" id="depth-bar">
    <button class="depth-btn active" onclick="setDepth(0)" title="Show all nodes (no depth limit)">All</button>
    <button class="depth-btn" onclick="setDepth(1)" title="Show only direct neighbors (1 hop)">1</button>
    <button class="depth-btn" onclick="setDepth(2)" title="Show nodes within 2 hops">2</button>
    <button class="depth-btn" onclick="setDepth(3)" title="Show nodes within 3 hops">3</button>
  </div></div>`;

  // Health mode toggle
  html += `<div class="filter-group"><h3>Node Color Mode</h3>
    <div class="ftoggle" id="health-toggle" onclick="toggleHealthMode()" style="cursor:pointer" title="Toggle between type-based colors and complexity-based health gradient (green=simple, red=complex)">
      <span class="fdot" style="background:var(--green)"></span>
      <span id="health-toggle-label">Label colors</span>
      <span class="fcount" style="font-size:9px">click to toggle</span>
    </div>
    <div style="font-size:10px;color:var(--overlay0);margin-top:4px" title="McCabe cyclomatic complexity: LOW (cc<=5), MEDIUM (5-10), HIGH (10-20), CRITICAL (>20)">
      <span style="color:#a6e3a1">&#9679;</span> LOW &nbsp;
      <span style="color:#f9e2af">&#9679;</span> MEDIUM &nbsp;
      <span style="color:#fab387">&#9679;</span> HIGH &nbsp;
      <span style="color:#f38ba8">&#9679;</span> CRITICAL
    </div>
  </div>`;

  // Hotspot mode toggle
  html += `<div class="filter-group"><h3>Git Hotspots</h3>
    <div class="ftoggle" id="hotspot-toggle" onclick="toggleHotspotMode()" style="cursor:pointer" title="Color nodes by git change frequency — blue (stable) to red (volatile). Requires git repository.">
      <span class="fdot" style="background:var(--peach)"></span>
      <span id="hotspot-toggle-label">Off</span>
      <span class="fcount" style="font-size:9px">click to toggle</span>
    </div>
    <div style="font-size:10px;color:var(--overlay0);margin-top:4px" title="Based on git log change frequency × code complexity over last 90 days">
      <span style="color:#89b4fa">&#9679;</span> Stable &nbsp;
      <span style="color:#f9e2af">&#9679;</span> Some &nbsp;
      <span style="color:#fab387">&#9679;</span> Volatile &nbsp;
      <span style="color:#f38ba8">&#9679;</span> Hot
    </div>
  </div>`;

  // Shape legend
  html += `<div class="filter-group"><h3>Node Shapes</h3><div class="shape-legend">
    <div class="shape-legend-item"><span class="shape-legend-icon">&#11044;</span> Function (sphere)</div>
    <div class="shape-legend-item"><span class="shape-legend-icon">&#9632;</span> Class (cube)</div>
    <div class="shape-legend-item"><span class="shape-legend-icon">&#9670;</span> Method (diamond)</div>
    <div class="shape-legend-item"><span class="shape-legend-icon">&#9648;</span> File (hex disc)</div>
    <div class="shape-legend-item"><span class="shape-legend-icon">&#9650;</span> Variable (pyramid)</div>
    <div class="shape-legend-item"><span class="shape-legend-icon">&#9675;</span> Decorator (ring)</div>
    <div class="shape-legend-item"><span class="shape-legend-icon">&#11200;</span> ROS2Node (icosahedron)</div>
    <div class="shape-legend-item"><span class="shape-legend-icon">&#9651;</span> Topic (cone)</div>
  </div></div>`;

  el.innerHTML = html;
}

function toggleHealthMode() {
  healthMode = !healthMode;
  if (healthMode) hotspotMode = false;
  // update hotspot toggle UI
  const hsLabel = document.getElementById('hotspot-toggle-label');
  if (hsLabel) hsLabel.textContent = hotspotMode ? 'On' : 'Off';
  const hsDot = document.querySelector('#hotspot-toggle .fdot');
  if (hsDot) hsDot.style.background = hotspotMode ? '#f38ba8' : 'var(--peach)';
  const label = document.getElementById('health-toggle-label');
  if (label) label.textContent = healthMode ? 'Health gradient' : 'Label colors';
  const dot = document.querySelector('#health-toggle .fdot');
  if (dot) dot.style.background = healthMode ? '#f38ba8' : 'var(--green)';
  refreshNodeAppearance();
}

function toggleHotspotMode() {
  hotspotMode = !hotspotMode;
  if (hotspotMode) healthMode = false; // mutually exclusive
  const label = document.getElementById('hotspot-toggle-label');
  if (label) label.textContent = hotspotMode ? 'On' : 'Off';
  const dot = document.querySelector('#hotspot-toggle .fdot');
  if (dot) dot.style.background = hotspotMode ? '#f38ba8' : 'var(--peach)';
  // Also update health toggle state
  const hLabel = document.getElementById('health-toggle-label');
  if (hLabel) hLabel.textContent = healthMode ? 'Health gradient' : 'Label colors';
  refreshNodeAppearance();
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

function updateStatusBar() {
  const {nodes: fn, links: fl} = getFilteredData();
  const gc = new Set(allNodes.map(n => n.group)).size;
  const modeEl = document.getElementById('sb-mode');
  if (modeEl) {
    const names = {architecture: 'ARCH', logic: 'LOGIC', deep: 'DEEP'};
    const colors = {architecture: 'var(--green)', logic: 'var(--blue)', deep: 'var(--mauve)'};
    const col = colors[currentMode] || 'var(--blue)';
    modeEl.textContent = names[currentMode] || currentMode;
    modeEl.style.cssText = 'padding:1px 8px;border-radius:2px;font-weight:bold;font-size:9px;text-transform:uppercase;letter-spacing:0.5px;margin-right:8px;'
      + 'color:' + col + ';'
      + 'background:color-mix(in srgb,' + col + ' 15%,transparent)';
  }
  const statsEl = document.getElementById('sb-stats');
  if (statsEl) statsEl.innerHTML = '<span>' + fn.length + '</span> nodes  <span>' + fl.length + '</span> edges  <span>' + gc + '</span> groups';
  const hintsEl = document.getElementById('sb-hints');
  if (hintsEl) {
    if (selectedId) {
      hintsEl.innerHTML = '<kbd>Esc</kbd> back  <kbd>d</kbd> depth  <kbd>h</kbd> health';
    } else if (changeHighlightActive) {
      hintsEl.innerHTML = '<kbd>Esc</kbd> clear';
    } else {
      hintsEl.innerHTML = '<kbd>Ctrl+K</kbd> search  <kbd>1/2/3</kbd> mode  <kbd>Ctrl+B</kbd> sidebar  <kbd>?</kbd> help';
    }
  }
}
