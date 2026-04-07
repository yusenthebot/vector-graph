# Agent Status — v0.9.2

## Session: 2026-04-06

### Current State

- Branch: `main` (after merge from `feat/beta-panel-collapse`)
- Tests: 824 passed, 86% coverage
- Version: 0.9.2

### Completed This Session

| Version | Features |
|---------|----------|
| v0.8.0 | Hover-to-show edges, connectivity-based node sizing |
| v0.9.0 | Status bar, panel collapse, command palette |
| v0.9.1 | Node labels, CALLS arrows, legend, minimap, glow halo, edge dashes, constellation expand |
| v0.9.2 | Impact graph fix (activeChangeIds fallback, auto-expand, XSS fix) |

### Phase 2 Complete: graph.js Modularization

Split 3271-line monolith into 12 files under `static/js/`:
config(76), state(46), appearance(106), core(491), nebulae(223),
selection(269), sidebar(274), search(159), changes(653), impact(470),
effects(156), panels(357). All under 800 lines. No behavior change.

### Completed (Alpha)

- `feat/alpha-dev-hot-reload`: `--dev` hot reload mode added to web server (824 tests pass)

### Completed (Beta)

- `feat/beta-e2e-playwright`: Playwright E2E test infrastructure — pyproject.toml updated, tests/e2e/ created with conftest + test_initial_load (5 tests), 824 unit tests still pass

### Next: v1.0.0

1. mcp_server.py split (1007 lines -> 3 files) [optional]
2. PyPI release + theme switching + zen mode
