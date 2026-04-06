# Agent Status — v0.9.0

## Session: 2026-04-06

### Completed: v0.8.0 Intuitive Visualization

All P0 items shipped. 778 tests, 86% coverage, zero regressions.

| Feature | Agent | Tests Added |
|---------|-------|-------------|
| Fan-in/fan-out in build_graph_data | Alpha | 5 |
| 2D label collision avoidance | Beta | 3 |
| Hover-to-show edges | Alpha | 4 |
| Connectivity-based node sizing | Alpha | (included above) |
| Docs + version bump | Dispatcher | 0 |

### In Progress: v0.9.0 Panel Collapse

| Feature | Agent | Status |
|---------|-------|--------|
| Panel collapse Ctrl+B/Ctrl+I | Beta | done — 784 tests, 0 regressions |

### Changes Summary

**graph.js**:
- `hoveredId` state + `onNodeHover` callback
- Edge callbacks: default opacity/width/color = 0/0/transparent; hover shows 1-hop edges
- `getNodeSize()`: connectivity-based scaling via `Math.log2(fanIn + fanOut + 1) * 0.25`
- 2D impact graph: conditional labels (hover-only when >15 nodes), adaptive forces

**web_server.py**:
- `build_graph_data()`: `fanIn`/`fanOut` fields on every node

**pyproject.toml**: 0.5.0 -> 0.8.0
