// ── renderer.js — Post-processing pipeline: bloom, fog, render intercept ──

// Bloom configuration — tune these for visual quality
const BLOOM_PARAMS = {
  strength: 1.5,    // bloom brightness
  radius: 0.4,      // bloom spread
  threshold: 0.35,  // brightness floor (below = no bloom)
};

// Emissive intensity presets — drive selective bloom via material emissive
const EMISSIVE = {
  normal: 0.15,     // subtle ambient glow — below bloom threshold
  selected: 0.95,   // bright halo on selected node
  highlight: 0.45,  // connected neighbors
  changed: 1.0,     // golden bloom on changed nodes
  impact: 0.65,     // warm impact chain
  dimmed: 0.03,     // barely visible when another node is selected
  heat2: 0.5,       // cumulative heat level 2+
  heat4: 0.75,      // cumulative heat level 4+
};

// Fog configuration
const FOG_PARAMS = {
  color: 0x11111b,  // match background
  density: 0.0025,  // exponential fog density
};

// Post-processing state (set by setupPostProcessing)
let _composer = null;
let _bloomPass = null;

/**
 * Set up EffectComposer with bloom and wire it into 3d-force-graph's render loop.
 * Call this ONCE after initGraph() has created graph3d.
 */
function setupPostProcessing() {
  if (!graph3d || typeof THREE === 'undefined') return;
  if (typeof THREE.EffectComposer === 'undefined') {
    console.warn('EffectComposer not loaded — skipping post-processing');
    return;
  }

  var renderer = graph3d.renderer();
  var scene = graph3d.scene();
  var camera = graph3d.camera();
  if (!renderer || !scene || !camera) return;

  // --- Fog ---
  scene.fog = new THREE.FogExp2(FOG_PARAMS.color, FOG_PARAMS.density);

  // --- Tone mapping for HDR bloom ---
  renderer.toneMapping = THREE.ReinhardToneMapping;
  renderer.toneMappingExposure = 1.8;

  // --- EffectComposer ---
  _composer = new THREE.EffectComposer(renderer);

  var renderPass = new THREE.RenderPass(scene, camera);
  _composer.addPass(renderPass);

  var size = renderer.getSize(new THREE.Vector2());
  _bloomPass = new THREE.UnrealBloomPass(size, BLOOM_PARAMS.strength, BLOOM_PARAMS.radius, BLOOM_PARAMS.threshold);
  _composer.addPass(_bloomPass);

  // --- Render intercept ---
  // 3d-force-graph calls renderer.render(scene, camera) each frame.
  // We redirect that to composer.render(), which internally calls the
  // original renderer.render via RenderPass.  A recursion guard prevents loops.
  var _origRender = renderer.render.bind(renderer);
  var _composing = false;

  renderer.render = function(s, c) {
    if (_composing) {
      // Called by EffectComposer's RenderPass — use original WebGL render
      _origRender(s, c);
    } else {
      // Called by 3d-force-graph's animation loop — redirect to composer
      _composing = true;
      _composer.render();
      _composing = false;
    }
  };

  // --- Handle resize ---
  var _resizeTimer = null;
  window.addEventListener('resize', function() {
    clearTimeout(_resizeTimer);
    _resizeTimer = setTimeout(function() {
      if (_composer && renderer) {
        var newSize = renderer.getSize(new THREE.Vector2());
        _composer.setSize(newSize.x, newSize.y);
      }
    }, 100);
  });

  // --- Ambient dust particles (depth reference) ---
  var dustCount = 1500;
  var dustPositions = new Float32Array(dustCount * 3);
  for (var i = 0; i < dustCount * 3; i++) {
    dustPositions[i] = (Math.random() - 0.5) * 1000;
  }
  var dustGeo = new THREE.BufferGeometry();
  dustGeo.setAttribute('position', new THREE.BufferAttribute(dustPositions, 3));
  var dustMat = new THREE.PointsMaterial({
    color: 0x585b70,
    size: 0.4,
    transparent: true,
    opacity: 0.12,
    depthWrite: false,
    fog: true,
  });
  scene.add(new THREE.Points(dustGeo, dustMat));
}

/**
 * Get the emissive intensity for a node based on current state.
 * Used by appearance.js to set material.emissiveIntensity.
 */
function getNodeEmissive(n) {
  // 1. User selection
  if (selectedId) {
    if (n.id === selectedId) return EMISSIVE.selected;
    if (highlightNodes.has(n.id)) return EMISSIVE.highlight;
    return EMISSIVE.dimmed;
  }
  // 2. Change highlight
  if (changeHighlightActive) {
    if (activeChangeIds.has(n.id)) return EMISSIVE.changed;
    if (activeImpactIds.has(n.id)) return EMISSIVE.impact;
  }
  // 3. Cumulative heat
  var heat = cumulativeHeat[n.id] || 0;
  if (heat >= 4) return EMISSIVE.heat4;
  if (heat >= 2) return EMISSIVE.heat2;
  // 4. Default
  return EMISSIVE.normal;
}
