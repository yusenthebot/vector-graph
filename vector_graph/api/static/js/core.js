// ── core.js — Data loading, graph initialization, filtering ──

// ── FPS counter ──────────────────────────────────────────────
let _fpsFrames = 0, _fpsLast = performance.now();
function _fpsLoop() {
  _fpsFrames++;
  const now = performance.now();
  if (now - _fpsLast >= 1000) {
    const el = document.getElementById('sb-fps');
    if (el) el.textContent = _fpsFrames + ' fps';
    _fpsFrames = 0;
    _fpsLast = now;
  }
  requestAnimationFrame(_fpsLoop);
}
requestAnimationFrame(_fpsLoop);

// ── Data loading ────────────────────────────────────────────
async function loadData() {
  // Pre-cache all 3 modes in parallel for instant switching
  const [archR, logicR, deepR] = await Promise.all([
    fetch('/api/data?mode=architecture').then(r => r.json()),
    fetch('/api/data?mode=logic').then(r => r.json()),
    fetch('/api/data?mode=deep').then(r => r.json()),
  ]);
  modeCache = {architecture: archR, logic: logicR, deep: deepR};

  // Fetch git history data (non-blocking — augments nodes after load)
  let gitData = null;
  fetch('/api/git-history').then(r => r.json()).then(d => {
    gitData = d;
    // Enrich nodes in all cached modes with hotspot data
    if (gitData && gitData.hotspots) {
      const hotspotMap = {};
      gitData.hotspots.forEach(h => { hotspotMap[h.file] = h; });
      Object.values(modeCache).forEach(modeData => {
        modeData.nodes.forEach(n => {
          // Match by relative file path (node.file may be absolute)
          const relFile = n.file ? n.file.split('/').slice(-2).join('/') : '';
          const fullFile = n.file || '';
          const hs = hotspotMap[relFile] || hotspotMap[fullFile] ||
                     Object.values(hotspotMap).find(h => fullFile.endsWith(h.file));
          if (hs) {
            n.hotspotScore = hs.score;
            n.hotspotChanges = hs.changes;
            n.hotspotRecent = hs.recent;
            n.hotspotContributors = hs.contributors;
            n.hotspotLastModified = hs.last_modified;
          }
        });
      });
    }
  }).catch(() => {});

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
  buildLegend();
  updateChangesPanel();
  updateStatusBar();
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
  hoveredId = null;
  highlightNodes.clear();
  highlightLinks.clear();
  changeHighlightActive = false;
  activeChangeIds.clear();
  activeImpactIds.clear();
  if (impactGraph2d) { impactGraph2d._destructor && impactGraph2d._destructor(); impactGraph2d = null; }
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
  buildLegend();
  updateChangesPanel();
  updateStatusBar();
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
      var emissiveIntensity = typeof getNodeEmissive === 'function' ? getNodeEmissive(n) : 0.15;
      const mat = new THREE.MeshStandardMaterial({
        color: color,
        emissive: color,
        emissiveIntensity: emissiveIntensity,
        metalness: 0.05,
        roughness: 0.6,
        transparent: true,
        opacity: 0.92,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.scale.setScalar(size * 0.8);

      // Label sprite — LOD controls visibility via _updateLabelVisibility
      var group = new THREE.Group();
      group.add(mesh);
      var labelSprite = _makeNodeLabel(n.name, COLORS[n.label] || '#cdd6f4');
      labelSprite.position.set(0, size * 1.2, 0);
      labelSprite.visible = false; // hidden by default, LOD shows when close enough
      labelSprite.userData = {isNodeLabel: true};
      group.add(labelSprite);
      return group;
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
      // Git hotspot info
      if (n.hotspotScore !== undefined) {
        const hsColor = n.hotspotScore >= 0.8 ? '#f38ba8' : n.hotspotScore >= 0.5 ? '#fab387' : n.hotspotScore >= 0.2 ? '#f9e2af' : '#89b4fa';
        t += '<br><span style="color:' + hsColor + '">&#9632; ' + n.hotspotChanges + ' changes (90d)</span>';
        if (n.hotspotRecent) t += ' <span style="color:#585b70">' + n.hotspotRecent + ' recent</span>';
        if (n.hotspotContributors && n.hotspotContributors.length) {
          t += '<br><span style="color:#585b70">by ' + n.hotspotContributors.slice(0,2).join(', ') + '</span>';
        }
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
        return '#1e1e2e'; // faint — not invisible
      }
      // Change highlight — spotlight: direct edges bright, rest keep normal color
      if (changeHighlightActive) {
        const srcChanged = activeChangeIds.has(sid);
        const tgtChanged = activeChangeIds.has(tid);
        if (srcChanged || tgtChanged) return '#fab387';
        if (activeImpactIds.has(sid) && activeImpactIds.has(tid)) return '#fab38733';
        return EDGE_COLORS[l.type] || '#45475a';
      }
      // Hover — show edges touching hovered node
      if (hoveredId) {
        if (sid === hoveredId || tid === hoveredId) return EDGE_COLORS[l.type] || '#89b4fa';
      }
      // Default: faint baseline edges
      return EDGE_COLORS[l.type] || '#45475a';
    })
    .linkOpacity(l => {
      const sid = typeof l.source === 'object' ? l.source.id : l.source;
      const tid = typeof l.target === 'object' ? l.target.id : l.target;
      if (selectedId) {
        return (sid === selectedId || tid === selectedId) ? 0.4 : 0.01;
      }
      if (changeHighlightActive) {
        const srcChanged = activeChangeIds.has(sid);
        const tgtChanged = activeChangeIds.has(tid);
        if (srcChanged || tgtChanged) return 0.6;
        if (activeImpactIds.has(sid) && activeImpactIds.has(tid)) return 0.08;
        if (l.type === 'CALLS') return 0.04;
        if (l.type === 'IMPORTS') return 0.03;
        return 0.02;
      }
      // Hover — boost edges touching hovered node
      if (hoveredId) {
        if (sid === hoveredId || tid === hoveredId) return 0.4;
      }
      // Default: faint baseline
      if (l.type === 'CALLS') return 0.015;
      if (l.type === 'IMPORTS') return 0.012;
      return 0.008;
    })
    .linkWidth(l => {
      const sid = typeof l.source === 'object' ? l.source.id : l.source;
      const tid = typeof l.target === 'object' ? l.target.id : l.target;
      if (selectedId) {
        return (sid === selectedId || tid === selectedId) ? 0.8 : 0.05;
      }
      if (changeHighlightActive) {
        const srcChanged = activeChangeIds.has(sid);
        const tgtChanged = activeChangeIds.has(tid);
        if (srcChanged || tgtChanged) return 1.5;
        if (activeImpactIds.has(sid) && activeImpactIds.has(tid)) return 0.3;
        if (l.type === 'CALLS') return 0.15;
        if (l.type === 'IMPORTS' || l.type === 'EXTENDS') return 0.1;
        return 0.05;
      }
      // Hover — boost edges touching hovered node
      if (hoveredId) {
        if (sid === hoveredId || tid === hoveredId) return 1.0;
      }
      // Default: faint baseline
      if (l.type === 'CALLS') return 0.15;
      if (l.type === 'IMPORTS' || l.type === 'EXTENDS') return 0.1;
      return 0.05;
    })
    .linkCurvature(l => {
      if (l.type === 'CALLS') return 0.15;
      if (l.type === 'IMPORTS') return 0.2;
      if (l.type === 'EXTENDS') return 0.25;
      return 0.1;
    })
    .linkCurveRotation(l => l.type === 'IMPORTS' ? Math.PI * 0.5 : 0)
    .linkDirectionalArrowLength(l => {
      const sid = typeof l.source === 'object' ? l.source.id : l.source;
      const tid = typeof l.target === 'object' ? l.target.id : l.target;
      if (hoveredId) {
        return (sid === hoveredId || tid === hoveredId) ? 2.5 : 0;
      }
      if (!selectedId) return l.type === 'CALLS' ? 1.0 : 0; // small default arrow for CALLS directional hint
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
    .onNodeHover(n => { hoveredId = n ? n.id : null; })
    .onBackgroundClick(() => { deselectNode(); clearChangeHighlight(); })
    .warmupTicks(80)
    .cooldownTicks(120)
    .d3AlphaDecay(0.04)
    .d3VelocityDecay(0.4)
    .d3AlphaMin(0.01)
    .enableNodeDrag(true)
    .enableNavigationControls(true)

  // Edge dash patterns — conditional: linkLineDash not available in all 3d-force-graph versions
  if (typeof graph3d.linkLineDash === 'function') {
    graph3d.linkLineDash(function(l) {
      if (l.type === 'IMPORTS') return [4, 2];
      if (l.type === 'EXTENDS' || l.type === 'IMPLEMENTS') return [1, 2];
      return null;
    });
  }

  // Lighting for MeshStandardMaterial (PBR)
  const scene = graph3d.scene();
  scene.add(new THREE.AmbientLight(0xffffff, 0.5));
  const dirLight = new THREE.DirectionalLight(0xffffff, 0.6);
  dirLight.position.set(100, 200, 100);
  scene.add(dirLight);
  var dirLight2 = new THREE.DirectionalLight(0xffffff, 0.2);
  dirLight2.position.set(-80, -100, -60);
  scene.add(dirLight2);

  // Seed initial positions by group — spread groups apart before simulation
  _seedGroupPositions(nodes);

  // Inject clustering force — strong enough to overcome link/charge forces
  graph3d.d3Force('cluster', clusterForce(0.6));
  // Weaker charge so groups stay compact, stronger inter-group repulsion handled by cluster
  graph3d.d3Force('charge').strength(-15);
  // Weaker link distance so intra-group links pull tight
  graph3d.d3Force('link').distance(20).strength(0.3);

  // Post-processing pipeline (bloom, fog, dust)
  if (typeof setupPostProcessing === 'function') setupPostProcessing();

  // Render nebulae once when simulation stabilizes
  graph3d.onEngineStop(() => updateNebulae());

  // Label LOD — check visibility every 200ms (5fps) based on camera distance
  setInterval(_updateLabelVisibility, 200);
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
  updateStatusBar();
}
