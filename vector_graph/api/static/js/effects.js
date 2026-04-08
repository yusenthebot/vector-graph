// ── effects.js — Change highlight, selection glow (bloom-driven, no geometry overlays) ──

// Change glow: bloom handles the visual — we just set emissive intensity high on changed nodes.
// No more sphere mesh overlays.
function addChangeGlowRings() {
  // Bloom-driven: refreshNodeAppearance() already sets high emissive on changed nodes
  // via getNodeEmissive(). Nothing extra needed here.
  // The old sphere-mesh glow approach is removed — bloom replaces it entirely.
  refreshNodeAppearance();
}

function clearChangeHighlight() {
  changeHighlightActive = false;
  activeChangeIds.clear();
  activeImpactIds.clear();
  // Destroy 2D impact graph
  if (impactGraph2d) { impactGraph2d._destructor && impactGraph2d._destructor(); impactGraph2d = null; }
  // No glow geometry to clean up — bloom-driven
  _changeGlowGroup = null;
  // Close impact panel
  document.getElementById('inspector').classList.remove('open');
  setTimeout(function() { if (graph3d) graph3d.width(document.getElementById('graph-container').clientWidth); }, 100);
  // Re-render with normal emissive (low intensity = no bloom)
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

// Selection glow: bloom-driven — set high emissive on selected node, medium on neighbors.
// No more sphere mesh overlays.
function addSelectionGlow(nodeId) {
  // Bloom handles the glow via emissive intensity in refreshNodeAppearance().
  // No geometry overlays needed.
  refreshNodeAppearance();
}

function removeSelectionGlow() {
  // No geometry to dispose — bloom-driven
  _selectionGlowGroup = null;
  refreshNodeAppearance();
}
