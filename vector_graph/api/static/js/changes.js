// ── changes.js — SSE, change events, impact subgraph, narrative ──
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
      bufferChangeEvent(change);
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

// ── Change grouping — 5-second debounce window ──────────────
function bufferChangeEvent(change) {
  changeGroupBuffer.push(change);

  // Reset the timer — wait for more events in the window
  if (changeGroupTimer) clearTimeout(changeGroupTimer);
  changeGroupTimer = setTimeout(() => {
    flushChangeGroup();
  }, CHANGE_GROUP_WINDOW);

  // Also immediately process the FIRST event for instant feedback
  if (changeGroupBuffer.length === 1) {
    handleChangeEvent(change);
  }
}

function flushChangeGroup() {
  changeGroupTimer = null;
  if (changeGroupBuffer.length <= 1) {
    // Single event already processed
    changeGroupBuffer = [];
    return;
  }

  // Multiple events — re-trigger handleChangeEvent with the LAST event
  // (which will show the session summary in the impact panel)
  const lastEvent = changeGroupBuffer[changeGroupBuffer.length - 1];
  changeGroupBuffer = [];
  handleChangeEvent(lastEvent);
}

// ── Ripple animation ─────────────────────────────────────────
function triggerRipple(cx, cy, cz) {
  if (!graph3d || typeof THREE === 'undefined') return;
  const scene = graph3d.scene();
  if (!scene) return;

  // Create expanding ring
  const geo = new THREE.RingGeometry(1, 3, 64);
  const mat = new THREE.MeshBasicMaterial({
    color: 0xf9e2af,  // warm yellow
    transparent: true,
    opacity: 0.5,
    side: THREE.DoubleSide,
  });
  const ring = new THREE.Mesh(geo, mat);
  ring.position.set(cx, cy, cz);
  // Face the camera
  ring.lookAt(graph3d.camera().position);
  scene.add(ring);

  const startTime = Date.now();
  const duration = 2000; // 2 seconds
  const maxScale = 120;

  function animateRipple() {
    const elapsed = Date.now() - startTime;
    const t = elapsed / duration;
    if (t >= 1) {
      scene.remove(ring);
      geo.dispose();
      mat.dispose();
      return;
    }
    const scale = t * maxScale;
    ring.scale.set(scale, scale, scale);
    ring.material.opacity = 0.5 * (1 - t * t); // quadratic fade
    ring.lookAt(graph3d.camera().position); // keep facing camera
    requestAnimationFrame(animateRipple);
  }
  requestAnimationFrame(animateRipple);
}

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
    // If still no match, match all nodes in the changed file (endsWith)
    if (activeChangeIds.size === 0) {
      gData.nodes.forEach(n => {
        if (n.file && changedFile && n.file.endsWith(changedFile)) {
          activeChangeIds.add(n.id);
        }
      });
    }
    // Broader fallback: exact basename comparison — handles path separator differences
    if (activeChangeIds.size === 0 && changedFile) {
      gData.nodes.forEach(function(n) {
        if (n.file && n.file.split('/').pop() === changedFile) {
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
      triggerRipple(cx, cy, cz);
    }
  }

  // 6. Trigger full re-render
  refreshNodeAppearance();
  graph3d.linkColor(graph3d.linkColor());
  graph3d.linkWidth(graph3d.linkWidth());
  graph3d.linkOpacity(graph3d.linkOpacity());
  graph3d.linkDirectionalParticles(graph3d.linkDirectionalParticles());
  graph3d.linkDirectionalParticleColor(graph3d.linkDirectionalParticleColor());

  // 6b. Spotlight: add pulsing glow rings on changed nodes
  addChangeGlowRings();

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

  // 9. Browser notification for high-risk changes
  if (change.impact && (change.impact.risk === 'HIGH' || change.impact.risk === 'CRITICAL')) {
    if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
      const file = (change.file || '').split('/').pop();
      new Notification('vector-graph', {
        body: change.impact.risk + ' risk change in ' + file + ' — ' + activeChangeIds.size + ' nodes affected',
        icon: '/api/logo',
        tag: 'vg-change', // replace previous notification
      });
    }
  }

  // 10. Update status bar hints to reflect change highlight mode
  updateStatusBar();
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

  // Fetch in parallel with 3s timeout per request
  const allSuggestions = [];
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 3000);
  try {
    const results = await Promise.allSettled(
      names.slice(0, 5).map(name =>  // max 5 to avoid flooding
        fetch('/api/suggest-tests?name=' + encodeURIComponent(name), {signal: controller.signal})
          .then(r => r.json())
      )
    );
    results.forEach(r => {
      if (r.status === 'fulfilled' && r.value.suggestions) {
        allSuggestions.push(...r.value.suggestions);
      }
    });
  } catch(e) {}
  clearTimeout(timeout);

  if (loading) loading.remove();

  if (allSuggestions.length === 0) {
    section.innerHTML = '<h4>Tests to Run</h4><div style="font-size:10px;color:var(--overlay0)">No related tests found in call graph</div>';
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

// Build 2D impact subgraph data (nodes + links) for canvas rendering
// 2D impact graph — progressive disclosure: start with changed nodes only,
// click to expand neighbors. Labels on hover, not rendered permanently.
let _expandedNode2d = null; // currently expanded node in 2D graph
let hovered2dId = null; // hover-to-show labels when >15 nodes

function buildImpactSubgraph() {
  const gData = graph3d ? graph3d.graphData() : {nodes:[], links:[]};
  const subNodes = new Map();
  const subLinks = [];

  // 1. Only changed nodes initially (clean, readable)
  gData.nodes.forEach(n => {
    if (activeChangeIds.has(n.id)) {
      subNodes.set(n.id, {...n, _role: 'changed'});
    }
  });

  // 2. If a node is expanded, add its 1-hop neighbors
  if (_expandedNode2d) {
    const eid = _expandedNode2d;
    (linkIndex.to[eid] || []).forEach(l => {
      if (l.type !== 'CALLS' && l.type !== 'IMPORTS') return;
      const sid = typeof l.source === 'object' ? l.source.id : l.source;
      if (!subNodes.has(sid)) {
        const src = gData.nodes.find(n => n.id === sid);
        if (src) subNodes.set(sid, {...src, _role: 'caller'});
      }
    });
    (linkIndex.from[eid] || []).forEach(l => {
      if (l.type !== 'CALLS' && l.type !== 'IMPORTS') return;
      const tid = typeof l.target === 'object' ? l.target.id : l.target;
      if (!subNodes.has(tid)) {
        const tgt = gData.nodes.find(n => n.id === tid);
        if (tgt) subNodes.set(tid, {...tgt, _role: 'callee'});
      }
    });
  }

  const nodeIds = new Set(subNodes.keys());

  // 3. Edges between included nodes
  gData.links.forEach(l => {
    const sid = typeof l.source === 'object' ? l.source.id : l.source;
    const tid = typeof l.target === 'object' ? l.target.id : l.target;
    if (nodeIds.has(sid) && nodeIds.has(tid)) {
      subLinks.push({source: sid, target: tid, type: l.type});
    }
  });

  return {
    nodes: [...subNodes.values()].map(n => ({
      id: n.id,
      name: n.name,
      label: n.label,
      file: (n.file || '').split('/').pop(),
      fullFile: n.file || '',
      _role: n._role,
      _expanded: n.id === _expandedNode2d,
      _callerCount: (linkIndex.to[n.id] || []).filter(l => l.type === 'CALLS').length,
      _calleeCount: (linkIndex.from[n.id] || []).filter(l => l.type === 'CALLS').length,
      group: n.group,
      source: n.source || '',
    })),
    links: subLinks,
  };
}

function expand2dNode(nodeId) {
  _expandedNode2d = (_expandedNode2d === nodeId) ? null : nodeId; // toggle
  refreshImpactGraph2d();
}

function refreshImpactGraph2d() {
  const container = document.getElementById('impact-graph-container');
  if (!container || !impactGraph2d) return;
  const subgraph = buildImpactSubgraph();
  impactGraph2d.graphData(subgraph);
  // Update detail panel
  updateNodeDetail2d(_expandedNode2d);
}

function updateNodeDetail2d(nodeId) {
  const detailEl = document.getElementById('impact-node-detail');
  if (!detailEl) return;
  if (!nodeId) { detailEl.innerHTML = '<span style="color:var(--overlay0);font-size:10px">Click a node to see details</span>'; return; }

  const gData = graph3d ? graph3d.graphData() : {nodes:[]};
  const nd = gData.nodes.find(n => n.id === nodeId);
  if (!nd) { detailEl.innerHTML = ''; return; }

  const callers = (linkIndex.to[nodeId] || []).filter(l => l.type === 'CALLS').map(l => {
    const sid = typeof l.source === 'object' ? l.source.id : l.source;
    return gData.nodes.find(n => n.id === sid);
  }).filter(Boolean).slice(0, 8);

  const callees = (linkIndex.from[nodeId] || []).filter(l => l.type === 'CALLS').map(l => {
    const tid = typeof l.target === 'object' ? l.target.id : l.target;
    return gData.nodes.find(n => n.id === tid);
  }).filter(Boolean).slice(0, 8);

  let h = '<div style="font-size:11px;font-weight:bold;color:var(--text);margin-bottom:4px">' + escHtml(nd.name) + '</div>';
  h += '<div style="font-size:9px;color:var(--overlay0);margin-bottom:6px">' + escHtml((nd.file||'').split('/').pop()) + ' &middot; ' + nd.label + '</div>';

  if (callers.length > 0) {
    h += '<div style="font-size:9px;color:var(--overlay0);margin-bottom:2px">Called by:</div>';
    callers.forEach(c => {
      h += '<div style="font-size:10px;padding:1px 0;cursor:pointer;color:var(--peach)" onclick="previewNode(\'' + c.id + '\')">&larr; ' + c.name + '</div>';
    });
  }
  if (callees.length > 0) {
    h += '<div style="font-size:9px;color:var(--overlay0);margin-top:4px;margin-bottom:2px">Calls:</div>';
    callees.forEach(c => {
      h += '<div style="font-size:10px;padding:1px 0;cursor:pointer;color:var(--blue)" onclick="previewNode(\'' + c.id + '\')">&rarr; ' + c.name + '</div>';
    });
  }

  if (nd.source) {
    h += '<div style="margin-top:6px"><div class="diff-block" style="max-height:120px;font-size:9px">' + formatSourceHighlighted(nd.source) + '</div></div>';
  }

  detailEl.innerHTML = h;
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

function generateChangeNarrative(change) {
  const added = change.nodes_added || [];
  const modified = change.nodes_modified || [];
  const removed = change.nodes_removed || [];
  const gData = graph3d ? graph3d.graphData() : {nodes:[]};

  const parts = [];

  // Pattern 1: New function added + caller now uses it
  if (added.length > 0) {
    const addedWithCallers = [];
    added.forEach(name => {
      const nd = gData.nodes.find(n => n.name === name && activeChangeIds.has(n.id));
      if (!nd) return;
      const callers = (linkIndex.to[nd.id] || [])
        .map(l => typeof l.source === 'object' ? l.source : gData.nodes.find(n => n.id === l.source))
        .filter(Boolean)
        .filter(n => typeof n === 'object' && !activeChangeIds.has(n.id));
      if (callers.length > 0) {
        addedWithCallers.push({name, caller: callers[0].name || callers[0]});
      }
    });

    if (addedWithCallers.length > 0) {
      const first = addedWithCallers[0];
      parts.push('Added ' + first.name + ' and integrated into ' + first.caller);
      if (addedWithCallers.length > 1) parts[parts.length - 1] += ' (+' + (addedWithCallers.length - 1) + ' more)';
    } else if (added.length <= 3) {
      parts.push('Added ' + added.join(', '));
    } else {
      parts.push('Added ' + added.length + ' new functions');
    }
  }

  // Pattern 2: Modified functions
  if (modified.length > 0) {
    if (modified.length <= 2) {
      parts.push('Modified ' + modified.join(', '));
    } else {
      parts.push('Modified ' + modified.length + ' functions');
    }
  }

  // Pattern 3: Removed functions
  if (removed.length > 0) {
    if (removed.length <= 2) {
      parts.push('Removed ' + removed.join(', '));
    } else {
      parts.push('Removed ' + removed.length + ' functions');
    }
  }

  if (parts.length === 0) return '';

  let narrative = parts.join('. ') + '.';

  // Add risk context if significant
  if (change.impact && change.impact.risk !== 'LOW') {
    narrative += ' (' + change.impact.risk + ' risk \u2014 ' + change.impact.affected_count + ' in blast radius)';
  }

  return narrative;
}

function buildSemanticGroups(history) {
  // Step 1: Collect all changed functions with their files
  const items = []; // {name, file, dir, type, changeIdx}
  history.forEach((c, idx) => {
    const file = (c.file || '').split('/').pop();
    const dir = (c.file || '').split('/').slice(-2, -1)[0] || 'root';
    (c.nodes_added || []).forEach(name => items.push({name, file, dir, type: 'added', changeIdx: idx}));
    (c.nodes_modified || []).forEach(name => items.push({name, file, dir, type: 'modified', changeIdx: idx}));
    (c.nodes_removed || []).forEach(name => items.push({name, file, dir, type: 'removed', changeIdx: idx}));
  });

  if (items.length === 0) return [];

  // Step 2: Union-Find by connectivity
  const parent = {};
  items.forEach((item, i) => { parent[i] = i; });

  function find(i) {
    while (parent[i] !== i) { parent[i] = parent[parent[i]]; i = parent[i]; }
    return i;
  }
  function union(a, b) {
    const ra = find(a), rb = find(b);
    if (ra !== rb) parent[ra] = rb;
  }

  // Union items in same file
  for (let i = 0; i < items.length; i++) {
    for (let j = i + 1; j < items.length; j++) {
      if (items[i].file === items[j].file) union(i, j);
    }
  }

  // Union items connected by CALLS edges
  const gData = graph3d ? graph3d.graphData() : {nodes:[]};
  for (let i = 0; i < items.length; i++) {
    const nd_i = gData.nodes.find(n => n.name === items[i].name);
    if (!nd_i) continue;
    for (let j = i + 1; j < items.length; j++) {
      const nd_j = gData.nodes.find(n => n.name === items[j].name);
      if (!nd_j) continue;
      const iCallsJ = (linkIndex.from[nd_i.id] || []).some(l => {
        const tid = typeof l.target === 'object' ? l.target.id : l.target;
        return tid === nd_j.id;
      });
      const jCallsI = (linkIndex.from[nd_j.id] || []).some(l => {
        const tid = typeof l.target === 'object' ? l.target.id : l.target;
        return tid === nd_i.id;
      });
      if (iCallsJ || jCallsI) union(i, j);
    }
  }

  // Step 3: Collect groups
  const groupMap = {};
  items.forEach((item, i) => {
    const root = find(i);
    if (!groupMap[root]) groupMap[root] = [];
    groupMap[root].push(item);
  });

  // Step 4: Label each group by dominant directory or file pattern
  const groups = Object.values(groupMap).map(members => {
    const dirCounts = {};
    members.forEach(m => { dirCounts[m.dir] = (dirCounts[m.dir] || 0) + 1; });
    const topDir = Object.entries(dirCounts).sort((a, b) => b[1] - a[1])[0][0];

    const files = [...new Set(members.map(m => m.file))];
    let label = topDir;
    if (files.length === 1) label = files[0].replace('.py', '');

    return {
      label,
      members,
      files,
      addedCount: members.filter(m => m.type === 'added').length,
      modifiedCount: members.filter(m => m.type === 'modified').length,
      removedCount: members.filter(m => m.type === 'removed').length,
    };
  });

  // Sort: largest groups first
  groups.sort((a, b) => b.members.length - a.members.length);
  return groups;
}
