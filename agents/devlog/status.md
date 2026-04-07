# Agent Status — v0.9.1

## Session: 2026-04-06

### v0.9.0 Features Complete

| Feature | Agent | Status |
|---------|-------|--------|
| Status bar | Alpha | done |
| Panel collapse (Ctrl+B/Ctrl+I) | Beta | done |
| Command palette (Ctrl+K, /) | Alpha | done |
| Stacked accordions (replace tabs) | Beta | done |

### v0.9.1 In Progress

| Feature | Agent | Status |
|---------|-------|--------|
| F2: Default CALLS arrows | Alpha | done |
| F3: Nebula label improvements | Alpha | done |
| F6: Edge dash patterns | Alpha | done |
| F4: Legend panel | Beta | merged |
| F7: Minimap overlay | Beta | merged |

| F1: Node text labels with LOD | Alpha | done |

**Alpha**: F1 node labels done — 2 new tests, 821 total passing. `_makeNodeLabel` + `_updateLabelVisibility` + Group wrapper in `nodeThreeObject`. `refreshNodeAppearance` updated for Group structure.
**Alpha**: v0.9.1 QA fixes committed — HIGH-1 THREE.js dispose (3 sites), HIGH-2 glow position tracking + neighbor nodeId, HIGH-3 minimap NaN guards, MEDIUM-1 linkLineDash compat check, MEDIUM-2 constellation timeout dedup. 821 tests still passing.
**Alpha**: [IN PROGRESS] v0.9.2 — fix empty impact graph + replace force-graph canvas with HTML impact tree. Working on: tests/unit/test_web_api.py (TestImpactTree), graph.js (buildImpactTree + fix activeChangeIds), graph.css (impact tree styles).
**Beta**: feat/beta-legend-minimap merged into main — legend + minimap integrated
