# Agent Status — v1.0.0-dev

## Session: 2026-04-07

### Current State

- Branch: `main`
- Tests: 839 (824 unit + 15 E2E), all passing
- Version: 0.9.2 (will bump to 1.0.0 on release)

### Completed This Session

**Phase 1: Housekeeping** — merged to main, version bump, branch cleanup

**Phase 2: graph.js Modularization** — 3271 lines split into 12 modules under static/js/

**Phase 3: Frontend Harness** — --dev hot reload, 15 Playwright E2E tests, GitHub Actions CI

**Phase A: Visual Overhaul — Bloom** (SDD-driven)
- EffectComposer + UnrealBloomPass post-processing pipeline
- MeshStandardMaterial with emissive replaces MeshLambertMaterial
- Selective bloom via emissive intensity (nodes glow, labels stay sharp)
- FogExp2 depth atmosphere + ambient dust particles
- Removed all geometry-based glow (sphere mesh overlays)
- renderer.js intercepts 3d-force-graph's render loop

### Next: Visual Overhaul Phases B-D

- Phase B: Unified tick loop + spring camera
- Phase C: Instanced rendering (600 draw calls → 15)
- Phase D: Edge overhaul (anti-aliased, animated flow)
