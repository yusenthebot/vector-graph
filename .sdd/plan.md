# Visual Overhaul — Technical Plan

## 1. Architecture Overview

Intercept 3d-force-graph's render call, redirect through EffectComposer for bloom. Switch node materials from MeshLambertMaterial to MeshStandardMaterial with emissive. Remove all geometry-based glow effects. Consolidate animation loops. Add fog.

## 2. Technical Decisions

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Post-processing | EffectComposer + UnrealBloomPass (already loaded) | Zero new dependencies |
| Bloom selectivity | Threshold-based (emissive > threshold blooms) | Simpler than layer compositing |
| Node material | MeshStandardMaterial | Has emissive property for bloom |
| Glow effects | Remove sphere meshes, use emissive intensity | Bloom replaces all manual glow |
| Animation | Single RAF tick with callbacks | Replaces 6 separate loops |
| Fog | THREE.FogExp2 | Depth perception |

## 3. Phase A Implementation (this execution)

1. Create `js/renderer.js` — EffectComposer setup, bloom, render intercept, fog, dust
2. Update `js/config.js` — BLOOM_PARAMS, EMISSIVE_INTENSITIES
3. Update `js/core.js` — MeshStandardMaterial in nodeThreeObject, call setupRenderer after initGraph
4. Update `js/appearance.js` — emissive-aware color/refresh
5. Update `js/effects.js` — remove geometry glow, emissive-based highlighting
6. Update `js/state.js` — add composer/bloomPass refs
7. Update `web_server.py` — renderer.js in load order
8. Verify: all 839 tests pass
