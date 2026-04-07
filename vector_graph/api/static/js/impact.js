// ── impact.js — Impact tree, impact panel, 2D force graph ──
// ── Impact Tree (v0.9.2 — replaces ForceGraph 2D canvas) ──────────────────

function _esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function buildImpactTree(change) {
  var changedFile = (change.file || '').split('/').pop();
  var gData = graph3d ? graph3d.graphData() : {nodes:[], links:[]};

  // Collect matched changed nodes
  var changedNodes = [];
  activeChangeIds.forEach(function(id) {
    var n = gData.nodes.find(function(nd){ return nd.id === id; });
    if (n) changedNodes.push(n);
  });

  if (changedNodes.length === 0) return '<div class="impact-tree-empty">No nodes matched</div>';

  var html = '<div class="impact-tree">';

  // Root: file header
  var typeLabel = change.type === 'created' ? 'NEW' : change.type === 'deleted' ? 'DEL' : 'MOD';
  var typeColor = change.type === 'created' ? 'var(--green)' : change.type === 'deleted' ? 'var(--red)' : 'var(--yellow)';
  html += '<div class="tree-root">';
  html += '<span class="tree-type" style="color:' + typeColor + '">' + typeLabel + '</span> ';
  html += '<span class="tree-file">' + _esc(changedFile) + '</span>';
  html += '</div>';

  // Changed functions / classes
  changedNodes.forEach(function(n) {
    if (n.label === 'File') return; // skip file-level nodes
    var added = (change.nodes_added || []).indexOf(n.name) >= 0;
    var removed = (change.nodes_removed || []).indexOf(n.name) >= 0;
    var color = added ? 'var(--green)' : removed ? 'var(--red)' : 'var(--yellow)';
    var prefix = added ? '+' : removed ? '-' : '~';

    html += '<div class="tree-branch">';
    html += '<div class="tree-node tree-changed" data-nid="' + _esc(n.id) + '" style="border-left-color:' + color + '">';
    html += '<span style="color:' + color + '">' + prefix + '</span> ';
    html += '<b>' + _esc(n.name) + '</b>';
    if (n.label) html += ' <span class="tree-label">' + _esc(n.label) + '</span>';
    html += '</div>';

    // Outgoing CALLS (what this function calls)
    var outCalls = (linkIndex.from[n.id] || []).filter(function(l) {
      return l.type === 'CALLS';
    });
    if (outCalls.length > 0) {
      var outResolved = [];
      outCalls.forEach(function(l) {
        var tid = typeof l.target === 'object' ? l.target.id : l.target;
        var tn = gData.nodes.find(function(nd){ return nd.id === tid; });
        if (tn) outResolved.push(tn);
      });
      if (outResolved.length > 0) {
        html += '<div class="tree-group">';
        html += '<div class="tree-group-label">calls (' + outResolved.length + ')</div>';
        outResolved.slice(0, 10).forEach(function(tn) {
          html += '<div class="tree-leaf" data-nid="' + _esc(tn.id) + '">';
          html += '<span class="tree-name">' + _esc(tn.name) + '</span>';
          html += '<span class="tree-file-hint">' + _esc((tn.file || '').split('/').pop()) + '</span>';
          html += '</div>';
        });
        if (outResolved.length > 10) html += '<div class="tree-more">+' + (outResolved.length - 10) + ' more</div>';
        html += '</div>';
      }
    }

    // Incoming CALLS (who calls this function)
    var inCalls = (linkIndex.to[n.id] || []).filter(function(l) {
      return l.type === 'CALLS';
    });
    if (inCalls.length > 0) {
      var inResolved = [];
      inCalls.forEach(function(l) {
        var sid = typeof l.source === 'object' ? l.source.id : l.source;
        var sn = gData.nodes.find(function(nd){ return nd.id === sid; });
        if (sn) inResolved.push(sn);
      });
      if (inResolved.length > 0) {
        html += '<div class="tree-group">';
        html += '<div class="tree-group-label">called by (' + inResolved.length + ')</div>';
        inResolved.slice(0, 10).forEach(function(sn) {
          html += '<div class="tree-leaf" data-nid="' + _esc(sn.id) + '">';
          html += '<span class="tree-name">' + _esc(sn.name) + '</span>';
          html += '<span class="tree-file-hint">' + _esc((sn.file || '').split('/').pop()) + '</span>';
          html += '</div>';
        });
        if (inResolved.length > 10) html += '<div class="tree-more">+' + (inResolved.length - 10) + ' more</div>';
        html += '</div>';
      }
    }

    html += '</div>'; // tree-branch
  });

  html += '</div>'; // impact-tree
  return html;
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

    // Change narrative — one-sentence description at the very top
    const narrative = generateChangeNarrative(change);
    if (narrative) {
      html += '<div class="insp-section" style="padding:8px 12px;border-left:2px solid ' + riskColor + '">';
      html += '<div style="font-size:11px;color:var(--text);line-height:1.5;font-style:italic">' + escHtml(narrative) + '</div>';
      html += '</div>';
    }

    // Session overview — semantic groups of changed functions
    if (changeHistory.length > 1) {
      const groups = buildSemanticGroups(changeHistory);
      if (groups.length > 0) {
        html += '<div class="insp-section"><h4>Session: ' + groups.length + ' change group' + (groups.length !== 1 ? 's' : '') + '</h4>';
        groups.forEach(group => {
          html += '<div style="margin-bottom:8px">';
          html += '<div style="font-size:10px;font-weight:bold;color:var(--text);margin-bottom:3px">' + escHtml(group.label) + ' <span style="color:var(--overlay0);font-weight:normal">(' + group.members.length + ')</span></div>';
          group.files.forEach(fname => {
            const fileMembers = group.members.filter(m => m.file === fname);
            const addCount = fileMembers.filter(m => m.type === 'added').length;
            const modCount = fileMembers.filter(m => m.type === 'modified').length;
            const remCount = fileMembers.filter(m => m.type === 'removed').length;
            html += '<div style="font-size:9px;padding:1px 0 1px 10px;color:var(--subtext)">';
            html += escHtml(fname);
            if (addCount) html += ' <span style="color:var(--green)">+' + addCount + '</span>';
            if (modCount) html += ' <span style="color:var(--yellow)">~' + modCount + '</span>';
            if (remCount) html += ' <span style="color:var(--red)">-' + remCount + '</span>';
            html += '</div>';
          });
          html += '</div>';
        });
        html += '</div>';
      }
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

    // ── 2D Impact Graph (force-directed) ──
    if (activeChangeIds.size > 0 && typeof ForceGraph !== 'undefined') {
      html += '<div class="insp-section"><h4>Impact Graph <span style="font-size:8px;color:var(--overlay0);font-weight:normal;text-transform:none">&mdash; click to expand</span></h4>';
      html += '<div id="impact-graph-container"></div>';
      html += '<div class="impact-graph-legend"><span class="legend-changed">changed</span> <span class="legend-caller">caller</span> <span class="legend-callee">callee</span></div>';
      html += '<div id="impact-node-detail"><span style="color:var(--overlay0);font-size:10px">Click a node to see details</span></div>';
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

  // Initialize 2D impact graph (after DOM is ready)
  setTimeout(function() {
    var container = document.getElementById('impact-graph-container');
    if (!container || typeof ForceGraph === 'undefined') return;

    if (impactGraph2d) { impactGraph2d._destructor && impactGraph2d._destructor(); impactGraph2d = null; }

    // Auto-expand: start with changed nodes + their 1-hop CALLS neighbors
    _expandedNode2d = null;
    // Pre-expand all changed nodes
    activeChangeIds.forEach(function(cid) { _expandedNode2d = cid; });
    // Build with last changed node expanded (shows its neighbors)
    var subgraph = buildImpactSubgraph();
    // Also add all other changed nodes' neighbors
    var gData = graph3d ? graph3d.graphData() : {nodes:[], links:[]};
    activeChangeIds.forEach(function(cid) {
      (linkIndex.to[cid] || []).forEach(function(l) {
        if (l.type !== 'CALLS') return;
        var sid = typeof l.source === 'object' ? l.source.id : l.source;
        if (!subgraph.nodes.find(function(n){return n.id===sid;})) {
          var src = gData.nodes.find(function(n){return n.id===sid;});
          if (src) subgraph.nodes.push({id:src.id, name:src.name, label:src.label, file:(src.file||'').split('/').pop(), _role:'caller', group:src.group});
        }
      });
      (linkIndex.from[cid] || []).forEach(function(l) {
        if (l.type !== 'CALLS') return;
        var tid = typeof l.target === 'object' ? l.target.id : l.target;
        if (!subgraph.nodes.find(function(n){return n.id===tid;})) {
          var tgt = gData.nodes.find(function(n){return n.id===tid;});
          if (tgt) subgraph.nodes.push({id:tgt.id, name:tgt.name, label:tgt.label, file:(tgt.file||'').split('/').pop(), _role:'callee', group:tgt.group});
        }
      });
    });
    // Rebuild edges for expanded set
    var nids = new Set(subgraph.nodes.map(function(n){return n.id;}));
    subgraph.links = [];
    gData.links.forEach(function(l) {
      var sid = typeof l.source === 'object' ? l.source.id : l.source;
      var tid = typeof l.target === 'object' ? l.target.id : l.target;
      if (nids.has(sid) && nids.has(tid) && (l.type === 'CALLS' || l.type === 'IMPORTS')) {
        subgraph.links.push({source:sid, target:tid, type:l.type});
      }
    });
    // Cap at 60 nodes
    if (subgraph.nodes.length > 60) {
      subgraph.nodes = subgraph.nodes.filter(function(n){return n._role==='changed';}).concat(
        subgraph.nodes.filter(function(n){return n._role!=='changed';}).slice(0, 60 - activeChangeIds.size)
      );
      nids = new Set(subgraph.nodes.map(function(n){return n.id;}));
      subgraph.links = subgraph.links.filter(function(l){return nids.has(l.source) && nids.has(l.target);});
    }

    if (subgraph.nodes.length === 0) return;

    var width = container.clientWidth;
    var height = 350;

    impactGraph2d = ForceGraph()(container)
      .graphData(subgraph)
      .width(width)
      .height(height)
      .backgroundColor('#1e1e2e')
      .nodeColor(function(n) {
        if (n._role === 'changed') return '#f9e2af';
        if (n._role === 'caller') return '#fab387';
        if (n._role === 'callee') return '#89b4fa';
        return '#585b70';
      })
      .nodeVal(function(n) {
        return n._role === 'changed' ? 5 : 3;
      })
      .nodeLabel(function(n) {
        return _esc(n.name) + ' (' + _esc(n.label) + ')\n' + _esc(n.file || '');
      })
      .nodeCanvasObjectMode(function() { return 'after'; })
      .nodeCanvasObject(function(n, ctx, globalScale) {
        var fontSize = Math.max(10 / globalScale, 2.5);
        ctx.font = fontSize + 'px monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillStyle = n._role === 'changed' ? '#f9e2af' : n._role === 'caller' ? '#fab387' : '#89b4fa';
        var label = n.name;
        if (label.length > 20) label = label.slice(0, 18) + '..';
        ctx.fillText(label, n.x, n.y + 6);
      })
      .linkColor(function(l) { return l.type === 'CALLS' ? '#89b4fa44' : '#fab38744'; })
      .linkWidth(1.5)
      .linkDirectionalArrowLength(5)
      .linkDirectionalArrowRelPos(1)
      .linkCurvature(0.15)
      .onNodeClick(function(n) {
        if (n && n.id) {
          expand2dNode(n.id);
          previewNode(n.id);
        }
      })
      .cooldownTicks(80)
      .warmupTicks(40);

    impactGraph2d.d3Force('charge').strength(subgraph.nodes.length > 20 ? -400 : -200);
    impactGraph2d.d3Force('link').distance(subgraph.nodes.length > 20 ? 80 : 60);
  }, 100);

  // Fetch test suggestions async
  if (changedNames.length > 0) {
    fetchTestSuggestions(changedNames);
  }
}
