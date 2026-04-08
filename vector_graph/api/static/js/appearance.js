// ── appearance.js — Node color, size, and appearance logic ──

// ── LOD label visibility — throttled at 200ms (5fps), distance-based ──
function _updateLabelVisibility() {
  if (!graph3d) return;
  var cam = graph3d.camera();
  if (!cam) return;
  var camPos = cam.position;
  graph3d.graphData().nodes.forEach(function(n) {
    var obj = n.__threeObj;
    if (!obj || !obj.children) return;
    obj.children.forEach(function(child) {
      if (child.userData && child.userData.isNodeLabel) {
        var dx = (n.x || 0) - camPos.x;
        var dy = (n.y || 0) - camPos.y;
        var dz = (n.z || 0) - camPos.z;
        var dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
        if (dist < 120) {
          child.visible = true;
        } else if (dist < 250) {
          child.visible = (n.label === 'Class' || n.label === 'File');
        } else {
          child.visible = false;
        }
      }
    });
  });
}

// ── Extracted node color logic (standalone for nodeThreeObject + refreshNodeAppearance) ──
function getNodeColor(n) {
  // 1. User selection (click) — highest priority
  if (selectedId) {
    if (n.id === selectedId) return '#cdd6f4'; // bright but not white — readable
    if (highlightNodes.has(n.id)) return GROUP_COLORS[n.group] || COLORS[n.label] || '#cdd6f4';
    return '#313244'; // dimmed but visible — spatial context preserved
  }
  // 2. Change highlight — spotlight: changed nodes glow, rest keeps NORMAL color
  if (changeHighlightActive) {
    if (activeChangeIds.has(n.id)) return '#f9e2af'; // bright yellow — directly changed
    if (activeImpactIds.has(n.id)) return '#fab387'; // warm orange — impact chain
    // SPOTLIGHT: fall through to normal rendering — spatial context preserved
  }
  // 3. Cumulative heat (session-level, always shown)
  const heat = cumulativeHeat[n.id] || 0;
  if (heat > 0) {
    if (heat >= 4) return '#f38ba8';
    if (heat >= 2) return '#fab387';
  }
  // 3b. Hotspot gradient (opt-in toggle — change frequency heatmap)
  if (hotspotMode && n.hotspotScore !== undefined) {
    const s = n.hotspotScore;
    if (s >= 0.8) return '#f38ba8';   // hot red — very volatile
    if (s >= 0.5) return '#fab387';   // orange — moderately volatile
    if (s >= 0.2) return '#f9e2af';   // yellow — some changes
    return '#89b4fa';                  // cool blue — stable
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
  if (selectedId && n.id !== selectedId && !highlightNodes.has(n.id)) return 1.0;
  let base = SIZES[n.label] || 2;
  // Connectivity-based sizing (v0.8.0)
  const connectivity = (n.fanIn || 0) + (n.fanOut || 0);
  if (connectivity > 0) {
    base = base * (1 + Math.log2(connectivity + 1) * 0.25);
  }
  // File nodes: size by symbol count
  if (n.label === 'File' && (n.function_count || n.class_count)) {
    const symbols = (n.function_count || 0) + (n.class_count || 0);
    base = base * (1 + Math.log2(symbols + 1) * 0.3);
  }
  if (changeHighlightActive) {
    if (activeChangeIds.has(n.id)) return base * 1.8; // 1.8x — noticeable but not extreme
    if (activeImpactIds.has(n.id)) return base * 1.3; // slight boost
    // SPOTLIGHT: fall through to normal sizing
  }
  if (n.complexity) return base + Math.min(n.complexity * 0.3, 5);
  return base;
}

// ── Refresh node appearance in-place (replaces nodeColor/nodeVal re-trigger) ──
function refreshNodeAppearance() {
  if (!graph3d) return;
  graph3d.graphData().nodes.forEach(n => {
    const obj = n.__threeObj;
    if (!obj) return;
    // Handle both direct Mesh (legacy) and Group wrapper (with label sprite)
    const mesh = obj.isMesh ? obj : (obj.children && obj.children[0]);
    if (mesh && mesh.material) {
      var c = getNodeColor(n);
      mesh.material.color.set(c);
      // Emissive for bloom: color matches node color, intensity drives bloom visibility
      if (mesh.material.emissive !== undefined) {
        mesh.material.emissive.set(c);
        mesh.material.emissiveIntensity = typeof getNodeEmissive === 'function' ? getNodeEmissive(n) : 0.15;
      }
      const s = getNodeSize(n) * 0.8;
      mesh.scale.set(s, s, s);
    }
  });
}
