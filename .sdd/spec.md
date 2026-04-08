# Visual Overhaul Specification — vector-graph v1.0

## 1. Overview

Ground-up restructuring of the 3D rendering pipeline to transform vector-graph from a functional prototype into a visually stunning code observatory. The core insight: EffectComposer and UnrealBloomPass are already CDN-loaded but unused — enabling them unlocks shader-based bloom, the single biggest visual upgrade. Combined with instanced rendering and edge overhaul, this creates a product-quality visualization.

## 2. Background & Motivation

The current renderer was built incrementally (v0.4-v0.9), adding effects one-by-one:
- "Glow" is opaque sphere meshes pulsing opacity — looks flat, costs draw calls
- 600 nodes = 600 unique materials = 600 draw calls (no instancing)
- Edges are thin built-in lines with no anti-aliasing or visual weight
- 6 separate requestAnimationFrame loops, uncoordinated
- Nebulae are transparent spheres + random particles — unclear visual metaphor
- No depth cues (no fog, no DOF, no ground reference)

The result: it works but looks like a prototype. For a tool whose entire value proposition is "see your code", the visual must be exceptional.

## 3. Goals

### MUST (v1.0 release blockers)
- M1: Shader-based bloom via EffectComposer (selective — nodes/edges glow, labels don't)
- M2: Instanced node rendering (InstancedMesh per type, ~15 draw calls instead of 600)
- M3: Unified animation loop (single RAF drives everything)
- M4: Depth atmosphere (linear fog, distance-based fade)
- M5: 60fps on 600-node graph (Logic mode, integrated GPU)
- M6: All 15 existing E2E tests pass, no visual regression

### SHOULD (strong quality targets)
- S1: Edge rendering overhaul (anti-aliased fat lines, animated flow)
- S2: Camera spring physics (inertial movement, smooth deceleration)
- S3: Fresnel rim glow on node meshes (shader-based edge highlight)
- S4: Nebula boundary shader (volumetric fog instead of solid spheres)

### MAY (nice-to-have, defer to v1.1)
- MAY1: Edge bundling (force-directed Bezier grouping between clusters)
- MAY2: Depth-of-field on extreme zoom
- MAY3: Theme system (multiple Catppuccin variants + community themes)
- MAY4: GPU particle system for nebula stardust

## 4. Non-Goals

- Dropping 3d-force-graph entirely (keep its force layout + interaction, override rendering)
- Custom WebGL shaders from scratch (use Three.js built-in materials + post-processing)
- VR/AR support
- Mobile optimization (desktop-first tool)
- Changing the data model, API, or backend

## 5. Architecture

### Current Pipeline

```
3d-force-graph owns the render loop
  └── renderer.render(scene, camera)  ← called internally, we can't touch
       ├── Nodes: 600x individual Mesh (shared geo, unique MeshLambertMaterial)
       ├── Edges: built-in thin lines (no AA, no glow)
       └── Bolted on: nebula spheres, glow sphere meshes, ripple rings
           (6 separate RAF loops)
```

### Target Pipeline

```
3d-force-graph still manages layout + physics + interaction
  └── BUT we intercept renderer.render() → redirect to EffectComposer
       ├── RenderPass (scene → framebuffer)
       ├── UnrealBloomPass (selective bloom, emissive-threshold driven)
       └── Output pass (final composite to screen)
       
Nodes: InstancedMesh per type (15 draw calls total)
  └── MeshStandardMaterial with emissive → bloom handles glow naturally
  └── Per-instance color + scale via InstancedBufferAttribute

Effects: Bloom replaces ALL geometry-based glow
  └── Selected node: high emissive → bright bloom halo
  └── Changed nodes: gold emissive → warm bloom spread
  └── Normal nodes: dim emissive → soft ambient glow

Animation: Single tick() loop
  └── registerTick(fn, priority) → all subsystems on one RAF
```

### Renderer Intercept (key technique)

```javascript
const renderer = graph3d.renderer();
const scene = graph3d.scene();
const camera = graph3d.camera();

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
composer.addPass(new UnrealBloomPass(res, strength, radius, threshold));

// Intercept: library calls renderer.render() internally → we redirect to composer
renderer.render = function() { composer.render(); };
```

Non-invasive. 3d-force-graph keeps doing its job. We just change what "render" means.

### Selective Bloom Strategy

Not everything should bloom. Labels must stay sharp.

**Threshold approach** (simpler, try first):
- Set bloom threshold = 0.6
- Normal objects: MeshStandardMaterial, color only, no emissive → below threshold, no bloom
- Bloom objects: set emissive color + emissiveIntensity > 0.6 → blooms
- Labels: dark background sprites → well below threshold

**Layer approach** (fallback if threshold insufficient):
- Layer 0: non-bloom (labels, UI)
- Layer 1: bloom (nodes, edges)
- Two-pass render with compositing

## 6. Phased Delivery

### Phase A: Bloom + Emissive (highest visual impact, lowest structural risk)

New file `js/renderer.js`:
- EffectComposer setup
- RenderPass + UnrealBloomPass
- renderer.render() intercept
- Bloom parameter tuning API

Changes to existing files:
- `core.js`: MeshLambertMaterial → MeshStandardMaterial with emissive in nodeThreeObject
- `effects.js`: Remove geometry-based glow spheres (addChangeGlowRings, addSelectionGlow). Replace with emissive intensity changes on node materials
- `appearance.js`: getNodeColor → also return emissive values; refreshNodeAppearance updates emissive
- `config.js`: Add BLOOM_PARAMS, EMISSIVE_MAP constants
- `state.js`: Add composer/bloomPass references
- `web_server.py`: Add renderer.js to _JS_LOAD_ORDER

### Phase B: Atmosphere + Unified Tick

New file `js/animation.js`:
- Single tick() RAF loop
- registerTick(fn, priority) system
- Spring interpolation functions

New file `js/atmosphere.js`:
- Scene fog setup
- Ambient dust particles

Changes:
- `core.js`: Remove FPS RAF loop, register as tick callback
- `effects.js`: Remove glow RAF loops (already removed in Phase A)
- `panels.js`: Remove minimap RAF loop, register as tick callback
- `appearance.js`: Remove setInterval for labels, register as tick callback

### Phase C: Instanced Rendering

New file `js/instancing.js`:
- InstancedMesh factory per node type
- Per-instance color/scale attribute updates
- Integration with 3d-force-graph position data

Changes:
- `core.js`: nodeThreeObject returns invisible Object3D (placeholder for physics), real rendering via instances
- `appearance.js`: refreshNodeAppearance works via instance attributes instead of material.color.set
- `config.js`: Remove per-node material creation

### Phase D: Edge Overhaul (SHOULD)

- THREE.Line2 for anti-aliased wide edges (requires importing Line2 from Three.js examples)
- Custom edge material with animated flow (shader uniform for time)
- Directional gradient (source color → target color along edge)

## 7. Test Contracts

### E2E (Playwright)

- [ ] `test_bloom_no_js_errors`: Page loads with bloom pipeline active, zero JS errors
- [ ] `test_bloom_canvas_not_blank`: Screenshot pixel analysis confirms non-black content
- [ ] `test_bloom_stats_correct`: Status bar counts match pre-bloom values
- [ ] `test_fog_depth_perception`: Near nodes visually distinct from far nodes
- [ ] `test_mode_switch_with_bloom`: Arch/Logic/Deep switching works with composer active
- [ ] `test_selection_emissive`: Node selection changes visual brightness
- [ ] `test_fps_above_30`: FPS counter reads >= 30 after graph stabilizes
- [ ] `test_label_not_bloomed`: Label text remains readable (not washed out)

### Unit (pytest)

- [ ] `test_bloom_params_valid`: BLOOM_PARAMS constants have required keys
- [ ] `test_load_order_includes_new_files`: _JS_LOAD_ORDER contains renderer.js, animation.js, etc.
- [ ] `test_all_js_files_exist`: Every file in load order exists on disk
- [ ] `test_no_duplicate_declarations`: No `let`/`const` variable declared in multiple JS files at top scope

### Regression

- [ ] All 15 existing E2E tests pass
- [ ] All 824 existing unit tests pass

## 8. Acceptance Criteria

- [ ] AC1: Nodes have visible soft luminous halos (bloom), not flat matte surfaces
- [ ] AC2: Selected node is visually brighter than neighbors (emissive bloom)
- [ ] AC3: Changed nodes glow gold via emissive + bloom (no sphere mesh overlays)
- [ ] AC4: Labels remain sharp and readable (not blurred by bloom)
- [ ] AC5: Fog creates depth — far nodes fade into dark background
- [ ] AC6: Single requestAnimationFrame loop in codebase (verified by grep)
- [ ] AC7: FPS >= 30 on Logic mode / 600 nodes (status bar measurement)
- [ ] AC8: Existing 15 E2E tests pass without modification
- [ ] AC9: Existing 824 unit tests pass without modification
- [ ] AC10: Before/after screenshots show clear visual improvement — CEO approved

## 9. Open Questions

1. **Bloom threshold vs. layer approach**: Try threshold first (simpler). If labels bloom unintentionally, switch to layer-based selective bloom. Need to experiment.

2. **3d-force-graph compatibility**: renderer.render() intercept works in tests but need to verify with all interaction modes (drag, zoom, hover tooltip rendering). If tooltips break, may need to intercept at a different level.

3. **InstancedMesh + node selection**: 3d-force-graph uses raycasting on individual Mesh objects for onClick/onHover. InstancedMesh raycasting works differently. Phase C needs to handle this — either keep invisible placeholder meshes for raycasting or implement custom InstancedMesh raycaster.

4. **MeshStandardMaterial performance**: More expensive than MeshLambertMaterial (PBR lighting model). With instancing (Phase C), the per-fragment cost is offset by reduced draw calls. In Phase A (before instancing), may see slight FPS drop on large graphs. Monitor.

5. **Three.js version**: Current v0.137.0 is from 2022. InstancedMesh and EffectComposer are available but the API may differ from current docs. Pin to 0.137.0 for all examples.
