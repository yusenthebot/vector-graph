// ── effects.js — Glow rings, selection halos, change highlight ──
// ── Pulsing glow rings for spotlight change mode ──────────────
function addChangeGlowRings() {
  if (!graph3d || typeof THREE === 'undefined') return;
  const scene = graph3d.scene();
  if (!scene) return;

  // Remove previous glow rings
  if (_changeGlowGroup) {
    scene.remove(_changeGlowGroup);
    _changeGlowGroup = null;
  }

  _changeGlowGroup = new THREE.Group();
  const gData = graph3d.graphData();

  gData.nodes.forEach(n => {
    if (!activeChangeIds.has(n.id)) return;
    const geo = new THREE.SphereGeometry(1, 16, 12);
    const mat = new THREE.MeshBasicMaterial({
      color: 0xf9e2af,
      transparent: true,
      opacity: 0.3,
    });
    const glow = new THREE.Mesh(geo, mat);
    const size = (SIZES[n.label] || 2) * 2.5;
    glow.scale.set(size, size, size);
    glow.position.set(n.x || 0, n.y || 0, n.z || 0);
    glow.userData = { nodeId: n.id };
    _changeGlowGroup.add(glow);
  });

  scene.add(_changeGlowGroup);

  // Animate pulse
  function pulseGlow() {
    if (!_changeGlowGroup || !changeHighlightActive) return;
    const t = (Date.now() % 2000) / 2000;
    const opacity = 0.15 + 0.2 * Math.sin(t * Math.PI * 2);
    _changeGlowGroup.children.forEach(function(child) {
      if (child.material) child.material.opacity = opacity;
    });
    requestAnimationFrame(pulseGlow);
  }
  pulseGlow();
}

function clearChangeHighlight() {
  changeHighlightActive = false;
  activeChangeIds.clear();
  activeImpactIds.clear();
  // Destroy 2D impact graph
  if (impactGraph2d) { impactGraph2d._destructor && impactGraph2d._destructor(); impactGraph2d = null; }
  // Remove pulsing glow rings
  if (_changeGlowGroup && graph3d) {
    const scene = graph3d.scene();
    if (scene) {
      _changeGlowGroup.traverse(function(obj) {
        if (obj.geometry) obj.geometry.dispose();
        if (obj.material) { if (obj.material.map) obj.material.map.dispose(); obj.material.dispose(); }
      });
      scene.remove(_changeGlowGroup);
    }
    _changeGlowGroup = null;
  }
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
  updateStatusBar();
}

// ── Selection glow halo (F5) ────────────────────────────────
function addSelectionGlow(nodeId) {
  if (!graph3d || typeof THREE === 'undefined') return;
  var scene = graph3d.scene();
  if (!scene) return;
  removeSelectionGlow();

  _selectionGlowGroup = new THREE.Group();
  var gData = graph3d.graphData();

  // Main glow on selected node
  var selNode = gData.nodes.find(function(n) { return n.id === nodeId; });
  if (selNode) {
    var geo = new THREE.SphereGeometry(1, 16, 12);
    var mat = new THREE.MeshBasicMaterial({ color: 0xcdd6f4, transparent: true, opacity: 0.3 });
    var glow = new THREE.Mesh(geo, mat);
    var size = (SIZES[selNode.label] || 2) * 3.0;
    glow.scale.set(size, size, size);
    glow.position.set(selNode.x || 0, selNode.y || 0, selNode.z || 0);
    glow.userData = { nodeId: nodeId, isPrimary: true };
    _selectionGlowGroup.add(glow);
  }

  // Faint glow on connected neighbors
  highlightNodes.forEach(function(nid) {
    var nd = gData.nodes.find(function(n) { return n.id === nid; });
    if (!nd) return;
    var geo2 = new THREE.SphereGeometry(1, 12, 8);
    var mat2 = new THREE.MeshBasicMaterial({ color: 0xcdd6f4, transparent: true, opacity: 0.1 });
    var g2 = new THREE.Mesh(geo2, mat2);
    var s2 = (SIZES[nd.label] || 2) * 2.0;
    g2.scale.set(s2, s2, s2);
    g2.position.set(nd.x || 0, nd.y || 0, nd.z || 0);
    g2.userData = { nodeId: nid };
    _selectionGlowGroup.add(g2);
  });

  scene.add(_selectionGlowGroup);

  // Pulse animation for primary glow — also tracks live node positions during simulation
  function pulseSelGlow() {
    if (!_selectionGlowGroup || !selectedId) return;
    var t = (Date.now() % 3000) / 3000;
    var gData = graph3d ? graph3d.graphData() : null;
    _selectionGlowGroup.children.forEach(function(child) {
      if (child.userData && child.userData.nodeId && gData) {
        var nd = gData.nodes.find(function(n) { return n.id === child.userData.nodeId; });
        if (nd) child.position.set(nd.x || 0, nd.y || 0, nd.z || 0);
      }
      if (child.userData && child.userData.isPrimary) {
        child.material.opacity = 0.2 + 0.2 * Math.sin(t * Math.PI * 2);
      }
    });
    requestAnimationFrame(pulseSelGlow);
  }
  pulseSelGlow();
}

function removeSelectionGlow() {
  if (_selectionGlowGroup && graph3d) {
    var scene = graph3d.scene();
    if (scene) {
      _selectionGlowGroup.traverse(function(obj) {
        if (obj.geometry) obj.geometry.dispose();
        if (obj.material) { if (obj.material.map) obj.material.map.dispose(); obj.material.dispose(); }
      });
      scene.remove(_selectionGlowGroup);
    }
    _selectionGlowGroup = null;
  }
}
