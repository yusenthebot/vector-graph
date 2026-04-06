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
// Hide structural edges by default — they clutter the graph without showing code flow
const _STRUCTURAL_EDGES = new Set(['CONTAINS','HAS_METHOD','DEFINES','HAS_PROPERTY']);
let enabledEdges = new Set(Object.keys(EDGE_COLORS).filter(e => !_STRUCTURAL_EDGES.has(e)));
let selectedId = null;
let highlightNodes = new Set();
let highlightLinks = new Set();
let depthFilter = 0; // 0 = all
let graph3d = null;
let linkIndex = {from: {}, to: {}}; // pre-built for O(1) lookups
let GROUP_COLORS = {}; // populated in loadData after nodes arrive
let nebulaGroup = null;
let healthMode = false; // OFF by default — show per-type label colors

let currentMode = localStorage.getItem('vg-mode') || 'logic';
let sessionChangeCount = {};  // symbol name -> change count this session
let changeViewMode = 'summary'; // 'summary' or 'detail'
let modeCache = {}; // {architecture: {nodes, links}, logic: {nodes, links}, deep: {nodes, links}}

// ── Shared geometries (one per node type, reused across all nodes) ──
const _GEO = {};
function _initGeo() {
  _GEO.File      = new THREE.CylinderGeometry(1, 1, 0.3, 6);     // flat hex disc
  _GEO.Class     = new THREE.BoxGeometry(1.4, 1.4, 1.4);          // cube
  _GEO.Function  = new THREE.SphereGeometry(1, 16, 12);            // sphere
  _GEO.Method    = new THREE.OctahedronGeometry(1);                 // diamond
  _GEO.Variable  = new THREE.TetrahedronGeometry(0.7);              // small pyramid
  _GEO.Property  = new THREE.BoxGeometry(0.7, 0.7, 0.7);           // small cube
  _GEO.Decorator = new THREE.TorusGeometry(0.7, 0.2, 8, 16);       // ring
  _GEO.Module    = new THREE.CylinderGeometry(1, 1, 0.4, 8);       // disc
  _GEO.ROS2Node  = new THREE.IcosahedronGeometry(1.2);              // icosahedron
  _GEO.Topic     = new THREE.ConeGeometry(0.8, 1.4, 6);            // cone
  _GEO.Service   = new THREE.CylinderGeometry(0.5, 0.5, 1.2, 8);   // cylinder
  _GEO.Action    = new THREE.DodecahedronGeometry(1);               // dodecahedron
  _GEO.Parameter = new THREE.SphereGeometry(0.6, 8, 6);             // small sphere
  _GEO._default  = new THREE.SphereGeometry(1, 12, 8);
}

// ── Extracted node color logic (standalone for nodeThreeObject + refreshNodeAppearance) ──
function getNodeColor(n) {
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
    const gc = GROUP_COLORS[n.group] || '#45475a';
    if (gc.startsWith('hsl')) {
      return gc.replace(/\d+%\)$/, '25%)');
    }
    return '#1a1a2e';
  }
  // 3. Cumulative heat (session-level, always shown)
  const heat = cumulativeHeat[n.id] || 0;
  if (heat > 0) {
    if (heat >= 4) return '#f38ba8';
    if (heat >= 2) return '#fab387';
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
}

// ── Extracted node size logic ──
function getNodeSize(n) {
  if (selectedId && n.id !== selectedId && !highlightNodes.has(n.id)) return 0.3;
  if (changeHighlightActive) {
    if (activeChangeIds.has(n.id)) return 8;
    if (activeImpactIds.has(n.id)) return 5;
    return SIZES[n.label] || 2;
  }
  const base = SIZES[n.label] || 2;
  if (n.complexity) return base + Math.min(n.complexity * 0.3, 5);
  return base;
}

// ── Refresh node appearance in-place (replaces nodeColor/nodeVal re-trigger) ──
function refreshNodeAppearance() {
  if (!graph3d) return;
  graph3d.graphData().nodes.forEach(n => {
    const obj = n.__threeObj;
    if (obj && obj.material) {
      obj.material.color.set(getNodeColor(n));
      const s = getNodeSize(n) * 0.8;
      obj.scale.set(s, s, s);
    }
  });
}

// ── Change tracking state (Live Radar) ──
let activeChangeIds = new Set();    // nodes directly changed (persistent until next change)
let activeImpactIds = new Set();    // impact chain nodes (depth 1-2 callers)
let cumulativeHeat = {};            // nodeId -> change count this session
let changeHighlightActive = false;  // true when showing change overlay

// ── Data loading ────────────────────────────────────────────
async function loadData() {
  // Pre-cache all 3 modes in parallel for instant switching
  const [archR, logicR, deepR] = await Promise.all([
    fetch('/api/data?mode=architecture').then(r => r.json()),
    fetch('/api/data?mode=logic').then(r => r.json()),
    fetch('/api/data?mode=deep').then(r => r.json()),
  ]);
  modeCache = {architecture: archR, logic: logicR, deep: deepR};

  const d = modeCache[currentMode];
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
  // Initialize shared geometries (requires THREE to be loaded)
  _initGeo();
  initGraph();
  // Sync button active states to currentMode (covers localStorage-restored mode)
  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === currentMode);
  });
  buildFilters();
  buildExplorer();
  buildGroupsPanel();
  updateChangesPanel();
  updateStats();
}

// ── Mode switching (instant — uses pre-cached data, no destroy/recreate) ──
function switchMode(mode) {
  if (mode === currentMode) return;
  currentMode = mode;
  localStorage.setItem('vg-mode', mode);
  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === mode);
  });

  // Use cached data (no network request)
  const d = modeCache[mode];
  if (!d) return;
  allNodes = d.nodes;
  allLinks = d.links;

  // Rebuild link index
  linkIndex = {from: {}, to: {}};
  allLinks.forEach(l => {
    const sid = typeof l.source === 'object' ? l.source.id : l.source;
    const tid = typeof l.target === 'object' ? l.target.id : l.target;
    (linkIndex.from[sid] = linkIndex.from[sid] || []).push(l);
    (linkIndex.to[tid] = linkIndex.to[tid] || []).push(l);
  });

  // Regenerate group colors
  const groupNames = [...new Set(allNodes.map(n => n.group))].sort();
  GROUP_COLORS = {};
  groupNames.forEach((g, i) => {
    const hue = (i * 137.508) % 360;
    GROUP_COLORS[g] = 'hsl(' + hue + ', 80%, 58%)';
  });

  // Clear state
  selectedId = null;
  highlightNodes.clear();
  highlightLinks.clear();
  changeHighlightActive = false;
  activeChangeIds.clear();
  activeImpactIds.clear();
  if (nebulaGroup && graph3d) {
    const scene = graph3d.scene();
    if (scene) scene.remove(nebulaGroup);
    nebulaGroup = null;
  }

  // Swap data in-place (no destroy/recreate)
  const {nodes, links} = getFilteredData();
  _seedGroupPositions(nodes);
  graph3d.graphData({nodes, links});

  // Rebuild nebulae after simulation settles
  setTimeout(() => { if (graph3d) updateNebulae(); }, 2500);

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
    // Custom per-type 3D shapes via nodeThreeObject
    .nodeThreeObject(n => {
      const geo = _GEO[n.label] || _GEO._default;
      const color = getNodeColor(n);
      const size = getNodeSize(n);
      const mat = new THREE.MeshLambertMaterial({color, transparent: true, opacity: 0.9});
      const mesh = new THREE.Mesh(geo, mat);
      mesh.scale.setScalar(size * 0.8);
      return mesh;
    })
    .nodeThreeObjectExtend(false)
    // nodeVal kept for force simulation radius (doesn't affect rendering with custom objects)
    .nodeVal(n => getNodeSize(n))
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
      // Change highlight — only bright for edges directly touching a changed node
      if (changeHighlightActive) {
        const srcChanged = activeChangeIds.has(sid);
        const tgtChanged = activeChangeIds.has(tid);
        // Direct edges from/to changed nodes: bright
        if (srcChanged || tgtChanged) return '#fab387';
        // Impact chain edges (both ends in impact set): faint
        if (activeImpactIds.has(sid) && activeImpactIds.has(tid)) return '#fab38733';
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
        const srcChanged = activeChangeIds.has(sid);
        const tgtChanged = activeChangeIds.has(tid);
        // Direct: bright. Impact chain: subtle. Rest: hidden
        if (srcChanged || tgtChanged) return 0.7;
        if (activeImpactIds.has(sid) && activeImpactIds.has(tid)) return 0.1;
        return 0.0;
      }
      // Default: edges barely visible — graph shows structure via node positions
      // CALLS slightly more visible than others
      if (l.type === 'CALLS') return 0.04;
      if (l.type === 'IMPORTS') return 0.03;
      return 0.02;
    })
    .linkWidth(l => {
      const sid = typeof l.source === 'object' ? l.source.id : l.source;
      const tid = typeof l.target === 'object' ? l.target.id : l.target;
      if (selectedId) {
        return (sid === selectedId || tid === selectedId) ? 2.0 : 0.0;
      }
      if (changeHighlightActive) {
        const srcChanged = activeChangeIds.has(sid);
        const tgtChanged = activeChangeIds.has(tid);
        if (srcChanged || tgtChanged) return 2.0;
        if (activeImpactIds.has(sid) && activeImpactIds.has(tid)) return 0.3;
        return 0.0;
      }
      // CALLS thicker than structural edges
      if (l.type === 'CALLS') return 0.3;
      if (l.type === 'IMPORTS' || l.type === 'EXTENDS') return 0.2;
      return 0.1;
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

  // Add lights for MeshLambertMaterial visibility
  const scene = graph3d.scene();
  scene.add(new THREE.AmbientLight(0xffffff, 0.6));
  const dirLight = new THREE.DirectionalLight(0xffffff, 0.4);
  dirLight.position.set(100, 200, 100);
  scene.add(dirLight);

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
  let html = '<div class="filter-group"><h3 title="Nebula clusters — each group is a directory in the project. Click to fly camera to that group.">Packages</h3>';
  sorted.forEach(([name, count]) => {
    const color = GROUP_COLORS[name] || '#888';
    const shortName = name.split('/').pop() || name;
    html += `<div class="ftoggle" onclick="focusGroup('${name.replace(/'/g, "\\'")}')\" title="Click to focus on ${name} (${count} nodes) — camera will fly to this nebula">
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
  const label = document.getElementById('health-toggle-label');
  if (label) label.textContent = healthMode ? 'Health gradient' : 'Label colors';
  const dot = document.querySelector('#health-toggle .fdot');
  if (dot) dot.style.background = healthMode ? '#f38ba8' : 'var(--green)';
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

function updateStats() {
  const {nodes: filteredNodes, links: filteredLinks} = getFilteredData();
  const groupCount = new Set(allNodes.map(n => n.group)).size;
  document.getElementById('sidebar-stats').textContent = `${filteredNodes.length} nodes · ${filteredLinks.length} edges · ${groupCount} groups`;
  // Update topbar stats span without overwriting the mode-selector buttons
  const topbarStats = document.getElementById('topbar-stats');
  if (topbarStats) {
    const modeNames = {architecture: 'Architecture', logic: 'Logic', deep: 'Deep'};
    topbarStats.innerHTML = '<span>' + (modeNames[currentMode] || currentMode) + '</span> ' +
      filteredNodes.length + ' nodes &middot; ' + filteredLinks.length + ' links';
  }
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
  // Mode keyboard shortcuts — only when not typing in an input
  if (!document.activeElement || document.activeElement.tagName !== 'INPUT') {
    if (e.key === '1') { switchMode('architecture'); return; }
    if (e.key === '2') { switchMode('logic'); return; }
    if (e.key === '3') { switchMode('deep'); return; }
  }
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

  // 1. Find directly changed node IDs (prefer node_ids_* from backend)
  activeChangeIds.clear();
  activeImpactIds.clear();

  // Track change frequency per symbol
  [...(change.nodes_added || []), ...(change.nodes_modified || [])].forEach(name => {
    sessionChangeCount[name] = (sessionChangeCount[name] || 0) + 1;
  });

  const nodeIdSet = new Set(gData.nodes.map(n => n.id));
  const idsFromBackend = [
    ...(change.node_ids_added || []),
    ...(change.node_ids_modified || []),
  ].filter(id => nodeIdSet.has(id));

  if (idsFromBackend.length > 0) {
    idsFromBackend.forEach(id => activeChangeIds.add(id));
  } else {
    // Fallback: match by name + file (for older events without node IDs)
    const changedNames = new Set([
      ...(change.nodes_added || []),
      ...(change.nodes_modified || []),
    ]);
    const changedFile = (change.file || '').split('/').pop();
    gData.nodes.forEach(n => {
      if (changedNames.has(n.name) && n.file && n.file.endsWith(changedFile)) {
        activeChangeIds.add(n.id);
      }
    });
    // If still no match, match all nodes in the changed file
    if (activeChangeIds.size === 0) {
      gData.nodes.forEach(n => {
        if (n.file && changedFile && n.file.endsWith(changedFile)) {
          activeChangeIds.add(n.id);
        }
      });
    }
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
  refreshNodeAppearance();
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

function toggleDiff(id, toggle) {
  const el = document.getElementById(id);
  if (el) {
    el.classList.toggle('collapsed');
    if (toggle) {
      toggle.textContent = el.classList.contains('collapsed') ? 'show' : 'hide';
    }
  }
}
function toggleSource(id, toggle) {
  const el = document.getElementById(id);
  if (el) {
    el.classList.toggle('open');
    if (toggle) {
      toggle.textContent = el.classList.contains('open') ? 'hide' : 'code';
    }
  }
}

function highlightPython(code) {
  if (typeof hljs !== 'undefined') {
    try { return hljs.highlight(code, {language: 'python'}).value; } catch(e) {}
  }
  return escHtml(code);
}

function formatDiff(text) {
  return text.split('\n').map(line => {
    if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('@@')) {
      return '<span class="diff-line-hdr">' + escHtml(line) + '</span>';
    }
    if (line.startsWith('+')) return '<span class="diff-line-add">' + highlightPython(line.slice(1)) + '</span>';
    if (line.startsWith('-')) return '<span class="diff-line-del">' + highlightPython(line.slice(1)) + '</span>';
    return highlightPython(line.startsWith(' ') ? line.slice(1) : line);
  }).join('\n');
}

function formatDiffRemoved(text) {
  return text.split('\n').map(line => {
    return '<span class="diff-line-del">' + highlightPython(line) + '</span>';
  }).join('\n');
}

function formatSourceHighlighted(text) {
  return highlightPython(text);
}

function ordinal(n) {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

async function fetchTestSuggestions(names) {
  const section = document.getElementById('test-suggestions-section');
  const loading = document.getElementById('test-suggestions-loading');
  if (!section) return;

  const allSuggestions = [];
  for (const name of names) {
    try {
      const r = await fetch('/api/suggest-tests?name=' + encodeURIComponent(name));
      const d = await r.json();
      if (d.suggestions) allSuggestions.push(...d.suggestions);
    } catch(e) {}
  }

  if (loading) loading.remove();

  if (allSuggestions.length === 0) {
    section.innerHTML = '<h4>Tests to Run</h4><div style="font-size:10px;color:var(--overlay0)">No test suggestions found</div>';
    return;
  }

  // Deduplicate by test_file + test_name
  const seen = new Set();
  const unique = allSuggestions.filter(s => {
    const key = s.test_file + '::' + s.test_name;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  let testsHtml = '<h4>Tests to Run (' + unique.length + ')</h4>';
  unique.forEach(s => {
    const file = s.test_file.split('/').pop();
    testsHtml += '<div class="test-item">' + file + '::' + s.test_name + '<span class="test-depth">depth ' + s.depth + '</span></div>';
  });
  section.innerHTML = testsHtml;
}

// Build a mini flow diagram for a changed node
function buildFlowDiagram(nodeId) {
  const gData = graph3d ? graph3d.graphData() : {nodes:[]};
  const nd = gData.nodes.find(n => n.id === nodeId);
  if (!nd) return '';

  // Collect callers (incoming CALLS edges) and callees (outgoing CALLS edges)
  const callers = [];
  const callees = [];
  (linkIndex.to[nodeId] || []).forEach(l => {
    if (l.type !== 'CALLS') return;
    const sid = typeof l.source === 'object' ? l.source.id : l.source;
    const src = gData.nodes.find(n => n.id === sid);
    if (src) callers.push(src);
  });
  (linkIndex.from[nodeId] || []).forEach(l => {
    if (l.type !== 'CALLS') return;
    const tid = typeof l.target === 'object' ? l.target.id : l.target;
    const tgt = gData.nodes.find(n => n.id === tid);
    if (tgt) callees.push(tgt);
  });

  if (callers.length === 0 && callees.length === 0) return '';

  let html = '<div class="flow-diagram">';

  // Left column: callers
  if (callers.length > 0) {
    html += '<div class="flow-col">';
    callers.slice(0, 4).forEach(c => {
      html += '<div class="flow-node flow-node-caller" onclick="previewNode(\'' + c.id + '\')" title="' + c.name + ' calls this function">';
      html += c.name;
      html += '<div class="flow-node-file">' + (c.file || '').split('/').pop() + '</div></div>';
    });
    if (callers.length > 4) html += '<div class="flow-more">+' + (callers.length - 4) + ' more</div>';
    html += '</div>';
    html += '<div class="flow-arrow">&#8594;</div>';
  }

  // Center: changed node
  html += '<div class="flow-col">';
  html += '<div class="flow-node flow-node-changed" onclick="previewNode(\'' + nd.id + '\')" title="Changed function">';
  html += '<b>' + nd.name + '</b>';
  html += '<div class="flow-node-file">' + (nd.file || '').split('/').pop() + '</div></div>';
  html += '</div>';

  // Right column: callees
  if (callees.length > 0) {
    html += '<div class="flow-arrow">&#8594;</div>';
    html += '<div class="flow-col">';
    callees.slice(0, 4).forEach(c => {
      html += '<div class="flow-node flow-node-callee" onclick="previewNode(\'' + c.id + '\')" title="This function calls ' + c.name + '">';
      html += c.name;
      html += '<div class="flow-node-file">' + (c.file || '').split('/').pop() + '</div></div>';
    });
    if (callees.length > 4) html += '<div class="flow-more">+' + (callees.length - 4) + ' more</div>';
    html += '</div>';
  }

  html += '</div>';
  return html;
}

function focusChangeFile(fname) {
  // Find and re-trigger the most recent change event for this filename
  const evt = changeHistory.find(c => (c.file || '').split('/').pop() === fname);
  if (evt) handleChangeEvent(evt);
}

function setChangeView(mode) {
  changeViewMode = mode;
  // Re-render with the last change event
  if (window._lastChangeForPanel) showImpactPanel(window._lastChangeForPanel);
}

function showImpactPanel(change) {
  window._lastChangeForPanel = change;
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

  const added = change.nodes_added || [];
  const modified = change.nodes_modified || [];
  const removed = change.nodes_removed || [];
  const idsAdded = change.node_ids_added || [];
  const idsModified = change.node_ids_modified || [];
  const idsRemoved = change.node_ids_removed || [];

  function findChangedNode(name, idx, idList) {
    if (idx < idList.length) return gData.nodes.find(n => n.id === idList[idx]);
    return gData.nodes.find(n => n.name === name && activeChangeIds.has(n.id));
  }

  // View toggle
  let html = '<div class="insp-section" style="padding:6px 12px">';
  html += '<div class="view-toggle">';
  html += '<button class="view-toggle-btn ' + (changeViewMode === 'summary' ? 'active' : '') + '" onclick="setChangeView(\'summary\')" title="Compact summary with flow diagrams">Summary</button>';
  html += '<button class="view-toggle-btn ' + (changeViewMode === 'detail' ? 'active' : '') + '" onclick="setChangeView(\'detail\')" title="Full detail with code diffs and dependency lists">Detail</button>';
  html += '</div></div>';

  if (changeViewMode === 'summary') {
    // ═══════════════ SUMMARY MODE ═══════════════

    // Session overview — aggregate all files changed this session
    if (changeHistory.length > 1) {
      const fileMap = {};
      changeHistory.forEach(c => {
        const f = (c.file || '').split('/').pop();
        if (!fileMap[f]) fileMap[f] = {added: 0, modified: 0, removed: 0, risk: 'LOW', file: c.file};
        fileMap[f].added += (c.nodes_added || []).length;
        fileMap[f].modified += (c.nodes_modified || []).length;
        fileMap[f].removed += (c.nodes_removed || []).length;
        const riskOrder = {LOW:0, MEDIUM:1, HIGH:2, CRITICAL:3};
        if (c.impact && riskOrder[c.impact.risk] > riskOrder[fileMap[f].risk]) fileMap[f].risk = c.impact.risk;
      });
      const files = Object.entries(fileMap).sort((a,b) => (b[1].added+b[1].modified+b[1].removed) - (a[1].added+a[1].modified+a[1].removed));
      html += '<div class="insp-section"><h4>Session: ' + files.length + ' files changed</h4>';
      files.forEach(([fname, stats]) => {
        const rc = stats.risk === 'CRITICAL' ? 'var(--red)' : stats.risk === 'HIGH' ? 'var(--peach)' : stats.risk === 'MEDIUM' ? 'var(--yellow)' : 'var(--green)';
        html += '<div style="display:flex;gap:6px;align-items:center;padding:2px 0;font-size:10px;cursor:pointer" onclick="focusChangeFile(\'' + escHtml(fname) + '\')">';
        html += '<span style="color:var(--subtext);min-width:90px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + fname + '</span>';
        if (stats.added) html += '<span style="color:var(--green)">+' + stats.added + '</span>';
        if (stats.modified) html += '<span style="color:var(--yellow)">~' + stats.modified + '</span>';
        if (stats.removed) html += '<span style="color:var(--red)">-' + stats.removed + '</span>';
        html += '<span class="risk-badge risk-' + stats.risk + '" style="margin-left:auto;font-size:8px;padding:0 4px">' + stats.risk + '</span>';
        html += '</div>';
      });
      html += '</div>';
    }

    // Current file summary card
    html += '<div class="insp-section"><div class="change-summary" style="border-left-color:' + riskColor + '">';
    html += '<div class="change-summary-title" style="color:' + typeColor + '">' + typeLabel + ' ' + file + '</div>';
    html += '<div class="change-summary-stats">';
    if (added.length) html += '<span style="color:var(--green)">+' + added.length + ' added</span> &nbsp;';
    if (modified.length) html += '<span style="color:var(--yellow)">~' + modified.length + ' modified</span> &nbsp;';
    if (removed.length) html += '<span style="color:var(--red)">-' + removed.length + ' removed</span> &nbsp;';
    html += '<br>' + story.outgoing.length + ' outgoing calls &middot; ' + story.incoming.length + ' dependents';
    if (change.impact) html += ' &middot; ' + change.impact.affected_count + ' in blast radius';
    html += '</div></div></div>';

    // Flow diagrams for each changed function (max 5)
    const changedItems = [];
    added.forEach((name, i) => { const nd = findChangedNode(name, i, idsAdded); if (nd) changedItems.push({name, nd, type: 'added'}); });
    modified.forEach((name, i) => { const nd = findChangedNode(name, i, idsModified); if (nd) changedItems.push({name, nd, type: 'modified'}); });

    if (changedItems.length > 0) {
      html += '<div class="insp-section"><h4>Impact Flow</h4>';
      changedItems.slice(0, 5).forEach(item => {
        const typeC = item.type === 'added' ? 'var(--green)' : 'var(--yellow)';
        const prefix = item.type === 'added' ? '+' : '~';
        html += '<div style="font-size:10px;color:' + typeC + ';margin-bottom:2px"><b>' + prefix + ' ' + item.name + '</b></div>';
        html += buildFlowDiagram(item.nd.id);
      });
      if (changedItems.length > 5) html += '<div style="font-size:10px;color:var(--overlay0)">+' + (changedItems.length - 5) + ' more changes...</div>';
      html += '</div>';
    }

    // Removed — show old code + orphaned callers
    if (removed.length > 0) {
      html += '<div class="insp-section"><h4>Removed (' + removed.length + ')</h4>';
      removed.forEach((name, i) => {
        const diffText = (change.diffs && change.diffs[name]) || '';
        const diffId = 'diff-sum-rem-' + i;

        // Header
        html += '<div style="padding:4px 0;font-size:11px;color:var(--red);font-weight:bold">- ' + name + '</div>';

        // Old source code (highlighted, red border)
        if (diffText) {
          html += '<div class="diff-block" style="border-left-color:var(--red)">' + formatDiffRemoved(diffText) + '</div>';
        }

        // Orphaned callers — scan story.incoming for anyone who called this name
        const orphanedCallers = story.incoming.filter(dep => {
          // Check if this dependent's outgoing edges referenced the removed function name
          const depLinks = linkIndex.from[dep.id] || [];
          return depLinks.some(l => {
            const tid = typeof l.target === 'object' ? l.target.id : l.target;
            // The target node was removed so it won't be in gData, but check by name
            // across activeChangeIds or removedIds
            const tgt = gData.nodes.find(n => n.id === tid);
            return tgt && tgt.name === name;
          });
        });

        // Also check: any node in the graph whose source mentions this function name
        // (simpler heuristic: just show all story.incoming as potentially affected)
        const callerCount = orphanedCallers.length || story.incoming.length;

        if (story.incoming.length > 0) {
          html += '<div style="font-size:9px;color:var(--overlay0);margin:2px 0 4px 14px">';
          if (orphanedCallers.length > 0) {
            html += '<span style="color:var(--peach)">' + orphanedCallers.length + ' callers may be broken:</span> ';
            orphanedCallers.slice(0, 5).forEach(dep => {
              html += '<span style="cursor:pointer;color:var(--peach)" onclick="previewNode(\'' + dep.id + '\')">' + dep.name + '</span> ';
            });
            if (orphanedCallers.length > 5) html += '+' + (orphanedCallers.length - 5) + ' more';
          } else {
            html += '<span style="color:var(--peach)">' + story.incoming.length + ' dependents in this file may be affected</span>';
          }
          html += '</div>';
        }
      });
      html += '</div>';
    }

  } else {
    // ═══════════════ DETAIL MODE ═══════════════
    // What Changed with diffs
    if (added.length + modified.length + removed.length > 0) {
      html += '<div class="insp-section"><h4>What Changed</h4>';
      added.forEach((name, i) => {
        const nd = findChangedNode(name, i, idsAdded);
        const freq = sessionChangeCount[name] || 0;
        const diffText = (change.diffs && change.diffs[name]) || '';
        const diffId = 'diff-add-' + i;
        html += '<div style="padding:3px 0;font-size:11px">';
        html += '<span style="color:var(--green);font-weight:bold">+ </span>';
        if (nd) html += '<span style="cursor:pointer;color:var(--green)" onclick="previewNode(\'' + nd.id + '\')">' + name + '</span>';
        else html += '<span style="color:var(--green)">' + name + '</span>';
        html += ' <span style="color:var(--surface2);font-size:9px">added</span>';
        if (freq > 1) html += '<span class="change-freq">(' + ordinal(freq) + ' change)</span>';
        if (diffText) html += ' <span class="collapse-toggle" onclick="toggleDiff(\'' + diffId + '\', this)">hide</span>';
        html += '</div>';
        if (diffText) html += '<div class="diff-block" id="' + diffId + '">' + formatDiff(diffText) + '</div>';
      });
      modified.forEach((name, i) => {
        const nd = findChangedNode(name, i, idsModified);
        const freq = sessionChangeCount[name] || 0;
        const diffText = (change.diffs && change.diffs[name]) || '';
        const diffId = 'diff-mod-' + i;
        html += '<div style="padding:3px 0;font-size:11px">';
        html += '<span style="color:var(--yellow);font-weight:bold">~ </span>';
        if (nd) html += '<span style="cursor:pointer;color:var(--yellow)" onclick="previewNode(\'' + nd.id + '\')">' + name + '</span>';
        else html += '<span style="color:var(--yellow)">' + name + '</span>';
        if (freq > 1) html += '<span class="change-freq">(' + ordinal(freq) + ' change)</span>';
        if (diffText) html += ' <span class="collapse-toggle" onclick="toggleDiff(\'' + diffId + '\', this)">hide</span>';
        html += '</div>';
        if (diffText) html += '<div class="diff-block" id="' + diffId + '">' + formatDiff(diffText) + '</div>';
      });
      removed.forEach((name, i) => {
        const diffText = (change.diffs && change.diffs[name]) || '';
        const diffId = 'diff-rem-' + i;
        html += '<div style="padding:3px 0;font-size:11px">';
        html += '<span style="color:var(--red);font-weight:bold">- </span>';
        html += '<span style="color:var(--red)">' + name + '</span>';
        html += ' <span style="color:var(--surface2);font-size:9px">removed</span>';
        if (diffText) html += ' <span class="collapse-toggle" onclick="toggleDiff(\'' + diffId + '\', this)">hide</span>';
        html += '</div>';
        if (diffText) html += '<div class="diff-block" id="' + diffId + '">' + formatDiffRemoved(diffText) + '</div>';
      });
      html += '</div>';
    }

    // Calls (outgoing)
    if (story.outgoing.length > 0) {
      html += '<div class="insp-section"><h4>Calls (' + story.outgoing.length + ')</h4>';
      story.outgoing.forEach((dep, i) => {
        const c = GROUP_COLORS[gData.nodes.find(n=>n.id===dep.id)?.group] || 'var(--blue)';
        const srcNode = gData.nodes.find(n => n.id === dep.id);
        const srcId = 'src-out-' + i;
        html += '<div class="rel-item" onclick="previewNode(\'' + dep.id + '\')">';
        html += '<span style="color:var(--blue)">&#8594;</span> ';
        html += '<span class="fdot" style="background:' + c + '"></span>';
        html += dep.name;
        html += ' <span class="rel-type">' + dep.file + '</span>';
        if (srcNode && srcNode.source) html += ' <span class="collapse-toggle" onclick="event.stopPropagation();toggleSource(\'' + srcId + '\', this)">code</span>';
        html += '</div>';
        if (srcNode && srcNode.source) html += '<div class="source-preview" id="' + srcId + '">' + formatSourceHighlighted(srcNode.source) + '</div>';
      });
      html += '</div>';
    }

    // Depended on by (incoming)
    if (story.incoming.length > 0) {
      html += '<div class="insp-section"><h4>Depended On By (' + story.incoming.length + ')</h4>';
      story.incoming.forEach((dep, i) => {
        const c = GROUP_COLORS[gData.nodes.find(n=>n.id===dep.id)?.group] || 'var(--peach)';
        const srcNode = gData.nodes.find(n => n.id === dep.id);
        const srcId = 'src-in-' + i;
        html += '<div class="rel-item" onclick="previewNode(\'' + dep.id + '\')">';
        html += '<span style="color:var(--peach)">&#8592;</span> ';
        html += '<span class="fdot" style="background:' + c + '"></span>';
        html += dep.name;
        html += ' <span class="rel-type">' + dep.file + '</span>';
        if (srcNode && srcNode.source) html += ' <span class="collapse-toggle" onclick="event.stopPropagation();toggleSource(\'' + srcId + '\', this)">code</span>';
        html += '</div>';
        if (srcNode && srcNode.source) html += '<div class="source-preview" id="' + srcId + '">' + formatSourceHighlighted(srcNode.source) + '</div>';
      });
      html += '</div>';
    }
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

  // ── Tests to Run ──
  const changedNames = [...(change.nodes_added || []), ...(change.nodes_modified || [])];
  if (changedNames.length > 0) {
    html += '<div class="insp-section" id="test-suggestions-section"><h4>Tests to Run</h4>';
    html += '<div id="test-suggestions-loading" style="font-size:10px;color:var(--overlay0)">Loading...</div>';
    html += '</div>';
  }

  document.getElementById('insp-body').innerHTML = html;

  // Fetch test suggestions async
  if (changedNames.length > 0) {
    fetchTestSuggestions(changedNames);
  }
}

function clearChangeHighlight() {
  changeHighlightActive = false;
  activeChangeIds.clear();
  activeImpactIds.clear();
  // Close impact panel
  document.getElementById('inspector').classList.remove('open');
  setTimeout(function() { if (graph3d) graph3d.width(document.getElementById('graph-container').clientWidth); }, 100);
  // Re-render with normal colors
  refreshNodeAppearance();
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

// ── Start ───────────────────────────────────────────────────
loadData();
